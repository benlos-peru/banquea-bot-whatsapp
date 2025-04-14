from .message_handler import handle_message 
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
async def verify_webhook(request: Request):
    """
    Verify webhook endpoint for WhatsApp Cloud API.
    This endpoint is called by WhatsApp when setting up the webhook.
    Returns 403 if verification fails, 400 if parameters are missing/invalid.
    """
    try:
        logger.info("Received webhook verification request")
        
        # Get query parameters
        params = request.query_params
        hub_mode = params.get("hub.mode")
        hub_verify_token = params.get("hub.verify_token")
        hub_challenge = params.get("hub.challenge")
        
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
    \"\"\"
    Main webhook endpoint for receiving WhatsApp messages and updates.
    This endpoint handles all incoming messages and interactions from WhatsApp.
    \"\"\"
    processed_data = {} # Initialize to handle potential errors before assignment
    request_id = 'N/A' # Initialize request_id
    try:
        # Get the raw payload
        body = await request.json()
        # logger.debug(f"Received webhook payload: {json.dumps(body)}") # Keep debug lower if too verbose
        
        # Initial validation
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail=\"Invalid payload format\")
            
        # Verify this is a WhatsApp Business Account webhook
        if body.get(\"object\") != \"whatsapp_business_account\":
            logger.info(\"Received non-WhatsApp webhook, ignoring\")
            return {\"status\": \"ignored\"}
            
        # Process the webhook payload
        processed_data = whatsapp_client.process_webhook_payload(body)
        request_id = processed_data.get('request_id', 'N/A') # Get request_id after processing
        
        if not processed_data:
            logger.info(f\"[{request_id}] Webhook payload did not result in processable data.\")
            return {\"status\": \"no_action_needed\"}
            
        # Check if it's a message type that needs handling
        if processed_data.get(\"type\") == \"message\":
            logger.info(f\"[{request_id}] Passing message to handler\")
            # Call the main message handler
            handler_result = await handle_message(db, processed_data)
            logger.info(f\"[{request_id}] Message handler result: {handler_result}\")
            # Return 200 OK to WhatsApp immediately
            return {\"status\": \"processed\"} 
        elif processed_data.get(\"type\") == \"status_update\":
             logger.info(f\"[{request_id}] Status update received, no handler action needed.\")
             return {\"status\": \"status_update_received\"}
        else:
            logger.warning(f\"[{request_id}] Unhandled processed data type: {processed_data.get('type')}\")
            return {\"status\": \"unhandled_type\"}

    except HTTPException as http_exc:
        # Re-raise HTTPExceptions to let FastAPI handle them
        logger.error(f\"[{request_id}] HTTP error processing webhook: {http_exc.detail}\", exc_info=True)
        raise http_exc
    except Exception as e:
        logger.error(f\"[{request_id}] Error processing webhook: {str(e)}\", exc_info=True)
        # Return a 500 error response for internal errors
        # Avoid returning detailed error messages in production if possible
        raise HTTPException(status_code=500, detail=\"Internal server error processing webhook\")
