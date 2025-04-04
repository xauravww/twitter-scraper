# Twikit Scraper Project (Based on Twikit Library)

This project demonstrates usage of the [Twikit](https://github.com/d60/twikit) library for interacting with Twitter.

---

<!-- Original Twikit README Content Below -->

<p align="center">
  <a href="https://github.com/d60/twikit/stargazers">
    <img alt="GitHub stars" src="https://img.shields.io/github/stars/d60/twikit?style=social">
  </a>
  <a href="https://github.com/d60/twikit/commit/">
    <img alt="GitHub commit activity" src="https://img.shields.io/github/commit-activity/m/d60/twikit?style=social">
  </a>
  <a href="https://github.com/d60/twikit/releases">
    <img alt="Version" src="https://img.shields.io/github/v/release/d60/twikit?style=social">
  </a>
  <a href="https://twitter.com/intent/tweet?text=Twikit+-+A+Simple+Twitter+API+Scraper&url=https://github.com/d60/twikit">
    <img alt="Tweet" src="https://img.shields.io/twitter/url?style=social&url=https%3A%2F%2Fgithub.com%2Fd60%2Ftwikit">
  </a>
  <a href="https://discord.gg/kMAH3CvCqn">
    <img alt="Discord" src="https://img.shields.io/discord/1108547597969391667?style=social">
  </a>
  <a href="https://www.buymeacoffee.com/d60">
    <img alt="BuyMeACoffee" src="https://img.shields.io/static/v1?label=BuyMeACoffee&message=Support&color=FFDD00&style=social&logo=buymeacoffee">
  </a>
</p>

[日本語] [中文]

# Twikit
A Simple Twitter API Scraper

You can use functions such as posting or searching for tweets without an API key using this library.

[Documentation (English)](https://twikit.readthedocs.io/en/latest/)
[🔵 Discord](https://discord.gg/kMAH3CvCqn)

## Note

Released [twikit_grok](https://github.com/d60/twikit_grok) an extension for using Grok AI with Twikit.
For more details, visit: https://github.com/d60/twikit_grok.

## Features
### No API Key Required
This library uses scraping and does not require an API key.

### Free
This library is free to use.

## Functionality
By using Twikit, you can access functionalities such as the following:

- Create tweets
- Search tweets
- Retrieve trending topics
- etc...

## Installing
```bash
pip install twikit
```

## Quick Example
Define a client and log in to the account.

```python
import asyncio
from twikit import Client

USERNAME = 'example_user'
EMAIL = 'email@example.com'
PASSWORD = 'password0000'

# Initialize client
client = Client('en-US')

async def main():
    # NOTE: Replace placeholders with your actual credentials
    # It's recommended to use environment variables or a config file
    # instead of hardcoding credentials.
    # The 'cookies.json' file will be created to store session cookies.
    await client.login(
        auth_info_1=USERNAME,
        auth_info_2=EMAIL,
        password=PASSWORD,
        cookies_file='cookies.json'
    )
    print("Login successful!")
    # Add other example calls here if needed
    await client.close() # Close the client session when done

# Run the main asynchronous function
if __name__ == "__main__":
    # You might need to handle potential login errors here
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"An error occurred: {e}")

```
Create a tweet with media attached.

```python
# Make sure client is logged in from the previous example

# Upload media files and obtain media_ids
# Replace 'media1.jpg', 'media2.jpg' with actual file paths
# Ensure these files exist before running
# media_ids = [
#     await client.upload_media('media1.jpg'),
#     await client.upload_media('media2.jpg')
# ]

# Create a tweet with the provided text and attached media
# Uncomment the relevant lines when media is ready
# await client.create_tweet(
#     text='Example Tweet',
#     media_ids=media_ids # Pass the obtained media IDs here
# )

# Example without media
# await client.create_tweet(text='Example Tweet without media')
```
Search the latest tweets based on a keyword

```python
# Make sure client is logged in

# tweets = await client.search_tweet('python', 'Latest')

# print(f"Found {len(tweets)} tweets for 'python':")
# for tweet in tweets:
#     print(
#         f"  User: {tweet.user.name}",
#         f"  Text: {tweet.text}",
#         f"  Created at: {tweet.created_at}"
#     )
```
Retrieve user tweets

```python
# Make sure client is logged in
# Replace '123456' with a valid Twitter User ID
# user_id_to_fetch = '123456'
# tweets = await client.get_user_tweets(user_id_to_fetch, 'Tweets')

# print(f"Found {len(tweets)} tweets for user ID {user_id_to_fetch}:")
# for tweet in tweets:
#     print(f"  Text: {tweet.text}")

```
Send a dm

```python
# Make sure client is logged in
# Replace '123456789' with a valid recipient Twitter User ID
# recipient_id = '123456789'
# await client.send_dm(recipient_id, 'Hello from Twikit!')
# print(f"DM sent to user ID {recipient_id}")
```
Get trends

```python
# Make sure client is logged in
# trends = await client.get_trends('trending')
# print("Current trends:")
# for trend in trends:
#     print(f" - {trend.name} ({trend.tweet_volume} tweets)")

```
More Examples: [examples](https://github.com/d60/twikit/tree/main/examples)

## Contributing
If you encounter any bugs or issues, please report them on [issues](https://github.com/d60/twikit/issues).

If you find this library useful, consider starring the [repository](https://github.com/d60/twikit)⭐️ 

## API Server (FastAPI)

This project also includes a FastAPI server to expose the Twikit functionalities over HTTP.

### Running the API Server

1.  **Ensure Dependencies:** Make sure you have installed all requirements, including `fastapi` and `uvicorn`:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Check `.env`:** Verify your `.env` file in the project root contains the correct Twitter credentials (`TWITTER_USERNAME`, `TWITTER_EMAIL`, `TWITTER_PASSWORD`).
3.  **Run with Uvicorn:** Navigate to the project root directory (`twikit_scraper`) in your terminal (with your virtual environment activated) and run:
    ```bash
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
    ```
    *   `--reload`: Enables auto-reload for development (server restarts on code changes).
    *   You should see output indicating the server is running on `http://127.0.0.1:8000`.

### Accessing the API

*   **Interactive Documentation (Swagger UI):** Open your web browser and go to `http://127.0.0.1:8000/docs`
*   **Alternative Documentation (ReDoc):** Open your web browser and go to `http://127.0.0.1:8000/redoc`

You can explore the available endpoints, see the expected request/response formats, and even try sending requests directly from the documentation interface.

## Interactive CLI

(Instructions for the interactive CLI remain the same...)

## Examples Script

(Instructions for the examples script remain the same...) 