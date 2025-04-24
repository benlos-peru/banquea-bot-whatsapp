import httpx
import logging

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
            response = httpx.get("https://enarm.pe/api/statistics/aienam", timeout=10)
            response.raise_for_status()
            payload = response.json()
            data = payload.get('data', []) or []
            # Extract phone numbers
            numbers = {item.get('phone') for item in data if item.get('phone')}
            # Normalize: include both raw and with country code if missing
            normalized = set()
            for num in numbers:
                normalized.add(num)
                # If no country code prefix (e.g., len<=8), add with '51'
                if len(num) <= 8:
                    normalized.add('51' + num)
                # If starts with '51', also add stripped
                elif num.startswith('51'):
                    normalized.add(num[2:])
            self.active_numbers = normalized
            logger.info(f"Loaded {len(numbers)} active user numbers")
        except Exception as e:
            logger.error(f"Error fetching active users from API: {e}")
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
        # Normalize format if needed (API returns numbers without '+' and with country code)
        return phone_number in self.active_numbers

# Create singleton instance
active_user_manager = ActiveUserManager()
