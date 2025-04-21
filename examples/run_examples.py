import asyncio
import os
from twikit import Client
from dotenv import load_dotenv # Import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
# It's highly recommended to use environment variables or a configuration file
# instead of hardcoding credentials directly in the script.
USERNAME = os.environ.get('TWITTER_USERNAME', 'your_username') # Replace 'your_username' or set env var
EMAIL = os.environ.get('TWITTER_EMAIL', 'your_email@example.com') # Replace 'your_email@example.com' or set env var
PASSWORD = os.environ.get('TWITTER_PASSWORD', 'your_password') # Replace 'your_password' or set env var
COOKIES_FILE = 'cookies.json' # File to store login session cookies

# --- Client Initialization ---
# Initialize client (e.g., 'en-US' for English)
client = Client('en-US')

async def login():
    """Logs into the Twitter account."""
    print("Attempting login...")
    if not all([USERNAME, EMAIL, PASSWORD]):
        print("Error: Please set TWITTER_USERNAME, TWITTER_EMAIL, and TWITTER_PASSWORD environment variables or update the script.")
        return False
    try:
        await client.login(
            auth_info_1=USERNAME,
            auth_info_2=EMAIL,
            password=PASSWORD,
            cookies_file=COOKIES_FILE
        )
        print("Login successful!")
        return True
    except Exception as e:
        print(f"Login failed: {e}")
        # Consider more specific error handling based on twikit exceptions
        return False

async def example_create_tweet_with_media():
    """Example: Creates a tweet with attached media."""
    print("\n--- Example: Create Tweet with Media ---")
    media_files = ['media1.jpg', 'media2.jpg'] # <<< Replace with actual paths to your media files

    try:
        # Check if media files exist (optional but good practice)
        existing_files = [f for f in media_files if os.path.exists(f)]
        if not existing_files:
            print(f"Media files not found: {media_files}. Skipping media upload.")
            media_ids = []
        else:
            print(f"Uploading media: {existing_files}...")
            media_ids = [await client.upload_media(filepath) for filepath in existing_files]
            print(f"Media uploaded successfully. Media IDs: {media_ids}")

        tweet_text = 'This is an example tweet sent via Twikit!'
        print(f"Creating tweet: '{tweet_text}' {'with media' if media_ids else 'without media'}...")
        tweet = await client.create_tweet(
            text=tweet_text,
            media_ids=media_ids # Pass empty list if no media
        )
        print(f"Tweet created successfully! Tweet ID: {tweet.id}")

    except Exception as e:
        print(f"Error creating tweet: {e}")

async def example_search_tweets():
    """Example: Searches for the latest tweets based on a keyword."""
    print("\n--- Example: Search Tweets ---")
    keyword = 'python programming'
    search_type = 'Latest' # Options: 'Latest', 'Top', etc.
    try:
        print(f"Searching for '{search_type}' tweets containing '{keyword}'...")
        tweets = await client.search_tweet(keyword, search_type)
        print(f"Found {len(tweets)} tweets.")
        for i, tweet in enumerate(tweets[:5]): # Print details of the first 5 tweets
            print(f"  Tweet {i+1}:")
            print(f"    User: {tweet.user.name} (@{tweet.user.screen_name})")
            print(f"    Text: {tweet.text[:100]}..." if len(tweet.text) > 100 else f"    Text: {tweet.text}")
            print(f"    Created at: {tweet.created_at}")
            print(f"    Link: https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}")
    except Exception as e:
        print(f"Error searching tweets: {e}")

async def example_get_user_tweets():
    """Example: Retrieves tweets from a specific user."""
    print("\n--- Example: Get User Tweets ---")
    user_id_to_fetch = '2244994945' # Example: TwitterDev User ID <<< Replace with a valid Twitter User ID
    tweet_type = 'Tweets' # Options: 'Tweets', 'TweetsAndReplies', 'Media'
    try:
        print(f"Fetching '{tweet_type}' for user ID {user_id_to_fetch}...")
        # Fetch tweets. Assuming it returns a Result object with a 'data' attribute list
        result = await client.get_user_tweets(user_id_to_fetch, tweet_type, count=20) # Fetch up to 20

        # Check if the result has data and iterate through it
        tweets = getattr(result, 'data', []) # Use getattr for safety

        # Limit to showing 5 tweets
        tweets_to_show = tweets[:5]

        print(f"Retrieved {len(tweets)} tweets (showing up to {len(tweets_to_show)}).")
        if not tweets_to_show:
            print("  No tweets found or result format unexpected.")
        for i, tweet in enumerate(tweets_to_show):
            # Safely access attributes that might be missing
            user_name = getattr(getattr(tweet, 'user', None), 'name', 'Unknown User')
            screen_name = getattr(getattr(tweet, 'user', None), 'screen_name', 'unknown')
            tweet_id = getattr(tweet, 'id', 'unknown_id')
            tweet_text = getattr(tweet, 'text', 'No text content')
            created_at = getattr(tweet, 'created_at', 'Unknown time')

            print(f"  Tweet {i+1}:")
            print(f"    User: {user_name} (@{screen_name})")
            print(f"    Text: {tweet_text[:100]}{'...' if len(tweet_text) > 100 else ''}")
            print(f"    Created at: {created_at}")
            print(f"    Link: https://twitter.com/{screen_name}/status/{tweet_id}")
    except Exception as e:
        print(f"Error getting user tweets: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging


async def example_send_dm():
    """Example: Sends a Direct Message (DM) to a user."""
    print("\n--- Example: Send DM ---")
    recipient_id = 'REPLACE_WITH_RECIPIENT_USER_ID' # <<< IMPORTANT: Replace with a valid Twitter User ID you can DM
    message_text = 'Hello from the Twikit example script!'

    if recipient_id == 'REPLACE_WITH_RECIPIENT_USER_ID':
        print("Skipping DM example. Please replace 'REPLACE_WITH_RECIPIENT_USER_ID' in the script.")
        return

    try:
        print(f"Sending DM to user ID {recipient_id}: '{message_text}'")
        await client.send_dm(recipient_id, message_text)
        print("DM sent successfully!")
    except Exception as e:
        print(f"Error sending DM: {e}")


async def example_get_trends():
    """Example: Retrieves trending topics."""
    print("\n--- Example: Get Trends ---")
    trend_type = 'trending' # Or specify WOEID for location-specific trends
    try:
        print(f"Fetching trends ({trend_type})...")
        # Assuming get_trends returns a Result object with a 'data' attribute list
        result = await client.get_trends(trend_type)
        trends = getattr(result, 'data', []) # Use getattr for safety

        print("Current trends:")
        if not trends:
            print("  No trends found or result format unexpected.")

        for i, trend in enumerate(trends[:10]): # Show top 10 trends
            trend_name = getattr(trend, 'name', 'Unknown Trend')
            # Handle potentially missing tweet_volume safely
            tweet_volume = getattr(trend, 'tweet_volume', None)
            volume_str = f" ({tweet_volume:,} tweets)" if tweet_volume else ""
            print(f"  {i+1}. {trend_name}{volume_str}")
    except Exception as e:
        print(f"Error getting trends: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging


async def main():
    """Main function to run the examples."""
    if await login():
        # --- Run Examples (Comment out any you don't want to run) ---
        # await example_create_tweet_with_media() # Requires media files
        await example_search_tweets()
        await example_get_user_tweets()
        # await example_send_dm() # Requires valid recipient ID
        await example_get_trends()

        # --- Cleanup ---
        # Removed client.close() as it doesn't exist
        print("\nClient session will end when script finishes.")
    else:
        print("Exiting due to login failure.")

if __name__ == "__main__":
    # Ensure you are in an environment where asyncio can run (e.g., standard Python 3.7+)
    # Consider adding error handling for the asyncio.run call itself
    print("Running Twikit examples...")
    asyncio.run(main())
    print("\nScript finished.") 