from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
import logging
import json
from typing import Optional, Dict, Any

from .database import get_db
from .whatsapp import WhatsAppClient

logger = logging.getLogger(__name__)
router = APIRouter()
whatsapp_client = WhatsAppClient()

@router.get("/webhook")
async def verify_webhook(
    request: Request,
    hub_mode: str = None,
    hub_verify_token: str = None,
    hub_challenge: str = None
):
    """
    Verify webhook endpoint for WhatsApp Cloud API.
    This endpoint is called by WhatsApp when setting up the webhook.
    Returns 403 if verification fails, 400 if parameters are missing/invalid.
    """
    try:
        logger.info("Received webhook verification request")
        
        # Validate required parameters
        if not all([hub_mode, hub_verify_token, hub_challenge]):
            missing_params = []
            if not hub_mode:
                missing_params.append("hub.mode")
            if not hub_verify_token:
                missing_params.append("hub.verify_token")
            if not hub_challenge:
                missing_params.append("hub.challenge")
            
            error_msg = f"Missing required parameters: {', '.join(missing_params)}"
            logger.warning(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Validate challenge is numeric
        try:
            int(hub_challenge)
        except ValueError:
            error_msg = "hub.challenge must be numeric"
            logger.warning(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
            
        # Log parameters safely (after validation)
        logger.info(
            "Verification parameters - "
            f"mode: {hub_mode}, "
            "token: [REDACTED], "
            f"challenge: {hub_challenge}"
        )
        
        # Verify the token and mode
        result = whatsapp_client.verify_webhook(
            mode=hub_mode,
            token=hub_verify_token,
            challenge=hub_challenge
        )
        
        if result:
            logger.info("Webhook verification successful")
            return int(hub_challenge)
        
        logger.warning("Webhook verification failed")
        raise HTTPException(status_code=403, detail="Verification failed")
        
    except Exception as e:
        logger.error(f"Error in webhook verification: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Main webhook endpoint for receiving WhatsApp messages and updates.
    This endpoint handles all incoming messages and interactions from WhatsApp.
    """
    try:
        # Get the raw payload
        body = await request.json()
        logger.debug(f"Received webhook payload: {json.dumps(body)}")
        
        # Initial validation
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Invalid payload format")
            
        # Verify this is a WhatsApp Business Account webhook
        if body.get("object") != "whatsapp_business_account":
            logger.info("Received non-WhatsApp webhook, ignoring")
            return {"status": "ignored"}
            
        # Process the webhook payload
        processed_data = whatsapp_client.process_webhook_payload(body)
        
        if not processed_data:
            logger.warning("No processable data in webhook payload")
            return {"status": "no_data"}
            
        # TODO: Implement conversation flow logic here
        # This will be handled by separate modules for different message types
        # and conversation states
        
        return {"status": "success", "processed": processed_data}
        
    except json.JSONDecodeError:
        logger.error("Failed to decode webhook payload")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
