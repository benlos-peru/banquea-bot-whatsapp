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
API_URL = "https://bot-whatsapp.banquea.pe"  # Update if your server is running on a different host/port
PHONE_NUMBER = "+51973296571"      # The test phone number
TEMPLATE_NAME = "seleccion_de_fecha"  # The template name to use
LANGUAGE_CODE = "es"               # The language code

async def send_template_message():
    """Send a template message to the test user."""
    try:
        # Add the test user and send a template message
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/admin/add-test-user",
                json={
                    "phone_number": PHONE_NUMBER,
                    "template_name": TEMPLATE_NAME,
                    "language_code": LANGUAGE_CODE
                }
            )
            
            # Check the response
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Success: {result.get('message')}")
            else:
                logger.error(f"Error: {response.status_code} - {response.text}")
                
    except Exception as e:
        logger.error(f"Error sending template message: {str(e)}")

if __name__ == "__main__":
    # Run the async function
    asyncio.run(send_template_message()) 