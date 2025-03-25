import asyncio
import httpx
import os
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
API_URL = "http://localhost:8000"  # Update if your server is running on a different host/port
PHONE_NUMBER = "+51973296571"      # The test phone number

async def send_test_question():
    """Send a test question to a user."""
    try:
        # Call the admin endpoint to send a question
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/admin/send-question-to-all"
            )
            
            # Check the response
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Success: {result}")
            else:
                logger.error(f"Error: {response.status_code} - {response.text}")
                
    except Exception as e:
        logger.error(f"Error sending question: {str(e)}")

# Run the async function
if __name__ == "__main__":
    asyncio.run(send_test_question()) 