import asyncio
import os
from dotenv import load_dotenv
from twikit import Client
import logging

# Configure logging similar to your app
logging.basicConfig(level=logging.DEBUG) # Use DEBUG for more detail
logger = logging.getLogger(__name__)

load_dotenv() # Load .env file from the same directory

USERNAME = os.environ.get('TWITTER_USERNAME')
EMAIL = os.environ.get('TWITTER_EMAIL')
PASSWORD = os.environ.get('TWITTER_PASSWORD')
COOKIES_FILE = 'cookies.json' # Use the same cookies file

async def main():
    if not all([USERNAME, EMAIL, PASSWORD]):
        logger.error("Credentials not found in .env file.")
        return

    client = Client('en-US')
    logger.info("Attempting login...")
    try:
        # Use the same cookies file to test session persistence if it exists
        # Or test fresh login by ensuring cookies.json is deleted first
        await client.login(
            auth_info_1=USERNAME,
            auth_info_2=EMAIL,
            password=PASSWORD,
            cookies_file=COOKIES_FILE
        )
        logger.info("Login successful according to twikit.")

        # Test fetching user data again post-login
        try:
            user_info = await client.user()
            logger.info(f"client.user() successful. Screen name: {user_info.screen_name}")
        except Exception as e:
            logger.error(f"Failed to get user info AFTER login: {e}", exc_info=True)
            # Proceed to try other calls anyway, but this is a bad sign

        # --- Test Get User Tweets ---
        test_user_id = "2244994945" # Example: TwitterDev User ID
        logger.info(f"Attempting to fetch tweets for user ID: {test_user_id}")
        try:
            tweets_result = await client.get_user_tweets(test_user_id, 'Tweets', count=5)
            logger.info(f"Result from get_user_tweets: Type={type(tweets_result)}, Value={tweets_result}")
            # Check result structure
            if hasattr(tweets_result, 'data'):
                logger.info(f"Tweet count from result.data: {len(tweets_result.data)}")
            elif isinstance(tweets_result, list):
                 logger.info(f"Tweet count from list result: {len(tweets_result)}")

        except Exception as e:
            logger.error(f"Error calling get_user_tweets: {e}", exc_info=True)

        # --- Test Get Trends ---
        logger.info("Attempting to fetch trends...")
        try:
            trends_result = await client.get_trends('trending')
            logger.info(f"Result from get_trends: Type={type(trends_result)}, Value={trends_result}")
             # Check result structure
            if hasattr(trends_result, 'data'):
                logger.info(f"Trend count from result.data: {len(trends_result.data)}")
            elif isinstance(trends_result, list):
                 logger.info(f"Trend count from list result: {len(trends_result)}")
        except Exception as e:
            logger.error(f"Error calling get_trends: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Login failed: {e}", exc_info=True)
    finally:
        # No close method observed needed, but good practice if it existed
        pass # await client.close() if available

if __name__ == "__main__":
    # Optionally delete cookies.json before running for a clean test
    # try:
    #     os.remove(COOKIES_FILE)
    #     logger.info(f"Deleted {COOKIES_FILE} for fresh login test.")
    # except OSError:
    #     pass # Ignore if it doesn't exist

    asyncio.run(main()) 