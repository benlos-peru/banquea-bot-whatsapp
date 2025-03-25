import asyncio
import os
import logging
from dotenv import load_dotenv
from app.whatsapp import WhatsAppClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
PHONE_NUMBER = "+51973296571"      # The test phone number
TEMPLATE_NAME = "seleccion_de_fecha"  # The template name to use
LANGUAGE_CODE = "es"               # The language code

async def send_template_message():
    """Send a template message to the test user directly using the WhatsApp client."""
    try:
        # Create a WhatsApp client
        client = WhatsAppClient()
        
        # Send template message
        success = await client.send_template_message(
            PHONE_NUMBER,
            TEMPLATE_NAME,
            LANGUAGE_CODE
        )
        
        if success:
            logger.info(f"Template message '{TEMPLATE_NAME}' sent successfully to {PHONE_NUMBER}")
        else:
            logger.error(f"Failed to send template message to {PHONE_NUMBER}")
                
    except Exception as e:
        logger.error(f"Error sending template message: {str(e)}")

# Run the async function
if __name__ == "__main__":
    asyncio.run(send_template_message()) 