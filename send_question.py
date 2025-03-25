#!/usr/bin/env python3
"""
Simple command line tool to send a test question to a user.
Usage: python send_question.py <phone_number>
Example: python send_question.py +51973296571
"""
import asyncio
import sys
import logging
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.whatsapp import WhatsAppClient
from app.utils import get_random_question, load_all_data
from app import crud

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

async def send_question_to_user(phone_number: str):
    """Send a question to a specified user."""
    try:
        # Load data
        load_all_data()
        logger.info(f"Data loaded, sending question to {phone_number}")
        
        # Create database session
        db = SessionLocal()
        
        # Get or create user
        user = crud.get_user_by_phone(db, phone_number)
        if not user:
            user = crud.create_user(db, phone_number)
            logger.info(f"Created new user with phone number: {phone_number}")
        else:
            logger.info(f"Using existing user with phone number: {phone_number}")
        
        # Get a random question
        question = get_random_question()
        if not question:
            logger.error("No questions available")
            return
        
        # Update user state
        user.last_question_id = question["id"]
        user.conversation_state = 5  # AWAITING_QUESTION_RESPONSE
        db.commit()
        
        # Create WhatsApp client
        client = WhatsAppClient()
        
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
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python send_question.py <phone_number>")
        print("Example: python send_question.py +51973296571")
        sys.exit(1)
        
    phone_number = sys.argv[1]
    
    # Clean up phone number
    if not phone_number.startswith("+"):
        phone_number = f"+{phone_number}"
        
    # Run the async function
    asyncio.run(send_question_to_user(phone_number)) 