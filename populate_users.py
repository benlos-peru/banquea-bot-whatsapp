import httpx
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add src directory to sys.path to allow imports
# project_root = Path(__file__).parent
# src_path = project_root / 'src'
# sys.path.insert(0, str(src_path)) # No longer needed if using src. imports

# Use imports relative to the project root, assuming src is a package
from src.database import SessionLocal, engine
from src.models import Base, UserState
from src.schemas import UserCreate, UserUpdate # Import UserUpdate
from src import crud # Import crud as part of the src package

# Load environment variables (if needed, e.g., for DB connection)
project_root = Path(__file__).parent # Define project_root for dotenv
load_dotenv(project_root / '.env')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_ENDPOINT = "https://enam.pe/api/statistics/aienam" # Endpoint for users

def normalize_phone_number(phone: str) -> str:
    """Ensure phone number starts with '51' prefix."""
    if not phone:
        return None
    # Remove leading/trailing whitespace
    phone = phone.strip()
    # Check if it already has a country code (assuming Peru '51')
    if len(phone) > 9 and phone.startswith('51'):
        return phone
    elif len(phone) == 9 and phone.isdigit(): # Standard 9-digit Peru mobile number
        return f"51{phone}"
    else:
        # Handle potentially invalid numbers or numbers with other prefixes if needed
        # For now, return as is or log a warning if format is unexpected
        logger.warning(f"Unexpected phone number format encountered: {phone}. Returning as is.")
        return phone # Or return None if invalid numbers should be skipped

async def fetch_users_from_api():
    """Fetch user data from the API endpoint."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(API_ENDPOINT)
            response.raise_for_status() # Raise exception for bad status codes
            payload = response.json()
            if payload.get("status") is True and isinstance(payload.get("data"), list):
                logger.info(f"Successfully fetched {len(payload['data'])} records from API.")
                return payload["data"]
            else:
                logger.error(f"API response format incorrect or status is not true: {payload}")
                return []
    except httpx.RequestError as e:
        logger.error(f"Error fetching users from API: {e}")
        return []
    except Exception as e:
        logger.error(f"An unexpected error occurred during API fetch: {e}")
        return []


async def populate_database():
    """Fetch users from API and add or update them in the database."""
    logger.info("Starting user population script...")
    
    # Ensure database tables are created (optional, usually handled by main app)
    # Base.metadata.create_all(bind=engine) 
    
    api_users = await fetch_users_from_api()
    if not api_users:
        logger.warning("No users fetched from API. Exiting.")
        return

    added_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    # Use a set to handle potential duplicates from the API based on normalized phone
    processed_phones = set()

    db = SessionLocal()
    try:
        for api_user in api_users:
            raw_phone = api_user.get("phone")
            name = api_user.get("name")
            # Potentially other fields like plan_id if needed
            # plan_id = api_user.get("plan_id") 

            if not raw_phone or not name:
                logger.warning(f"Skipping record due to missing phone or name: {api_user}")
                error_count += 1
                continue

            normalized_phone = normalize_phone_number(raw_phone)
            if not normalized_phone:
                 logger.warning(f"Skipping record due to invalid phone number after normalization: {raw_phone}")
                 error_count += 1
                 continue
                 
            # Avoid processing duplicates from the API list itself
            if normalized_phone in processed_phones:
                continue
            processed_phones.add(normalized_phone)

            # Check if user already exists
            existing_user = crud.get_user_by_phone(db, phone_number=normalized_phone)
            
            if existing_user:
                # Update existing user if name differs
                if existing_user.username != name:
                    logger.info(f"Updating user {normalized_phone}: Name change from '{existing_user.username}' to '{name}'")
                    update_data = UserUpdate(username=name) # Use UserUpdate directly
                    try:
                        crud.update_user(db=db, user_id=existing_user.id, user=update_data)
                        updated_count += 1
                    except Exception as e:
                        logger.error(f"Failed to update user {normalized_phone} ('{name}'): {e}")
                        error_count += 1
                        db.rollback()
                else:
                    # logger.info(f"User with phone {normalized_phone} already exists and name matches. Skipping.")
                    skipped_count += 1
            else:
                # Create new user
                logger.info(f"Adding new user: Name='{name}', Phone='{normalized_phone}'")
                user_data = UserCreate( # Use UserCreate directly
                    phone_number=normalized_phone,
                    username=name,
                    # Default schedule details (not important for UNCONTACTED state)
                    scheduled_hour=9, 
                    scheduled_minute=0,
                    scheduled_day_of_week=0, # Monday
                    state=UserState.UNCONTACTED # State 0
                )
                try:
                    crud.create_user(db=db, user=user_data)
                    added_count += 1
                except Exception as e:
                    logger.error(f"Failed to add user {normalized_phone} ('{name}'): {e}")
                    error_count += 1
                    db.rollback() # Rollback failed transaction for this user

    finally:
        db.close()
        logger.info("Finished user population.")
        logger.info(f"Summary: Added={added_count}, Updated={updated_count}, Skipped (no change)={skipped_count}, Errors/Invalid={error_count}")


if __name__ == "__main__":
    import asyncio
    # Ensure database tables exist before running
    # This might be better handled elsewhere, but ensures the script can run standalone
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables checked/created.")
    except Exception as e:
        logger.error(f"Failed to check/create database tables: {e}")
        sys.exit(1) # Exit if DB setup fails

    asyncio.run(populate_database())
