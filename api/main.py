import asyncio
import os
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Union
from datetime import datetime, date
import urllib.parse # Needed for relogin redirect error message
import json # Import json module

from fastapi import FastAPI, HTTPException, Query, Path, Body, Depends, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from twikit import Client
# Restore specific NotFound import, as identified in logs
from twikit.errors import NotFound # Removed others for now, add back if needed

# --- Configuration & Logging ---
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment Mode ---
ENV_TYPE = os.environ.get('ENV_TYPE', 'dev').lower() # Default to dev
logger.info(f"Running in ENV_TYPE: {ENV_TYPE}")

# --- Template Engine (Conditional) ---
templates: Optional[Jinja2Templates] = None
if ENV_TYPE == 'dev':
    templates = Jinja2Templates(directory="templates")

# --- Global Twikit Client ---
twikit_client: Optional[Client] = None
login_error_message: Optional[str] = None # Used only in dev mode

# --- Helper Functions ---

# Only relevant in dev mode
async def attempt_manual_login(username: str, email: str, password: str) -> bool:
    """
    (Dev Mode Only) Attempts to log in using provided credentials and updates the global client.
    Returns True on success, False on failure.
    Stores error message in global login_error_message.
    """
    global twikit_client, login_error_message
    if ENV_TYPE != 'dev':
        logger.warning("attempt_manual_login called in non-dev mode. Ignoring.")
        return False

    logger.info(f"Attempting manual login for user: {username} (Dev Mode)")
    login_error_message = None # Reset error message
    COOKIES_FILE = 'cookies.json'
    try:
        temp_client = Client('en-US')
        await temp_client.login(
            auth_info_1=username,
            auth_info_2=email,
            password=password,
            cookies_file=COOKIES_FILE # Use the same cookies file
        )
        user_data = await temp_client.user()
        if user_data and hasattr(user_data, 'screen_name'):
            temp_client._logged_in_user = user_data
            twikit_client = temp_client # Update global client
            logger.info(f"Manual login successful for @{user_data.screen_name}! (Dev Mode)")
            return True
        else:
            logger.error("Manual login seemed successful, but failed to retrieve user data. (Dev Mode)")
            login_error_message = "Login succeeded but could not verify user data."
            twikit_client = None
            return False
    except EOFError as e:
        error_msg = f"Manual login failed: {e}. Interactive input (OTP/Password) likely required and cannot be provided here. (Dev Mode)"
        logger.error(error_msg)
        login_error_message = error_msg
        twikit_client = None
        return False
    except Exception as e:
        # Log the actual exception type and message
        logger.error(f"Manual login failed (Caught Exception Type: {type(e).__name__}): {e} (Dev Mode)", exc_info=True)
        error_msg = f"Manual login failed ({type(e).__name__}). Check logs for details."
        login_error_message = error_msg # Store simplified message for UI
        twikit_client = None
        return False

async def initialize_twikit_client():
    """Initializes the global Twikit client based on ENV_TYPE."""
    global twikit_client, login_error_message
    twikit_client = None # Reset
    login_error_message = None # Reset

    logger.info(f"Initializing Twikit client in {ENV_TYPE} mode...")

    if ENV_TYPE == "prod":
        # --- Production Mode: Use TWITTER_COOKIES_JSON_STRING --- 
        cookies_json_string = os.environ.get('TWITTER_COOKIES_JSON_STRING')
        if not cookies_json_string:
            logger.error("[Prod Mode] TWITTER_COOKIES_JSON_STRING environment variable not set. Cannot initialize Twikit client.")
            return
        
        try:
            logger.info("[Prod Mode] Parsing cookies from TWITTER_COOKIES_JSON_STRING...")
            parsed_data = json.loads(cookies_json_string)
            
            # *** NEW: Check for list containing one dictionary ***
            if not (isinstance(parsed_data, list) and len(parsed_data) == 1 and isinstance(parsed_data[0], dict)):
                logger.error(f"[Prod Mode] Failed to load cookies: Expected JSON format '[{{cookie_name: value, ...}}]' in TWITTER_COOKIES_JSON_STRING, but structure is different.")
                return

            # Extract the dictionary containing the cookies
            cookies_dict = parsed_data[0]
            logger.info(f"[Prod Mode] Extracted {len(cookies_dict)} cookies from the dictionary.")

            if not cookies_dict:
                 logger.error("[Prod Mode] No cookies found in the parsed dictionary.")
                 return

            # *** NEW: Try initializing Client directly with cookies dict ***
            logger.info("[Prod Mode] Initializing Twikit Client with extracted cookies...")
            # Assuming Twikit Client constructor accepts a cookies argument
            client = Client('en-US', cookies=cookies_dict)
            
            # Remove the previous manual injection logic
            # logger.info("[Prod Mode] Injecting cookies into client session from list...")
            # ... (removed cookie jar access and iteration) ...

            logger.info("[Prod Mode] Verifying cookies by fetching user data...")
            # *** Add specific catch for NotFound during verification ***
            try:
                user_data = await client.user()
            except NotFound as e:
                 logger.error(f"[Prod Mode] Verification failed: twikit received 404 calling internal endpoint ({e}). This might indicate invalid cookies OR an API change in Twitter/X affecting twikit.")
                 # Set client to None and return, preventing assignment to global
                 client = None 
                 user_data = None # Ensure user_data is None
                 # We don't re-raise here, just log and prevent global assignment

            if user_data and hasattr(user_data, 'screen_name'):
                client._logged_in_user = user_data
                twikit_client = client # Assign to global on success
                logger.info(f"[Prod Mode] Twikit client initialization successful using cookies string. Logged in as @{user_data.screen_name}!")
            elif client is not None: # Only log error if NotFound wasn't the issue
                logger.error("[Prod Mode] Cookies were loaded, but failed to retrieve valid user data. Cookies might be invalid or expired.")
            # If client is None (due to NotFound), the failure is already logged.

        except json.JSONDecodeError as e:
             logger.error(f"[Prod Mode] Failed to parse TWITTER_COOKIES_JSON_STRING: Invalid JSON. Error: {e}")
        except Exception as e: # General catch for other prod init errors (like Client init itself)
            logger.error(f"[Prod Mode] Failed to initialize/verify with cookies string (Caught Exception Type: {type(e).__name__}): {e}", exc_info=True)

    else:
        # --- Development Mode: Use Credentials & Cookies File --- 
        USERNAME = os.environ.get('TWITTER_USERNAME')
        EMAIL = os.environ.get('TWITTER_EMAIL')
        PASSWORD = os.environ.get('TWITTER_PASSWORD')
        COOKIES_FILE = 'cookies.json'

        if not all([USERNAME, EMAIL, PASSWORD]):
            logger.error("[Dev Mode] TWITTER_USERNAME, EMAIL, or PASSWORD not found in .env. Automatic login skipped.")
            login_error_message = "Dev Mode: Credentials not found in .env for automatic login."
            return
        try:
            logger.info("[Dev Mode] Attempting login with credentials/cookies...")
            client = Client('en-US')
            await client.login(
                auth_info_1=USERNAME,
                auth_info_2=EMAIL,
                password=PASSWORD,
                cookies_file=COOKIES_FILE
            )
            user_data = await client.user()
            if user_data and hasattr(user_data, 'screen_name'):
                client._logged_in_user = user_data
                twikit_client = client
                logger.info(f"[Dev Mode] Automatic login successful. Logged in as @{user_data.screen_name}!")
            else:
                 logger.warning("[Dev Mode] Automatic login seemed successful, but failed to retrieve user data.")
                 login_error_message = "Dev Mode: Automatic login succeeded but could not verify user data."
        except EOFError as e:
            err_msg = f"[Dev Mode] Automatic login failed: {e}. Interactive input required."
            logger.error(err_msg, exc_info=False)
            logger.info("[Dev Mode] Server starting without logged-in client. Manual login via /login-admin may be required.")
            login_error_message = err_msg
        except Exception as e: # General catch for dev init
            # Log the actual exception type and message
            logger.error(f"[Dev Mode] Automatic login failed (Caught Exception Type: {type(e).__name__}): {e}", exc_info=True)
            err_msg = f"Dev Mode: Automatic login failed ({type(e).__name__}). Check logs."
            logger.info("[Dev Mode] Server starting without logged-in client. Manual login via /login-admin may be required.")
            login_error_message = err_msg # Store simplified message for UI
            twikit_client = None

# --- Dependency Function ---
async def get_twikit_client():
    """
    Dependency function to get the initialized Twikit client.
    Raises HTTPException if the client is not available.
    """
    global twikit_client
    if twikit_client and twikit_client._logged_in_user:
        return twikit_client
    else:
        logger.warning(f"Access denied to protected endpoint: Twikit client not available (Mode: {ENV_TYPE}).")
        if ENV_TYPE == 'dev':
            detail_msg = "Twikit client not available or not logged in. Try logging in via /login-admin."
        else:
            detail_msg = "Twikit client not available. Check server logs and ensure TWITTER_AUTH_TOKEN is set correctly for prod mode."
        raise HTTPException(status_code=503, detail=detail_msg)

# Function to get user ID (can now use the dependency)
async def get_user_id_from_input(user_identifier: str, client: Client = Depends(get_twikit_client)) -> Optional[str]:
    """Gets user ID from screen name or returns ID if input is numeric."""
    # No need to check twikit_client here, Depends handles it.
    if user_identifier.isdigit():
        return user_identifier
    else:
        try:
            screen_name = user_identifier.lstrip('@')
            # logger.info(f"Looking up user ID for screen name: @{screen_name}") # Less verbose logging
            user_info = await client.get_user_by_screen_name(screen_name)
            if user_info and hasattr(user_info, 'id'):
                # logger.info(f"Found User ID: {user_info.id}")
                return user_info.id
            else:
                logger.warning(f"Could not find user or retrieve ID for screen name: @{screen_name}")
                return None
        except Exception as e:
            # Don't log full trace if it's likely a 404 or auth issue handled by dependency
            log_trace = not isinstance(e, (HTTPException, TwikitError))
            logger.error(f"Error looking up user @{screen_name}: {e}", exc_info=log_trace)
            return None

# --- FastAPI Lifecycle (Startup/Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("FastAPI application startup...")
    await initialize_twikit_client()
    yield
    # Shutdown
    logger.info("FastAPI application shutdown.")
    # No explicit twikit client close needed based on previous findings

# --- FastAPI App ---
app = FastAPI(
    title="Twikit Scraper API",
    description=f"An API to interact with Twitter using Twikit. Mode: {ENV_TYPE}.",
    version="0.1.2", # Incremented version
    lifespan=lifespan
)

# --- Pydantic Models (for Request/Response Validation & OpenAPI Docs) ---
# Basic structure, can be expanded based on actual twikit object fields
class TweetUser(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    screen_name: Optional[str] = None

class TweetData(BaseModel):
    id: Optional[str] = None
    text: Optional[str] = None
    created_at: Optional[str] = None
    user: Optional[TweetUser] = None
    tweet_url: Optional[str] = None # Added tweet URL
    media_urls: List[str] = [] # Added list for media URLs (defaults to empty)
    # Add other relevant fields from twikit Tweet object as needed

class TrendData(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    tweet_volume: Optional[int] = None

class CreateTweetRequest(BaseModel):
    text: str = Field(..., min_length=1, description="The text content of the tweet.")
    # Add media_ids: Optional[List[str]] = None if implementing media uploads

class CreateTweetResponse(BaseModel):
    tweet_id: str
    tweet_url: str

# Response model for the user ID endpoint
class UserIdResponse(BaseModel):
    screen_name: str
    user_id: str

# --- API Endpoints ---

@app.get("/health", tags=["General"])
async def health_check():
    """Simple health check endpoint."""
    # This endpoint can be expanded later to check database connections, etc.
    return {"status": "healthy"}

@app.get("/", include_in_schema=False)
async def root():
    """Redirects to the API documentation."""
    return RedirectResponse(url="/docs")

@app.get("/status", tags=["General"])
async def get_status():
    """Checks the status of the API and Twikit client initialization/login."""
    global twikit_client, login_error_message
    status_info = {"env_mode": ENV_TYPE}
    if twikit_client and twikit_client._logged_in_user:
         screen_name = getattr(twikit_client._logged_in_user, 'screen_name', 'Unknown')
         status_info.update({"status": "OK", "twikit_ready": True, "logged_in_user": screen_name})
    else:
         status_info.update({"status": "Error", "twikit_ready": False, "logged_in_user": None})
         if ENV_TYPE == 'dev':
             status_info["last_error"] = login_error_message or "Client not initialized or login failed."
         else:
             status_info["detail"] = "Client not initialized. Check TWITTER_AUTH_TOKEN."
    return status_info

@app.get("/search/tweets", response_model=List[TweetData], tags=["Search & Retrieve"])
async def search_tweets(
    query: str = Query(..., description="The search query string."),
    search_type: str = Query("Latest", enum=["Latest", "Top", "Media"], description="Type of search results."),
    count: int = Query(20, ge=1, le=100, description="Number of tweets to retrieve."),
    start_date: Optional[str] = Query(None, description="Start date for filtering (YYYY-MM-DD)", regex="^\\d{4}-\\d{2}-\\d{2}$"),
    end_date: Optional[str] = Query(None, description="End date for filtering (YYYY-MM-DD)", regex="^\\d{4}-\\d{2}-\\d{2}$"),
    client: Client = Depends(get_twikit_client) # Use dependency
):
    """Searches for tweets based on a query, optionally filtering by date."""
    # --- Parse dates ---
    start_date_obj: Optional[date] = None
    end_date_obj: Optional[date] = None
    try:
        if start_date:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        if end_date:
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Please use YYYY-MM-DD.")

    # Ensure start_date is not after end_date if both are provided
    if start_date_obj and end_date_obj and start_date_obj > end_date_obj:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date.")

    # Remove: if not twikit_client: ... (dependency handles this)
    try:
        search_info = f"'{search_type}' tweets matching '{query}' (count={count})"
        if start_date_obj or end_date_obj:
            date_range = f"from {start_date or 'beginning'} to {end_date or 'end'}"
            search_info += f" filtered {date_range}"
        logger.info(f"Searching for {search_info}...")

        tweets_result = await client.search_tweet(query, search_type, count=count)

        response_data = []
        filtered_count = 0
        for tweet in tweets_result:
            tweet_created_at_str = getattr(tweet, 'created_at', None)
            if not tweet_created_at_str:
                continue # Skip if no date

            try:
                # Parse the Twitter date string (e.g., "Mon Apr 21 21:53:41 +0000 2025")
                # Ensure the object from twikit is datetime, if not, parse string
                if isinstance(tweet_created_at_str, datetime):
                    tweet_dt = tweet_created_at_str
                else:
                    tweet_dt = datetime.strptime(str(tweet_created_at_str), "%a %b %d %H:%M:%S %z %Y")
                tweet_date = tweet_dt.date()
            except (ValueError, TypeError) as parse_error:
                logger.warning(f"Could not parse tweet created_at '{tweet_created_at_str}': {parse_error}. Skipping tweet ID {getattr(tweet, 'id', 'N/A')}")
                continue # Skip tweet if date is unparseable

            # Apply date filtering
            if start_date_obj and tweet_date < start_date_obj:
                filtered_count += 1
                continue # Skip tweet if before start date
            if end_date_obj and tweet_date > end_date_obj:
                filtered_count += 1
                continue # Skip tweet if after end date

            # Map to Pydantic model if within date range
            user_data = getattr(tweet, 'user', None)
            tweet_id = getattr(tweet, 'id', None)
            screen_name = getattr(user_data, 'screen_name', None) if user_data else None

            # Construct tweet URL
            tweet_url = None
            if tweet_id and screen_name:
                tweet_url = f"https://twitter.com/{screen_name}/status/{tweet_id}"

            # Extract media URLs with specific logic for type
            media_urls = []
            # Try extended_entities first, then media, default to empty list
            media_list = []
            extended_entities = getattr(tweet, 'extended_entities', None)
            if extended_entities and isinstance(extended_entities, dict):
                media_list = extended_entities.get('media', [])
            if not media_list: # Fallback to primary media attribute if extended not found
                media_list = getattr(tweet, 'media', [])
            
            if isinstance(media_list, list):
                for media_item in media_list:
                    media_type = getattr(media_item, 'type', None)
                    
                    if media_type in ['photo', 'animated_gif']:
                        url = getattr(media_item, 'media_url_https', None)
                        if url and isinstance(url, str):
                            media_urls.append(url)
                            
                    elif media_type == 'video':
                        video_info = getattr(media_item, 'video_info', None)
                        if video_info and isinstance(video_info, dict):
                            variants = video_info.get('variants', [])
                            if isinstance(variants, list):
                                best_url = None
                                max_bitrate = -1
                                for variant in variants:
                                    if isinstance(variant, dict) and variant.get('content_type') == 'video/mp4':
                                        bitrate = variant.get('bitrate', 0)
                                        variant_url = variant.get('url')
                                        try:
                                            current_bitrate = int(bitrate)
                                        except (ValueError, TypeError):
                                            current_bitrate = 0
                                            
                                        if variant_url and current_bitrate >= max_bitrate:
                                            max_bitrate = current_bitrate
                                            best_url = variant_url
                                            
                                if best_url and isinstance(best_url, str):
                                    media_urls.append(best_url)
                                # Optionally add fallback for non-mp4 video? (Currently disabled)
                                # elif variants: ... 

            response_data.append(TweetData(
                id=tweet_id,
                text=getattr(tweet, 'text', None),
                created_at=str(tweet_created_at_str),
                user=TweetUser(
                    id=getattr(user_data, 'id', None),
                    name=getattr(user_data, 'name', None),
                    screen_name=screen_name
                ) if user_data else None,
                tweet_url=tweet_url, # Assign constructed URL
                media_urls=media_urls # Assign extracted media URLs
            ))

        logger.info(f"Found {len(response_data)} tweets matching criteria ({filtered_count} tweets filtered out by date).")
        return response_data
    except Exception as e:
        logger.error(f"Error during tweet search: {e}", exc_info=True)
        if isinstance(e, HTTPException):
             raise e # Re-raise HTTP exceptions (like 503 from dependency)
        # Assume other errors are internal server errors
        raise HTTPException(status_code=500, detail=f"Internal server error during tweet search: {str(e)}")

@app.get("/users/{user_identifier}/tweets", response_model=List[TweetData], tags=["Search & Retrieve"])
async def get_user_tweets(
    user_identifier: str = Path(..., description="Twitter User ID or Screen Name (without @)."),
    tweet_type: str = Query("Tweets", enum=["Tweets", "TweetsAndReplies", "Media"], description="Type of tweets to retrieve."),
    count: int = Query(20, ge=1, le=100, description="Number of tweets to retrieve."),
    client: Client = Depends(get_twikit_client) # Use dependency
):
    """Retrieves tweets for a specific user."""
    user_id = await get_user_id_from_input(user_identifier, client=client)
    if not user_id:
        raise HTTPException(status_code=404, detail=f"Could not resolve User ID for identifier: {user_identifier}")

    logger.info(f"Attempting to fetch '{tweet_type}' for resolved user ID {user_id} (count={count})...") # Added log

    try:
        # --- Log the call ---
        logger.debug(f"Calling client.get_user_tweets(user_id='{user_id}', tweet_type='{tweet_type}', count={count})")

        result = await client.get_user_tweets(user_id, tweet_type, count=count) # Use injected client

        # --- Log the raw result ---
        logger.debug(f"Raw result from client.get_user_tweets: Type={type(result)}, Value={result}")
        # --- ADDED: Log attributes of the Result object if it's a Result ---
        if isinstance(result, object) and type(result).__name__ == 'Result': # Check if it's likely a twikit Result
            try:
                logger.debug(f"Attributes of Result object: {result.__dict__}")
            except AttributeError:
                logger.debug(f"dir(Result object): {dir(result)}") # Fallback if __dict__ is not standard

        # --- Process the result, assuming it's iterable ---
        # The twikit.utils.Result object is likely directly iterable.
        # We don't need to check for .data or list type explicitly here anymore.
        # If result is None or empty, the loop below will simply not run.
        tweets_iterable = result if result is not None else []
        logger.debug(f"Processing result of type {type(tweets_iterable)}. Assuming iterable.")

        response_data = []
        # Log count *before* iterating, requires converting iterator to list if we need count first.
        # Instead, we log *after* processing.
        # logger.debug(f"Processing items found in tweets_iterable...") # Adjusted log
        processed_count = 0
        try:
            for i, tweet in enumerate(tweets_iterable):
                # logger.debug(f"Processing item {i}: Type={type(tweet)}") # Log inside loop
                user_data = getattr(tweet, 'user', None)
                tweet_id = getattr(tweet, 'id', None)
                screen_name = getattr(user_data, 'screen_name', None) if user_data else None
                tweet_created_at_str = getattr(tweet, 'created_at', None)

                # Construct tweet URL
                tweet_url = None
                if tweet_id and screen_name:
                    tweet_url = f"https://twitter.com/{screen_name}/status/{tweet_id}"

                # Extract media URLs with specific logic for type
                media_urls = []
                # Try extended_entities first, then media, default to empty list
                media_list = []
                extended_entities = getattr(tweet, 'extended_entities', None)
                if extended_entities and isinstance(extended_entities, dict):
                    media_list = extended_entities.get('media', [])
                if not media_list: # Fallback to primary media attribute if extended not found
                    media_list = getattr(tweet, 'media', [])

                if isinstance(media_list, list):
                    for media_item in media_list:
                        media_type = getattr(media_item, 'type', None)
                        
                        if media_type in ['photo', 'animated_gif']:
                            url = getattr(media_item, 'media_url_https', None)
                            if url and isinstance(url, str):
                                media_urls.append(url)
                                
                        elif media_type == 'video':
                            video_info = getattr(media_item, 'video_info', None)
                            if video_info and isinstance(video_info, dict):
                                variants = video_info.get('variants', [])
                                if isinstance(variants, list):
                                    best_url = None
                                    max_bitrate = -1
                                    for variant in variants:
                                        if isinstance(variant, dict) and variant.get('content_type') == 'video/mp4':
                                            bitrate = variant.get('bitrate', 0)
                                            variant_url = variant.get('url')
                                            try:
                                                current_bitrate = int(bitrate)
                                            except (ValueError, TypeError):
                                                current_bitrate = 0
                                                
                                            if variant_url and current_bitrate >= max_bitrate:
                                                max_bitrate = current_bitrate
                                                best_url = variant_url
                                                
                                    if best_url and isinstance(best_url, str):
                                        media_urls.append(best_url)
                                    # Optionally add fallback for non-mp4 video? (Currently disabled)
                                    # elif variants: ... 

                try:
                    mapped_tweet = TweetData(
                        id=tweet_id,
                        text=getattr(tweet, 'text', None),
                        created_at=str(tweet_created_at_str),
                        user=TweetUser(
                            id=getattr(user_data, 'id', None),
                            name=getattr(user_data, 'name', None),
                            screen_name=screen_name
                        ) if user_data else None,
                        tweet_url=tweet_url, # Assign constructed URL
                        media_urls=media_urls # Assign extracted media URLs
                    )
                    response_data.append(mapped_tweet)
                    processed_count += 1
                    # logger.debug(f"Successfully mapped item {i} to TweetData")
                except Exception as mapping_error:
                    logger.error(f"Error mapping tweet item {i} to TweetData: {mapping_error}", exc_info=True)
                    # Decide whether to skip this tweet or raise an error
            logger.info(f"Finished processing. Returning {processed_count} mapped tweets for user ID {user_id}.") # Updated log
        except TypeError as te:
             # This catches cases where tweets_iterable is unexpectedly not iterable
             logger.error(f"Result object of type {type(result)} was not iterable as expected: {te}", exc_info=True)
             # Keep response_data empty as it failed to iterate
             logger.info(f"Finished processing due to iteration error. Returning {len(response_data)} mapped tweets for user ID {user_id}.")

        return response_data
    except Exception as e:
        # Log the actual exception type
        logger.error(f"Error during get_user_tweets for ID {user_id} (Caught Exception Type: {type(e).__name__}): {e}", exc_info=True)
        if isinstance(e, HTTPException):
             raise e # Re-raise HTTP exceptions (like 503 from dependency)
        # Check if it looks like a rate limit error based on message (heuristic)
        if "rate limit" in str(e).lower() or "429" in str(e):
             raise HTTPException(status_code=429, detail=f"Rate limit likely exceeded. Details: {str(e)}")
        # General internal server error for others
        raise HTTPException(status_code=500, detail=f"Internal server error fetching user tweets: {str(e)}")

@app.get("/trends", response_model=List[TrendData], tags=["Search & Retrieve"])
async def get_trends(
    trend_type: str = Query("trending", description="Type of trends (e.g., 'trending' or WOEID for specific location)."),
    client: Client = Depends(get_twikit_client) # Use dependency
):
    """Retrieves trending topics."""
    # Remove: if not twikit_client: ... (dependency handles this)
    try:
        logger.info(f"Fetching trends for type: {trend_type}...")
        logger.debug(f"Calling client.get_trends(trend_type='{trend_type}')") # Add log
        result = await client.get_trends(trend_type) # Use injected client
        logger.debug(f"Raw result from client.get_trends: Type={type(result)}, Value={result}") # Add log

        # Adjust extraction based on logged result type if needed
        if hasattr(result, 'data') and isinstance(getattr(result, 'data', None), list):
            trends_data = result.data
            logger.debug(f"Extracted trends_data from result.data (Count: {len(trends_data)})")
        elif isinstance(result, list):
            trends_data = result
            logger.debug(f"Result is already a list (Count: {len(trends_data)})")
        else:
            trends_data = []
            logger.warning(f"Unexpected result type from get_trends. Expected list or object with .data attribute. Got: {type(result)}")

        # Map to Pydantic model
        logger.debug(f"Mapping {len(trends_data)} items found in trends_data...")
        response_data = [TrendData(**trend.__dict__) for trend in trends_data]
        logger.info(f"Finished processing. Returning {len(response_data)} mapped trends.")
        return response_data
    except Exception as e:
        logger.error(f"Error fetching trends: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error fetching trends: {e}")

@app.post("/tweets", response_model=CreateTweetResponse, tags=["Actions"], status_code=201)
async def create_tweet(
    tweet_request: CreateTweetRequest = Body(...),
    client: Client = Depends(get_twikit_client) # Use dependency
):
    """Creates a new tweet."""
    # Remove: if not twikit_client or not twikit_client._logged_in_user: ... (dependency handles this)

    try:
        logger.info(f"Attempting to post tweet: {tweet_request.text[:50]}...")
        created_tweet = await client.create_tweet(text=tweet_request.text) # Use injected client

        # Use client._logged_in_user if needed (dependency ensures it exists if client is valid)
        screen_name = getattr(client._logged_in_user, 'screen_name', 'unknown')
        tweet_id = getattr(created_tweet, 'id', 'unknown')
        tweet_url = f"https://twitter.com/{screen_name}/status/{tweet_id}"

        logger.info(f"Tweet posted successfully: ID {tweet_id}")
        return CreateTweetResponse(tweet_id=tweet_id, tweet_url=tweet_url)

    except Exception as e:
        logger.error(f"Failed to post tweet: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error posting tweet: {e}")

# --- FIX THIS ENDPOINT ---
@app.get("/users/id/{screen_name}", response_model=UserIdResponse, tags=["Users"]) # Added tag
async def get_user_id_by_screen_name(
    screen_name: str = Path(..., description="Twitter Screen Name (without @)."), # Use Path
    client: Client = Depends(get_twikit_client) # Use the CORRECT dependency
):
    """
    Retrieves the Twitter User ID for a given screen name.
    """
    # Remove: if not twikit_client: ... (dependency handles this)
    try:
        # Use the injected client directly
        logger.info(f"Looking up user ID for screen name: @{screen_name}")
        user = await client.get_user_by_screen_name(screen_name)
        if user and hasattr(user, 'id'):
            logger.info(f"Found User ID: {user.id} for @{screen_name}")
            return UserIdResponse(screen_name=screen_name, user_id=user.id)
        else:
            logger.warning(f"Twikit returned no user or user has no ID for @{screen_name}")
            raise HTTPException(status_code=404, detail=f"User with screen name '{screen_name}' not found.")
    except HTTPException as http_exc:
         # Re-raise HTTPExceptions (like 404 from above)
         raise http_exc
    except Exception as e:
        logger.error(f"Error fetching user ID for @{screen_name}: {e}", exc_info=True)
        # Improve error message based on potential twikit exception types if known
        raise HTTPException(status_code=404, detail=f"Could not retrieve user ID for '{screen_name}'. Reason: {e}")

# --- Dev Mode Only: Login Admin UI Endpoint ---
@app.get("/login-admin", response_class=HTMLResponse, tags=["Admin"], include_in_schema=(ENV_TYPE == 'dev'))
async def login_admin_ui(request: Request):
    """(Dev Mode Only) Serves the HTML page for manual login."""
    if ENV_TYPE != 'dev':
        raise HTTPException(status_code=404, detail="Login admin UI is only available in dev mode.")
    if not templates:
         raise HTTPException(status_code=500, detail="Templates not initialized for dev mode.")

    global twikit_client, login_error_message
    logged_in = False
    username = None
    if twikit_client and twikit_client._logged_in_user:
        logged_in = True
        username = getattr(twikit_client._logged_in_user, 'screen_name', 'Unknown')

    env_username = os.environ.get('TWITTER_USERNAME', '')
    env_email = os.environ.get('TWITTER_EMAIL', '')

    return templates.TemplateResponse("login.html", {
        "request": request,
        "logged_in": logged_in,
        "username": username,
        "last_error": login_error_message,
        "env_username": env_username,
        "env_email": env_email
    })

# --- Dev Mode Only: Re-Login Endpoint ---
@app.post("/relogin", tags=["Admin"], status_code=303, include_in_schema=(ENV_TYPE == 'dev'))
async def relogin(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    """(Dev Mode Only) Attempts to manually log in the global Twikit client."""
    if ENV_TYPE != 'dev':
         raise HTTPException(status_code=404, detail="Relogin functionality is only available in dev mode.")

    global twikit_client, login_error_message
    if twikit_client and twikit_client._logged_in_user:
        logger.warning("Relogin attempt rejected: Client already logged in. (Dev Mode)")
        return RedirectResponse("/login-admin?message=Already+logged+in", status_code=303)

    success = await attempt_manual_login(username, email, password)

    if success:
        logger.info("Manual relogin successful, redirecting. (Dev Mode)")
        login_error_message = None # Clear error on success
        return RedirectResponse("/login-admin?message=Login+Successful", status_code=303)
    else:
        logger.error(f"Manual relogin failed. Error: {login_error_message} (Dev Mode)")
        error_param = urllib.parse.quote(login_error_message or 'Login failed, check logs.')
        return RedirectResponse(f"/login-admin?error={error_param}", status_code=303)

# --- Uvicorn Runner (Conditional Template Creation) ---
if __name__ == "__main__":
    import uvicorn

    # Only create templates in dev mode
    if ENV_TYPE == 'dev':
        if not os.path.exists("templates"):
            os.makedirs("templates")
            logger.info("Created 'templates' directory for dev mode.")

        login_html_path = os.path.join("templates", "login.html")
        if not os.path.exists(login_html_path):
            logger.info(f"Creating basic '{login_html_path}' file for dev mode.")
            # (Use the same basic_html content from previous step)
            basic_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Twikit Login Admin</title>
    <style>
        body { font-family: sans-serif; padding: 20px; line-height: 1.6; }
        .container { max-width: 600px; margin: auto; }
        .message { border: 1px solid; padding: 10px; margin-bottom: 15px; border-radius: 4px; }
        .error { color: #721c24; background-color: #f8d7da; border-color: #f5c6cb; }
        .success { color: #155724; background-color: #d4edda; border-color: #c3e6cb; }
        .status { border: 1px solid #ccc; padding: 10px; margin-bottom: 15px; background-color: #f9f9f9; border-radius: 4px;}
        .status strong { display: inline-block; min-width: 60px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type=text], input[type=password], input[type=email] {
            width: calc(100% - 18px); /* Adjust for padding */
            padding: 8px;
            margin-bottom: 10px;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
        button { padding: 10px 15px; cursor: pointer; background-color: #007bff; color: white; border: none; border-radius: 4px; font-size: 1em; }
        button:hover { background-color: #0056b3; }
        h1, h2 { border-bottom: 1px solid #eee; padding-bottom: 5px; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Twikit API Login Status</h1>

        <div class="status">
            <strong>Mode:</strong> {{ env_mode }} <br>
            <strong>Status:</strong>
            {% if logged_in %}
                <span style="color: green; font-weight: bold;">Logged In</span> as <strong>@{{ username }}</strong>
            {% else %}
                <span style="color: red; font-weight: bold;">Not Logged In</span>
            {% endif %}
        </div>

        {# Display feedback messages from redirects or persistent errors #}
        {% set error_msg = request.query_params.get('error') %}
        {% set success_msg = request.query_params.get('message') %}
        {% if error_msg %}
            <div class="message error">Login Failed: {{ error_msg }}</div>
        {% elif success_msg %}
             <div class="message success">{{ success_msg }}</div>
        {% elif last_error %}
             <div class="message error">Last Login Attempt Error: {{ last_error }}</div>
        {% endif %}


        {% if not logged_in %}
            <h2>Manual Login</h2>
            <p>If automatic login failed (check server logs), enter credentials below and click Login.</p>
            <form action="/relogin" method="post">
                <div>
                    <label for="username">Username:</label>
                    <input type="text" id="username" name="username" value="{{ env_username }}" required>
                </div>
                <div>
                    <label for="email">Email:</label>
                    <input type="email" id="email" name="email" value="{{ env_email }}" required>
                </div>
                <div>
                    <label for="password">Password:</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit">Login</button>
            </form>
        {% endif %}
    </div>
</body>
</html>
            """
            with open(login_html_path, "w", encoding='utf-8') as f:
                f.write(basic_html)

    logger.info("Starting Uvicorn server directly...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info") 