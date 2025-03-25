#!/usr/bin/env python3
"""
Script to send WhatsApp templates to uncontacted users in the database.
Usage: python send_bulk_messages.py [--limit=100]
"""
import asyncio
import argparse
import logging
from datetime import datetime
from sqlalchemy import or_

from app.database import SessionLocal
from app.whatsapp import WhatsAppClient
from app.utils import load_all_data
from app import crud
from app.models import User, UserResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# State machine constants (must match routes.py)
STATES = {
    "INITIAL": 0,
    "AWAITING_CONFIRMATION": 1,
    "AWAITING_DAY": 2,
    "AWAITING_HOUR": 3,
    "SUBSCRIBED": 4,
    "AWAITING_QUESTION_RESPONSE": 5
}

async def send_bulk_messages(limit: int = 100):
    """
    Send templates to uncontacted users in the database.
    
    Args:
        limit: Maximum number of users to contact in one run
    """
    try:
        # Load data
        load_all_data()
        logger.info(f"Data loaded, preparing to send to up to {limit} users")
        
        # Create database session
        db = SessionLocal()
        
        # Get uncontacted users: 
        # - Active users who are not blacklisted
        # - Either they have never been contacted (last_message_sent is NULL) 
        # - Or they have completed the flow (state is SUBSCRIBED) but haven't received a question recently
        uncontacted_users = db.query(User).filter(
            User.is_active == True,
            User.is_blacklisted == False,
            or_(
                User.last_message_sent == None,  # Never contacted
                User.conversation_state == STATES["SUBSCRIBED"]  # Completed setup but no recent question
            )
        ).limit(limit).all()
        
        logger.info(f"Found {len(uncontacted_users)} users to contact")
        
        # Create WhatsApp client
        client = WhatsAppClient()
        
        # Send templates to users
        success_count = 0
        failure_count = 0
        
        for user in uncontacted_users:
            phone_number = user.phone_number
            
            # Check if this is a first-time user or a returning user
            user_has_previous_answers = db.query(UserResponse).filter(
                UserResponse.user_id == user.id
            ).count() > 0
            
            template_name = "confirmacion_pregunta" if user_has_previous_answers else "bienvenida_banquea"
            
            # Send the appropriate template
            success = await client.send_template_message(
                phone_number,
                template_name,
                "es"
            )
            
            if success:
                # Update user state
                user.conversation_state = STATES["AWAITING_CONFIRMATION"]
                user.last_message_sent = datetime.utcnow()
                db.commit()
                
                logger.info(f"Successfully sent {template_name} to {phone_number}")
                success_count += 1
            else:
                logger.error(f"Failed to send template to {phone_number}")
                failure_count += 1
            
            # Add a small delay to avoid rate limiting
            await asyncio.sleep(1)
        
        logger.info(f"Completed sending templates - Success: {success_count}, Failed: {failure_count}")
        
    except Exception as e:
        logger.error(f"Error sending bulk messages: {str(e)}", exc_info=True)
    finally:
        db.close()

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Send WhatsApp templates to uncontacted users")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of users to contact")
    args = parser.parse_args()
    
    # Run the async function
    asyncio.run(send_bulk_messages(args.limit)) 