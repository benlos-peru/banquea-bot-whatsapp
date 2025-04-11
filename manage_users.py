#!/usr/bin/env python3
"""
Utility script for managing users in the WhatsApp bot application.
This script can add specific users and reset user states for testing purposes.
"""
import argparse
import logging
import os
import sys
import json
from typing import List, Dict, Optional

# Set up path to include the src directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from src.database import SessionLocal, engine
from src.models import Base, User, UserState
from src import crud, schemas

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Ensure database tables exist
Base.metadata.create_all(bind=engine)

def add_specific_users(db: Session, users_info: List[Dict]) -> List[User]:
    """
    Add specific users with provided phone numbers and usernames.
    
    Args:
        db: Database session
        users_info: List of dictionaries with phone_number and username
        
    Returns:
        List of created users
    """
    created_users = []
    
    for user_info in users_info:
        phone_number = user_info["phone_number"]
        username = user_info.get("username", f"user_{phone_number[-4:]}")
        
        # Check if user already exists
        existing_user = crud.get_user_by_phone(db, phone_number)
        if existing_user:
            logger.info(f"User with phone {phone_number} already exists, updating.")
            # Update the existing user if needed
            try:
                update_data = schemas.UserUpdate(
                    username=username,
                    state=UserState.UNCONTACTED
                )
                updated_user = crud.update_user(db, existing_user.id, update_data)
                created_users.append(updated_user)
                logger.info(f"Updated user: {username} with phone: {phone_number}")
            except Exception as e:
                logger.error(f"Error updating user: {str(e)}")
            continue
        
        # Create new user
        user_data = schemas.UserCreate(
            phone_number=phone_number,
            username=username,
            scheduled_hour=12,  # Default hour
            scheduled_day_of_week=1,  # Default day (Tuesday)
            whatsapp_id="",  # Will be filled when user first interacts
            state=UserState.UNCONTACTED
        )
        
        try:
            new_user = crud.create_user(db, user_data)
            if new_user:
                logger.info(f"Created user: {username} with phone: {phone_number}")
                created_users.append(new_user)
            else:
                logger.error(f"Failed to create user with phone: {phone_number}")
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
    
    return created_users

def reset_users_by_phone(db: Session, state: int = UserState.UNCONTACTED, phone_numbers: Optional[List[str]] = None) -> int:
    """
    Reset users to a specific state by phone number.
    
    Args:
        db: Database session
        state: The state to set users to
        phone_numbers: List of phone numbers to reset
        
    Returns:
        Number of users reset
    """
    if not phone_numbers:
        return 0
        
    reset_count = 0
    
    for phone in phone_numbers:
        user = crud.get_user_by_phone(db, phone)
        if not user:
            logger.warning(f"User with phone {phone} not found, skipping.")
            continue
            
        old_state = user.state
        user.state = state
        logger.info(f"Resetting user {user.phone_number} from state {old_state} to {state}")
        reset_count += 1
    
    db.commit()
    return reset_count

def list_users(db: Session, limit: int = 50) -> List[User]:
    """
    List users in the database.
    
    Args:
        db: Database session
        limit: Maximum number of users to list
        
    Returns:
        List of users
    """
    users = db.query(User).limit(limit).all()
    
    if not users:
        logger.info("No users found in the database.")
        return []
    
    logger.info(f"Found {len(users)} users:")
    for user in users:
        state_name = "UNKNOWN"
        for state_name_attr in dir(UserState):
            if not state_name_attr.startswith("_") and getattr(UserState, state_name_attr) == user.state:
                state_name = state_name_attr
                break
        
        logger.info(f"ID: {user.id}, Phone: {user.phone_number}, Username: {user.username}, "
                   f"State: {user.state} ({state_name}), "
                   f"Day: {user.scheduled_day_of_week}, Hour: {user.scheduled_hour}")
    
    return users

def main():
    parser = argparse.ArgumentParser(description="Manage WhatsApp bot users")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Add specific users command
    add_parser = subparsers.add_parser("add", help="Add specific users")
    add_parser.add_argument("--file", type=str, help="JSON file with users to add")
    add_parser.add_argument("--phone", type=str, nargs="+", help="Phone numbers to add")
    add_parser.add_argument("--names", type=str, nargs="+", help="Usernames for the numbers (same order)")
    
    # Reset states command
    reset_parser = subparsers.add_parser("reset", help="Reset user states")
    reset_parser.add_argument("--state", type=int, default=UserState.UNCONTACTED, 
                             help="State to set users to (0=UNCONTACTED, 1=AWAITING_DAY, 2=AWAITING_HOUR, 3=SUBSCRIBED)")
    reset_parser.add_argument("--phone", type=str, nargs="+", help="Phone numbers to reset")
    
    # List users command
    list_parser = subparsers.add_parser("list", help="List users in the database")
    list_parser.add_argument("--limit", type=int, default=50, help="Maximum number of users to list")
    
    args = parser.parse_args()
    
    # Get database session
    db = SessionLocal()
    try:
        if args.command == "add":
            users_to_add = []
            
            if args.file:
                try:
                    with open(args.file, 'r') as f:
                        users_to_add = json.load(f)
                    logger.info(f"Loaded {len(users_to_add)} users from {args.file}")
                except Exception as e:
                    logger.error(f"Error loading users from file: {str(e)}")
            
            elif args.phone:
                if args.names and len(args.names) != len(args.phone):
                    logger.warning("Number of names doesn't match number of phones, using default names")
                    args.names = None
                
                for i, phone in enumerate(args.phone):
                    username = args.names[i] if args.names and i < len(args.names) else f"user_{phone[-4:]}"
                    users_to_add.append({
                        "phone_number": phone,
                        "username": username
                    })
            
            if users_to_add:
                added = add_specific_users(db, users_to_add)
                logger.info(f"Added/updated {len(added)} users")
            else:
                logger.error("No users to add. Specify --file or --phone")
                parser.print_help()
                
        elif args.command == "reset":
            if args.phone:
                count = reset_users_by_phone(db, args.state, args.phone)
                logger.info(f"Reset {count} users to state {args.state}")
            else:
                logger.error("No users specified for reset. Use --phone")
                
        elif args.command == "list":
            list_users(db, args.limit)
            
        else:
            parser.print_help()
    finally:
        db.close()

if __name__ == "__main__":
    main()
