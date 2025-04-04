import asyncio
import os
import sys
from twikit import Client
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.text import Text
from rich.table import Table

# --- Initialization ---
load_dotenv()
console = Console()
client = None # Initialize client as None initially

# --- Helper Functions ---
def print_panel(content, title="Twikit Scraper", style="bold blue"):
    """Prints content inside a styled panel."""
    console.print(Panel(content, title=title, border_style=style, expand=False))

def print_error(message):
    """Prints an error message in red."""
    console.print(f"[bold red]Error: {message}[/]")

def print_success(message):
    """Prints a success message in green."""
    console.print(f"[bold green]{message}[/]")

async def ensure_login():
    """Ensures the client is logged in. Logs in if necessary."""
    global client
    # Check if client exists and has the stored user data
    if client and hasattr(client, '_logged_in_user') and client._logged_in_user:
        # print_success(f"Already logged in as {client._logged_in_user.screen_name}")
        return True

    USERNAME = os.environ.get('TWITTER_USERNAME')
    EMAIL = os.environ.get('TWITTER_EMAIL')
    PASSWORD = os.environ.get('TWITTER_PASSWORD')
    COOKIES_FILE = 'cookies.json'

    if not all([USERNAME, EMAIL, PASSWORD]):
        print_error("Twitter credentials not found in .env file.")
        console.print("Please create a .env file with TWITTER_USERNAME, TWITTER_EMAIL, and TWITTER_PASSWORD.")
        return False

    # If client exists but no user data, reset it to force re-login attempt
    # This handles cases where previous attempts might have partially failed
    if client:
        client = None
        
    console.print("\nAttempting login...")
    try:
        client = Client('en-US')
        await client.login(
            auth_info_1=USERNAME,
            auth_info_2=EMAIL,
            password=PASSWORD,
            cookies_file=COOKIES_FILE
        )
        # --- Get user data by CALLING the method ---
        user_data = await client.user()
        # --- Store user data on the client instance for later use ---
        client._logged_in_user = user_data
        # --- END Changes ---

        if client._logged_in_user and hasattr(client._logged_in_user, 'screen_name'):
            print_success(f"Login successful as @{client._logged_in_user.screen_name}!")
            return True
        else:
            print_error("Login successful, but failed to retrieve user data correctly.")
            client = None # Reset client
            return False

    except Exception as e:
        print_error(f"Login failed: {e}")
        client = None # Reset client on failure
        return False

# --- Action Functions ---

async def search_tweets_interactive():
    """Interactively searches tweets."""
    if not await ensure_login():
        return

    query = Prompt.ask("[cyan]Enter search query[/]")
    search_type = Prompt.ask(
        "[cyan]Enter search type[/]",
        choices=['Latest', 'Top', 'Media'],
        default='Latest'
    )
    max_results = IntPrompt.ask("[cyan]Maximum results to fetch?[/]", default=10)

    console.print(f"\nSearching for '{search_type}' tweets containing '{query}'...")
    try:
        tweets = await client.search_tweet(query, search_type, count=max_results)
        result_count = len(tweets) # Assuming search_tweet returns a list directly now
        print_success(f"Found {result_count} tweets.")

        if not tweets:
            return

        table = Table(title=f"Search Results for '{query}' ({search_type})")
        table.add_column("User", style="magenta")
        table.add_column("Tweet", style="green", no_wrap=False)
        table.add_column("Date", style="cyan")
        table.add_column("Link", style="blue")

        for tweet in tweets:
            user_text = f"{getattr(getattr(tweet, 'user', None), 'name', '?')} (@{getattr(getattr(tweet, 'user', None), 'screen_name', '?')})"
            tweet_text = getattr(tweet, 'text', '')
            created_at = str(getattr(tweet, 'created_at', '?'))
            # Construct the full URL
            screen_name = getattr(getattr(tweet, 'user', None), 'screen_name', '?')
            tweet_id = getattr(tweet, 'id', '?')
            full_link = f"https://twitter.com/{screen_name}/status/{tweet_id}"
            # Use rich hyperlink markup
            link_markup = f"[link={full_link}]{full_link}[/link]" if screen_name != '?' and tweet_id != '?' else "N/A"
            table.add_row(user_text, tweet_text, created_at, link_markup)

        console.print(table)

    except Exception as e:
        print_error(f"Error searching tweets: {e}")

async def get_user_tweets_interactive():
    """Interactively gets user tweets."""
    if not await ensure_login():
        return

    user_input = Prompt.ask("[cyan]Enter Twitter User ID or Screen Name[/]").strip()
    # Revert choices to standard capitalization, using 'TweetsAndReplies'
    tweet_type = Prompt.ask(
        "[cyan]Enter tweet type[/]",
        choices=['Tweets', 'TweetsAndReplies', 'Media'], # Use standard capitalization
        default='Tweets'
    )
    max_results = IntPrompt.ask("[cyan]Maximum results to fetch?[/]", default=10)

    user_id = None
    try:
        # Check if the input is purely numeric (likely an ID)
        if user_input.isdigit():
            user_id = user_input
            print(f"(Assuming '{user_input}' is a User ID)")
        else:
            # Assume it's a screen name, fetch the user object
            screen_name_to_fetch = user_input.lstrip('@') # Remove leading @ if present
            console.print(f"Looking up User ID for screen name: @{screen_name_to_fetch}...")
            user_info = await client.get_user_by_screen_name(screen_name_to_fetch)
            if user_info and hasattr(user_info, 'id'):
                user_id = user_info.id
                print_success(f"Found User ID: {user_id}")
            else:
                print_error(f"Could not find user or retrieve ID for screen name: @{screen_name_to_fetch}")
                return # Stop if we couldn't get the ID

        # Proceed only if we have a numeric user_id
        if user_id:
            # Pass the selected tweet_type directly (with capitalization)
            console.print(f"\nFetching '{tweet_type}' for user ID '{user_id}'...")
            result = await client.get_user_tweets(user_id, tweet_type, count=max_results)
            tweets = getattr(result, 'data', [])
            print_success(f"Retrieved {len(tweets)} tweets.")

            if not tweets:
                return

            table = Table(title=f"User Tweets for '{user_input}' ({tweet_type})")
            table.add_column("Tweet", style="green", no_wrap=False)
            table.add_column("Date", style="cyan")
            table.add_column("Link", style="blue")

            for tweet in tweets:
                tweet_text = getattr(tweet, 'text', '')
                created_at = str(getattr(tweet, 'created_at', '?'))
                # Construct the full URL - use the confirmed user_id for consistency
                fetched_screen_name = getattr(getattr(tweet, 'user', None), 'screen_name', user_input.lstrip('@')) # Fallback still useful
                tweet_id = getattr(tweet, 'id', '?')
                full_link = f"https://twitter.com/{fetched_screen_name}/status/{tweet_id}"
                # Use rich hyperlink markup
                link_markup = f"[link={full_link}]{full_link}[/link]" if fetched_screen_name != '?' and tweet_id != '?' else "N/A"
                table.add_row(tweet_text, created_at, link_markup)

            console.print(table)
        else:
             # This case should ideally not be reached if ID lookup fails above, but acts as a safeguard
             print_error("Could not determine a valid User ID to fetch tweets.")

    except Exception as e:
        # Specific handling for user not found potentially?
        if "Could not find user" in str(e):
            print_error(f"Failed to find user: {user_input}")
        else:
            print_error(f"Error getting user tweets: {e}")
        import traceback
        traceback.print_exc()

async def get_trends_interactive():
    """Gets trending topics."""
    if not await ensure_login():
        return

    # In the future, could prompt for WOEID
    trend_type = 'trending'
    console.print(f"\nFetching trends ({trend_type})...")
    try:
        result = await client.get_trends(trend_type)
        trends = getattr(result, 'data', [])
        print_success(f"Retrieved {len(trends)} trends.")

        if not trends:
            return

        table = Table(title="Trending Topics")
        table.add_column("#", style="dim cyan")
        table.add_column("Trend", style="magenta")
        table.add_column("Volume", style="blue")

        for i, trend in enumerate(trends):
            name = getattr(trend, 'name', '?')
            volume = getattr(trend, 'tweet_volume', None)
            volume_str = f"{volume:,}" if volume else "N/A"
            table.add_row(str(i + 1), name, volume_str)

        console.print(table)

    except Exception as e:
        print_error(f"Error getting trends: {e}")

async def create_tweet_interactive():
    """Interactively creates a tweet."""
    if not await ensure_login():
        return

    console.print("\nEnter tweet text (press Enter twice to finish):")
    lines = []
    try:
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
    except EOFError:
        pass # Handle Ctrl+D or similar
    tweet_text = "\n".join(lines).strip()

    if not tweet_text:
        print_error("Tweet text cannot be empty.")
        return

    # Optional: Add media upload here if desired
    # media_paths_str = Prompt.ask("[cyan]Enter paths to media files (comma-separated, optional):[/]")
    # media_ids = []
    # if media_paths_str:
    #     media_paths = [p.strip() for p in media_paths_str.split(',') if p.strip()]
    #     # Add logic to check paths and upload using client.upload_media

    confirm = Prompt.ask(
        f"\nPost this tweet?\n[yellow]{tweet_text}[/yellow]\n",
        choices=['y', 'n'], default='y'
    )

    if confirm.lower() == 'y':
        console.print("\nPosting tweet...")
        try:
            # Add media_ids=media_ids if implementing media upload
            tweet = await client.create_tweet(text=tweet_text)
            # --- Use stored user data --- 
            screen_name = getattr(client._logged_in_user, 'screen_name', 'unknown')
            print_success(f"Tweet posted successfully! ID: {tweet.id}")
            console.print(f"Link: https://twitter.com/{screen_name}/status/{tweet.id}")
            # --- END Change ---
        except Exception as e:
            print_error(f"Failed to post tweet: {e}")
    else:
        console.print("Tweet posting cancelled.")


# --- Main Menu ---`

def display_menu():
    """Displays the main menu."""
    menu_text = Text("\nChoose an action:")
    menu_text.append("\n 1. Search Tweets", style="cyan")
    menu_text.append("\n 2. Get User Tweets", style="cyan")
    menu_text.append("\n 3. Get Trends", style="cyan")
    menu_text.append("\n 4. Create Tweet", style="cyan")
    menu_text.append("\n 0. Exit", style="cyan")
    print_panel(menu_text, title="Main Menu", style="bold green")

async def main_loop():
    """Runs the main interactive loop."""
    print_panel("Welcome to the Interactive Twikit Scraper!", style="bold magenta")

    # Attempt initial login
    await ensure_login()

    while True:
        display_menu()
        choice = IntPrompt.ask("[yellow]Enter your choice[/]", choices=[str(i) for i in range(5)], show_choices=False)

        if choice == 1:
            await search_tweets_interactive()
        elif choice == 2:
            await get_user_tweets_interactive()
        elif choice == 3:
            await get_trends_interactive()
        elif choice == 4:
            await create_tweet_interactive()
        elif choice == 0:
            console.print("\n[bold blue]Exiting. Goodbye![/]")
            break
        else:
            print_error("Invalid choice.")

        Prompt.ask("\nPress Enter to continue...") # Pause before showing menu again
        console.clear() # Optional: Clear screen before next menu

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Operation cancelled by user.[/]")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        console.print("CLI finished.")
        sys.exit(0) 