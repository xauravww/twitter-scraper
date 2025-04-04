import asyncio
import os
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Union

from fastapi import FastAPI, HTTPException, Query, Path, Body
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

async def get_user_id_from_input(user_identifier: str) -> Optional[str]:
    """Gets user ID from screen name or returns ID if input is numeric."""
    if not twikit_client:
        raise HTTPException(status_code=503, detail="Twikit client not available or not logged in.")

    if user_identifier.isdigit():
        return user_identifier
    else:
        try:
            screen_name = user_identifier.lstrip('@')
            logger.info(f"Looking up user ID for screen name: @{screen_name}")
            user_info = await twikit_client.get_user_by_screen_name(screen_name)
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

# --- API Endpoints ---

@app.get("/", include_in_schema=False)
async def root():
    """Redirects to the API documentation."""
    return RedirectResponse(url="/docs")

@app.get("/status", tags=["General"])
async def get_status():
    """Checks the status of the API and Twikit client login."""
    if twikit_client and twikit_client._logged_in_user:
        return {"status": "OK", "logged_in_user": twikit_client._logged_in_user.screen_name}
    elif twikit_client:
        return {"status": "OK", "logged_in_user": "Login incomplete"}
    else:
        return {"status": "Error", "logged_in_user": "Client not initialized or login failed"}

@app.get("/search/tweets", response_model=List[TweetData], tags=["Search & Retrieve"])
async def search_tweets(
    query: str = Query(..., description="The search query string."),
    search_type: str = Query("Latest", enum=["Latest", "Top", "Media"], description="Type of search results."),
    count: int = Query(20, ge=1, le=100, description="Number of tweets to retrieve.")
):
    """Searches for tweets based on a query."""
    if not twikit_client:
        raise HTTPException(status_code=503, detail="Twikit client not available or not logged in.")
    try:
        logger.info(f"Searching for '{search_type}' tweets matching '{query}' (count={count})...")
        # Assuming search_tweet returns a list of Tweet objects directly
        tweets_result = await twikit_client.search_tweet(query, search_type, count=count)
        # Manually map results to Pydantic model if necessary, or rely on FastAPI if structure matches
        # For safety, let's assume manual mapping might be needed if fields differ slightly
        response_data = []
        for tweet in tweets_result:
             user_data = getattr(tweet, 'user', None)
             response_data.append(TweetData(
                 id=getattr(tweet, 'id', None),
                 text=getattr(tweet, 'text', None),
                 created_at=str(getattr(tweet, 'created_at', None)),
                 user=TweetUser(
                     id=getattr(user_data, 'id', None),
                     name=getattr(user_data, 'name', None),
                     screen_name=getattr(user_data, 'screen_name', None)
                 ) if user_data else None
             ))
        return response_data
    except Exception as e:
        logger.error(f"Error during tweet search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error during tweet search: {e}")

@app.get("/users/{user_identifier}/tweets", response_model=List[TweetData], tags=["Search & Retrieve"])
async def get_user_tweets(
    user_identifier: str = Path(..., description="Twitter User ID or Screen Name (without @)."),
    tweet_type: str = Query("Tweets", enum=["Tweets", "TweetsAndReplies", "Media"], description="Type of tweets to retrieve."),
    count: int = Query(20, ge=1, le=100, description="Number of tweets to retrieve.")
):
    """Retrieves tweets for a specific user."""
    if not twikit_client:
        raise HTTPException(status_code=503, detail="Twikit client not available or not logged in.")

    user_id = await get_user_id_from_input(user_identifier)
    if not user_id:
        raise HTTPException(status_code=404, detail=f"Could not resolve User ID for identifier: {user_identifier}")

    try:
        logger.info(f"Fetching '{tweet_type}' for user ID {user_id} (count={count})...")
        result = await twikit_client.get_user_tweets(user_id, tweet_type, count=count)
        tweets_data = getattr(result, 'data', []) # Access the data list from the Result object

        response_data = []
        for tweet in tweets_data:
             user_data = getattr(tweet, 'user', None)
             response_data.append(TweetData(
                 id=getattr(tweet, 'id', None),
                 text=getattr(tweet, 'text', None),
                 created_at=str(getattr(tweet, 'created_at', None)),
                 user=TweetUser(
                     id=getattr(user_data, 'id', None),
                     name=getattr(user_data, 'name', None),
                     screen_name=getattr(user_data, 'screen_name', None)
                 ) if user_data else None
             ))
        return response_data
    except Exception as e:
        logger.error(f"Error fetching user tweets for ID {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error fetching user tweets: {e}")


@app.get("/trends", response_model=List[TrendData], tags=["Search & Retrieve"])
async def get_trends(
    trend_type: str = Query("trending", description="Type of trends (e.g., 'trending' or WOEID for specific location).")
):
    """Retrieves trending topics."""
    if not twikit_client:
        raise HTTPException(status_code=503, detail="Twikit client not available or not logged in.")
    try:
        logger.info(f"Fetching trends for type: {trend_type}...")
        result = await twikit_client.get_trends(trend_type)
        trends_data = getattr(result, 'data', []) # Access the data list

        # Map to Pydantic model
        response_data = [TrendData(**trend.__dict__) for trend in trends_data]
        return response_data
    except Exception as e:
        logger.error(f"Error fetching trends: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error fetching trends: {e}")

@app.post("/tweets", response_model=CreateTweetResponse, tags=["Actions"], status_code=201)
async def create_tweet(
    tweet_request: CreateTweetRequest = Body(...)
):
    """Creates a new tweet."""
    if not twikit_client or not twikit_client._logged_in_user:
        raise HTTPException(status_code=503, detail="Twikit client not available or not logged in.")

    try:
        logger.info(f"Attempting to post tweet: {tweet_request.text[:50]}...")
        # Add media_ids=tweet_request.media_ids if implementing media uploads
        created_tweet = await twikit_client.create_tweet(text=tweet_request.text)

        screen_name = getattr(twikit_client._logged_in_user, 'screen_name', 'unknown')
        tweet_id = getattr(created_tweet, 'id', 'unknown')
        tweet_url = f"https://twitter.com/{screen_name}/status/{tweet_id}"

        logger.info(f"Tweet posted successfully: ID {tweet_id}")
        return CreateTweetResponse(tweet_id=tweet_id, tweet_url=tweet_url)

    except Exception as e:
        logger.error(f"Failed to post tweet: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error posting tweet: {e}")

# --- Uvicorn Runner (for direct execution) ---
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server directly...")
    # Make sure .env is in the root directory when running this way
    # Use reload=True only for development
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info") 