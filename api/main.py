import asyncio
import os
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Union
from datetime import datetime, date

from fastapi import FastAPI, HTTPException, Query, Path, Body, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from twikit import Client

# --- Configuration & Logging ---
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Global Twikit Client ---
# Will be initialized during startup
twikit_client: Optional[Client] = None

# --- Helper Functions ---
async def initialize_twikit_client():
    """Initializes and logs in the global Twikit client."""
    global twikit_client
    if twikit_client and twikit_client._logged_in_user:
        logger.info(f"Twikit client already logged in as @{twikit_client._logged_in_user.screen_name}")
        return

    USERNAME = os.environ.get('TWITTER_USERNAME')
    EMAIL = os.environ.get('TWITTER_EMAIL')
    PASSWORD = os.environ.get('TWITTER_PASSWORD')
    COOKIES_FILE = 'cookies.json' # Ensure this is writable/readable by the server process

    if not all([USERNAME, EMAIL, PASSWORD]):
        logger.error("TWITTER_USERNAME, TWITTER_EMAIL, or TWITTER_PASSWORD not found in .env")
        # Decide how to handle this: raise exception, run without auth, etc.
        # For now, we'll allow the app to start but endpoints requiring auth will fail.
        twikit_client = None
        return

    logger.info("Initializing and logging in Twikit client...")
    try:
        client = Client('en-US')
        await client.login(
            auth_info_1=USERNAME,
            auth_info_2=EMAIL,
            password=PASSWORD,
            cookies_file=COOKIES_FILE
        )
        user_data = await client.user()
        client._logged_in_user = user_data # Store user data
        twikit_client = client # Assign to global variable
        if twikit_client._logged_in_user:
            logger.info(f"Twikit client login successful as @{twikit_client._logged_in_user.screen_name}!")
        else:
            logger.warning("Twikit client login seemed successful, but user data retrieval failed.")
            twikit_client = None # Ensure client is None if login wasn't fully successful
    except Exception as e:
        logger.error(f"Twikit client login failed: {e}", exc_info=True)
        twikit_client = None # Ensure client is None on failure

# --- NEW Dependency Function ---
async def get_twikit_client():
    """
    Dependency function to get the initialized Twikit client.
    Raises HTTPException if the client is not available or logged in.
    """
    if twikit_client and twikit_client._logged_in_user:
        return twikit_client
    else:
        # Logged during initialize_twikit_client, just raise HTTP error here
        raise HTTPException(status_code=503, detail="Twikit client not available or not logged in.")

# Function to get user ID (can now use the dependency)
async def get_user_id_from_input(user_identifier: str, client: Client = Depends(get_twikit_client)) -> Optional[str]:
    """Gets user ID from screen name or returns ID if input is numeric."""
    # No need to check twikit_client here, Depends handles it.
    if user_identifier.isdigit():
        return user_identifier
    else:
        try:
            screen_name = user_identifier.lstrip('@')
            logger.info(f"Looking up user ID for screen name: @{screen_name}")
            user_info = await client.get_user_by_screen_name(screen_name) # Use injected client
            if user_info and hasattr(user_info, 'id'):
                logger.info(f"Found User ID: {user_info.id}")
                return user_info.id
            else:
                logger.warning(f"Could not find user or retrieve ID for screen name: @{screen_name}")
                return None
        except Exception as e:
            logger.error(f"Error looking up user @{screen_name}: {e}")
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
    description="An API to interact with Twitter using the Twikit library. Requires login credentials in a .env file.",
    version="0.1.0",
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
async def get_status(client: Optional[Client] = Depends(get_twikit_client)): # Use dependency, allow optional for status check
    """Checks the status of the API and Twikit client login."""
    # Logic remains similar but uses the potentially injected client
    if client and client._logged_in_user:
         return {"status": "OK", "logged_in_user": client._logged_in_user.screen_name}
    # Check global state if dependency failed (returned None implicitly before raising 503)
    elif twikit_client:
         return {"status": "OK", "logged_in_user": "Login incomplete"}
    else:
         return {"status": "Error", "logged_in_user": "Client not initialized or login failed"}

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
        logger.info(f"Searching for {search_info}...") # Updated log

        tweets_result = await client.search_tweet(query, search_type, count=count) # Use injected client

        # --- Filter and Map results --- # Updated section
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
            response_data.append(TweetData(
                id=getattr(tweet, 'id', None),
                text=getattr(tweet, 'text', None),
                created_at=str(tweet_created_at_str), # Keep original string format for response
                user=TweetUser(
                    id=getattr(user_data, 'id', None),
                    name=getattr(user_data, 'name', None),
                    screen_name=getattr(user_data, 'screen_name', None)
                ) if user_data else None
            ))

        logger.info(f"Found {len(response_data)} tweets matching criteria ({filtered_count} tweets filtered out by date)." ) # Updated log
        return response_data
    except Exception as e:
        logger.error(f"Error during tweet search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error during tweet search: {e}")

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
                try:
                    mapped_tweet = TweetData(
                        id=getattr(tweet, 'id', None),
                        text=getattr(tweet, 'text', None),
                        created_at=str(getattr(tweet, 'created_at', None)),
                        user=TweetUser(
                            id=getattr(user_data, 'id', None),
                            name=getattr(user_data, 'name', None),
                            screen_name=getattr(user_data, 'screen_name', None)
                        ) if user_data else None
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
    except twikit.errors.AccountSuspended as e:
        # Check if the suspension is due to a rate limit (status 429)
        if e.response and e.response.status_code == 429:
            logger.warning(f"Twitter API rate limit exceeded for user ID {user_id}: {e}")
            raise HTTPException(status_code=429, detail=f"Twitter API rate limit exceeded. Please try again later. Details: {e.message}")
        else:
            # If it's another AccountSuspended reason, treat as 500 or other appropriate error
            logger.error(f"Account suspended or other critical error for user ID {user_id}: {e}", exc_info=True)
            raise HTTPException(status_code=503, detail=f"Account issue encountered: {e.message}") # 503 Service Unavailable might be suitable
    except Exception as e:
        logger.error(f"Error during get_user_tweets execution for ID {user_id}: {e}", exc_info=True)
        # Avoid raising 500 if it's a known "not found" type error from twikit, if possible
        raise HTTPException(status_code=500, detail=f"Internal server error fetching user tweets: {e}")

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

# --- Uvicorn Runner (for direct execution) ---
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server directly...")
    # Make sure .env is in the root directory when running this way
    # Use reload=True only for development
    # Bind to 0.0.0.0 to make accessible on the network
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info") 