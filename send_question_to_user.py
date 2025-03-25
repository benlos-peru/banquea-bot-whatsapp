import asyncio
import os
import sys
import logging
from dotenv import load_dotenv
from app.whatsapp import WhatsAppClient
from app.utils import get_random_question, add_or_update_user, load_all_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

async def send_question_to_user(phone_number: str):
    """Send a question to a specific user."""
    try:
        # Load data first
        load_all_data()
        
        # Create a WhatsApp client
        client = WhatsAppClient()
        
        # Register the user if not exists
        add_or_update_user(phone_number)
        
        # Get a random question
        question = get_random_question()
        if not question:
            logger.error("No questions available")
            return
        
        # Send the question
        success = await client.send_question_list_message(
            phone_number,
            question["text"],
            question["options"],
            question["id"]
        )
        
        if success:
            logger.info(f"Question sent successfully to {phone_number}")
        else:
            logger.error(f"Failed to send question to {phone_number}")
                
    except Exception as e:
        logger.error(f"Error sending question: {str(e)}")

# Run the async function
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python send_question_to_user.py <phone_number>")
        print("Example: python send_question_to_user.py +51973296571")
        sys.exit(1)
        
    phone_number = sys.argv[1]
    asyncio.run(send_question_to_user(phone_number)) 