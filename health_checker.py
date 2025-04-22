import os
import sys
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

# --- Configuration ---
# Load .env file from the same directory as the script
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

# Get the URL to check from environment variable
HEALTH_CHECK_URL = os.environ.get('HEALTH_CHECK_URL')
# Default to local FastAPI instance if not set (adjust if your default differs)
if not HEALTH_CHECK_URL:
    HEALTH_CHECK_URL = "http://127.0.0.1:8000/health"

# Configure logging
log_file = os.path.join(os.path.dirname(__file__), 'health_check.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout) # Also print to console
    ]
)

# --- Health Check Function ---
def check_server_health(url: str):
    """Performs a GET request to the specified health check URL and logs the result."""
    logging.info(f"Attempting health check for: {url}")
    try:
        # Use a timeout to prevent the script from hanging indefinitely
        response = requests.get(url, timeout=10) # 10 second timeout

        # Check if the status code indicates success (e.g., 200 OK)
        if response.status_code == 200:
            try:
                # Optionally check the content of the response
                data = response.json()
                if data.get("status") == "healthy":
                    logging.info(f"Health check SUCCESS: Status={response.status_code}, Response={data}")
                    return True
                else:
                    logging.warning(f"Health check UNEXPECTED RESPONSE: Status={response.status_code}, Response={data}")
                    return False
            except requests.exceptions.JSONDecodeError:
                logging.warning(f"Health check UNEXPECTED RESPONSE: Status={response.status_code}, Response is not valid JSON: {response.text[:100]}...")
                return False
        else:
            logging.error(f"Health check FAILED: Status={response.status_code}, Response: {response.text[:200]}...")
            return False

    except requests.exceptions.ConnectionError as e:
        logging.error(f"Health check FAILED: Connection error to {url}. Server might be down. Error: {e}")
        return False
    except requests.exceptions.Timeout as e:
        logging.error(f"Health check FAILED: Request timed out for {url}. Error: {e}")
        return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Health check FAILED: An unexpected error occurred. Error: {e}")
        return False

# --- Main Execution ---
if __name__ == "__main__":
    logging.info("--- Starting Health Check --- ")
    if not HEALTH_CHECK_URL:
        logging.error("HEALTH_CHECK_URL environment variable not set. Exiting.")
        sys.exit(1) # Exit with error code

    is_healthy = check_server_health(HEALTH_CHECK_URL)

    if is_healthy:
        logging.info("--- Health Check Completed: Server is healthy --- ")
        sys.exit(0) # Exit with success code
    else:
        logging.error("--- Health Check Completed: Server is UNHEALTHY --- ")
        # You could add actions here, like sending notifications
        sys.exit(1) # Exit with error code 