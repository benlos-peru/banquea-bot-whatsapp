import httpx
import logging
import json # Import json for logging

logger = logging.getLogger(__name__)

class ActiveUserManager:
    """
    Manages the list of active users fetched from external API.
    """
    def __init__(self):
        self.active_numbers = set()
        self._load_active_users()

    def _load_active_users(self):
        """Fetch active users list from API and store phone numbers"""
        try:
            logger.debug("Fetching active users from API...")
            response = httpx.get("https://enarm.pe/api/statistics/aienam", timeout=10)
            response.raise_for_status()
            payload = response.json()
            # Log raw payload (or part of it) for debugging
            logger.debug(f"API Raw Payload (first 500 chars): {json.dumps(payload)[:500]}")
            data = payload.get('data', []) or []
            # Extract phone numbers
            numbers = {item.get('phone') for item in data if item.get('phone')}
            logger.debug(f"Extracted raw phone numbers from API: {numbers}")
            # Normalize: include both raw and with country code if missing
            normalized = set()
            for num in numbers:
                if not num: continue # Skip empty strings
                num_stripped = num.strip() # Remove whitespace
                normalized.add(num_stripped)
                # If no country code prefix (assuming 9 digits for Peru mobile), add with '51'
                if len(num_stripped) == 9 and num_stripped.isdigit():
                    normalized.add('51' + num_stripped)
                # If starts with '51' and has 11 digits, also add stripped version (9 digits)
                elif num_stripped.startswith('51') and len(num_stripped) == 11:
                    normalized.add(num_stripped[2:])
            self.active_numbers = normalized
            logger.info(f"Loaded {len(numbers)} active user numbers. Stored {len(self.active_numbers)} normalized variations.")
            logger.debug(f"Stored normalized active numbers (sample): {list(self.active_numbers)[:20]}") # Log a sample
        except Exception as e:
            logger.error(f"Error fetching active users from API: {e}", exc_info=True) # Add exc_info
        # Cleanup: remove scheduled jobs for inactive users
        try:
            from .scheduler import scheduler
            from .database import SessionLocal
            from .models import User
            jobs = scheduler.get_jobs()
            with SessionLocal() as db:
                for job in jobs:
                    if job.id.startswith('question_confirmation_'):
                        uid = int(job.id.split('_')[-1])
                        user = db.query(User).filter(User.id == uid).first()
                        if user and not self.is_active(user.phone_number):
                            scheduler.remove_job(job.id)
                            logger.info(f"Removed job {job.id} for inactive user {user.phone_number}")
        except Exception as err:
            logger.error(f"Error cleaning up scheduled jobs: {err}")

    def is_active(self, phone_number: str) -> bool:
        """Check if a given phone number is in the active set"""
        logger.debug(f"Checking if number '{phone_number}' is active...")
        # Normalize format if needed (API returns numbers without '+' and with country code)
        is_present = phone_number in self.active_numbers
        logger.debug(f"Result for '{phone_number}': {is_present}. (Set sample: {list(self.active_numbers)[:10]})")
        return is_present

# Create singleton instance
active_user_manager = ActiveUserManager()
