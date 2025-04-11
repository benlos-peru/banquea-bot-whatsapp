import httpx
import os
from dotenv import load_dotenv
import json
import logging
import requests
from typing import Dict, Any, Optional, List

load_dotenv()

logger = logging.getLogger(__name__)

class WhatsAppClient:
    def __init__(self):
        # Phone number ID (not the display phone number)
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        # WhatsApp Business Account ID
        self.waba_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
        # Base URL for the WhatsApp Cloud API
        self.api_url = "https://graph.facebook.com/v22.0"
        # Access token
        self.access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        # Verify token for webhook
        self.verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "banquea_medical_bot_verify_token")
    
    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """
        Verify the webhook for WhatsApp Cloud API.
        
        Args:
            mode: The hub.mode parameter
            token: The hub.verify_token parameter
            challenge: The hub.challenge parameter
            
        Returns:
            str: The challenge string if verification passes, None otherwise
        """
        logger.info("Starting webhook verification...")
        logger.info(f"Received parameters - mode: {mode}, token: [REDACTED], challenge: {challenge}")
        logger.info(f"Expected verify_token: [REDACTED] (first 3 chars: {self.verify_token[:3] if self.verify_token else 'None'})")
        
        if mode == "subscribe" and token == self.verify_token:
            logger.info("WEBHOOK_VERIFIED: Mode and token match")
            return challenge
        
        # Log specific verification failure reason
        if mode != "subscribe":
            logger.warning(f"Webhook verification failed: Mode '{mode}' is not 'subscribe'")
        elif token != self.verify_token:
            logger.warning("Webhook verification failed: Token mismatch")
        else:
            logger.warning("Webhook verification failed: Unknown reason")
        
        return None