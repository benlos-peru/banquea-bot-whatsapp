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
        
    async def send_message(self, to_number: str, message: str) -> bool:
        """
        Send a WhatsApp message to the specified number using the Meta WhatsApp Cloud API.
        
        Args:
            to_number: The recipient's phone number (with country code, no +)
            message: The message text to send
            
        Returns:
            bool: True if the message was sent successfully, False otherwise
        """
        try:
            # Ensure number is in the right format (no + at the beginning)
            if to_number.startswith("+"):
                to_number = to_number[1:]
            
            # API endpoint for sending messages
            url = f"{self.api_url}/{self.phone_number_id}/messages"
            
            # Headers
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Message payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_number,
                "type": "text",
                "text": {
                    "body": message
                }
            }
            
            # Log the request
            logger.info(f"Sending WhatsApp message to {to_number}")
            
            # Send the request
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload
                )
                
                # Check response
                if response.status_code == 200:
                    logger.info(f"Successfully sent WhatsApp message to {to_number}")
                    return True
                else:
                    logger.error(f"Failed to send WhatsApp message: {response.text}")
                    return False
            
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {str(e)}")
            return False
    
    async def send_template_message(self, to_number: str, template_name: str, language_code: str = "es", components: Optional[list] = None) -> bool:
        """
        Send a template message to a WhatsApp number.
        Templates must be pre-approved in the WhatsApp Business Manager.
        This is required for the first message to a user or when re-engaging after 24 hours.
        
        Args:
            to_number: The recipient's phone number (with country code, no +)
            template_name: The name of the template
            language_code: The language code (default: es for Spanish)
            components: Optional template components
            
        Returns:
            bool: True if the template was sent successfully, False otherwise
        """
        try:
            # Ensure number is in the right format
            if to_number.startswith("+"):
                to_number = to_number[1:]
            
            # API endpoint
            url = f"{self.api_url}/{self.phone_number_id}/messages"
            
            # Headers
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Template payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_number,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {
                        "code": language_code
                    }
                }
            }
            
            # Add components if provided
            if components:
                payload["template"]["components"] = components
            
            # Send the request
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload
                )
                
                # Check response
                if response.status_code == 200:
                    logger.info(f"Successfully sent template message to {to_number}")
                    return True
                else:
                    logger.error(f"Failed to send template message: {response.text}")
                    return False
            
        except Exception as e:
            logger.error(f"Error sending template message: {str(e)}")
            return False
    
    async def send_interactive_list_message(
        self, 
        to_number: str, 
        body_text: str,
        button_text: str, 
        sections: List[Dict[str, Any]],
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None
    ) -> bool:
        """
        Send an interactive list message to a WhatsApp number.
        
        Args:
            to_number: The recipient's phone number (with country code, no +)
            body_text: The main message text
            button_text: Text for the button that opens the list
            sections: List of sections with title and rows
            header_text: Optional header text
            footer_text: Optional footer text
            
        Returns:
            bool: True if the message was sent successfully, False otherwise
        """
        try:
            # Ensure number is in the right format
            if to_number.startswith("+"):
                to_number = to_number[1:]
            
            # API endpoint
            url = f"{self.api_url}/{self.phone_number_id}/messages"
            
            # Headers
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Build the interactive message payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_number,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {
                        "text": body_text
                    },
                    "action": {
                        "button": button_text,
                        "sections": sections
                    }
                }
            }
            
            # Add header if provided
            if header_text:
                payload["interactive"]["header"] = {
                    "type": "text",
                    "text": header_text
                }
            
            # Add footer if provided
            if footer_text:
                payload["interactive"]["footer"] = {
                    "text": footer_text
                }
            
            # Send the request
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload
                )
                
                # Check response
                if response.status_code == 200:
                    logger.info(f"Successfully sent interactive list message to {to_number}")
                    return True
                else:
                    logger.error(f"Failed to send interactive list message: {response.text}")
                    return False
            
        except Exception as e:
            logger.error(f"Error sending interactive list message: {str(e)}")
            return False
    
    async def send_button_message(
        self, 
        to_number: str, 
        body_text: str,
        buttons: List[Dict[str, Any]],
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None
    ) -> bool:
        """
        Send a button message to a WhatsApp number.
        
        Args:
            to_number: The recipient's phone number (with country code, no +)
            body_text: The main message text
            buttons: List of button objects, each with type and reply properties
            header_text: Optional header text
            footer_text: Optional footer text
            
        Returns:
            bool: True if the message was sent successfully, False otherwise
        """
        try:
            # Ensure number is in the right format
            if to_number.startswith("+"):
                to_number = to_number[1:]
            
            # API endpoint
            url = f"{self.api_url}/{self.phone_number_id}/messages"
            
            # Headers
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Build the interactive message payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": body_text
                    },
                    "action": {
                        "buttons": buttons
                    }
                }
            }
            
            # Add header if provided
            if header_text:
                payload["interactive"]["header"] = {
                    "type": "text",
                    "text": header_text
                }
            
            # Add footer if provided
            if footer_text:
                payload["interactive"]["footer"] = {
                    "text": footer_text
                }
            
            # Send the request
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload
                )
                
                # Check response
                if response.status_code == 200:
                    logger.info(f"Successfully sent button message to {to_number}")
                    return True
                else:
                    logger.error(f"Failed to send button message: {response.text}")
                    return False
            
        except Exception as e:
            logger.error(f"Error sending button message: {str(e)}")
            return False
    
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
        if mode == "subscribe" and token == self.verify_token:
            logger.info("WEBHOOK_VERIFIED")
            return challenge
        
        logger.warning("Webhook verification failed")
        return None
    
    def process_webhook_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a webhook payload from WhatsApp Cloud API.
        
        Args:
            payload: The webhook payload
            
        Returns:
            Dict: Structured information extracted from the payload
        """
        # Generate request ID for consistent logging
        import time
        import json  # Make sure json is imported
        request_id = f"req_{int(time.time())}"
        
        try:
            # Log entire payload structure at debug level
            logger.debug(f"[{request_id}] Processing webhook payload structure: {json.dumps(payload)}")
            
            # Extract value object (can be different based on payload structure)
            if not payload.get("entry"):
                logger.warning(f"[{request_id}] Webhook payload missing 'entry' field")
                return {}
            
            entry = payload.get("entry", [{}])[0]
            logger.debug(f"[{request_id}] Entry data: {json.dumps(entry)}")
            
            if not entry.get("changes"):
                logger.warning(f"[{request_id}] Entry missing 'changes' field")
                return {}
            
            changes = entry.get("changes", [{}])[0]
            logger.debug(f"[{request_id}] Changes data: {json.dumps(changes)}")
            
            value = changes.get("value", {})
            logger.debug(f"[{request_id}] Value data: {json.dumps(value)}")
            
            # Get messaging product
            messaging_product = value.get("messaging_product")
            logger.info(f"[{request_id}] Messaging product: {messaging_product}")
            
            if messaging_product != "whatsapp":
                logger.warning(f"[{request_id}] Received non-WhatsApp webhook: {messaging_product}")
                return {}
            
            # Extract messages
            messages = value.get("messages", [])
            logger.info(f"[{request_id}] Number of messages in payload: {len(messages)}")
            
            if not messages:
                # Check if this is a status update
                statuses = value.get("statuses", [])
                if statuses:
                    status = statuses[0]
                    status_id = status.get("id")
                    status_recipient_id = status.get("recipient_id")
                    status_status = status.get("status")  # delivered, read, etc.
                    status_timestamp = status.get("timestamp")
                    
                    logger.info(f"[{request_id}] Message status update - ID: {status_id}, Recipient: {status_recipient_id}, Status: {status_status}, Timestamp: {status_timestamp}")
                    return {
                        "type": "status_update",
                        "status": status_status,
                        "message_id": status_id,
                        "recipient_id": status_recipient_id,
                        "timestamp": status_timestamp,
                        "request_id": request_id
                    }
                
                logger.info(f"[{request_id}] No messages or statuses in webhook payload")
                return {}
            
            # Get the first message
            message = messages[0]
            logger.debug(f"[{request_id}] Message data: {json.dumps(message)}")
            
            # Extract message details
            message_type = message.get("type")
            from_number = message.get("from")
            message_id = message.get("id")
            timestamp = message.get("timestamp")
            
            logger.info(f"[{request_id}] Message details - Type: {message_type}, From: {from_number}, ID: {message_id}, Timestamp: {timestamp}")
            
            # Extract message content based on type
            body = ""
            interactive_data = {}
            
            if message_type == "text":
                text_data = message.get("text", {})
                body = text_data.get("body", "")
                logger.info(f"[{request_id}] Text message content: {body}")
                
            elif message_type == "interactive":
                interactive = message.get("interactive", {})
                interactive_type = interactive.get("type")
                logger.info(f"[{request_id}] Interactive message type: {interactive_type}")
                
                if interactive_type == "list_reply":
                    list_reply = interactive.get("list_reply", {})
                    body = list_reply.get("title", "")
                    logger.info(f"[{request_id}] List reply - ID: {list_reply.get('id')}, Title: {body}, Description: {list_reply.get('description')}")
                    
                    interactive_data = {
                        "reply_type": "list_reply",
                        "id": list_reply.get("id"),
                        "title": list_reply.get("title"),
                        "description": list_reply.get("description")
                    }
                    
                elif interactive_type == "button_reply":
                    button_reply = interactive.get("button_reply", {})
                    body = button_reply.get("title", "")
                    logger.info(f"[{request_id}] Button reply - ID: {button_reply.get('id')}, Title: {body}")
                    
                    interactive_data = {
                        "reply_type": "button_reply",
                        "id": button_reply.get("id"),
                        "title": button_reply.get("title")
                    }
            elif message_type == "image":
                image_data = message.get("image", {})
                image_id = image_data.get("id", "")
                image_mime = image_data.get("mime_type", "")
                image_sha = image_data.get("sha256", "")
                caption = image_data.get("caption", "")
                body = caption or "Image message"
                logger.info(f"[{request_id}] Image message - ID: {image_id}, MIME: {image_mime}, Caption: {caption}")
            elif message_type == "document":
                doc_data = message.get("document", {})
                doc_id = doc_data.get("id", "")
                doc_mime = doc_data.get("mime_type", "")
                filename = doc_data.get("filename", "")
                body = f"Document: {filename}" if filename else "Document message"
                logger.info(f"[{request_id}] Document message - ID: {doc_id}, MIME: {doc_mime}, Filename: {filename}")
            elif message_type == "location":
                location_data = message.get("location", {})
                latitude = location_data.get("latitude", "")
                longitude = location_data.get("longitude", "")
                body = f"Location: {latitude},{longitude}"
                logger.info(f"[{request_id}] Location message - Lat: {latitude}, Long: {longitude}")
            
            # Log the message data
            logger.info(f"[{request_id}] Processed message: type={message_type}, body={body}, interactive_data={json.dumps(interactive_data)}")
            
            # Return structured information
            result = {
                "from_number": from_number,
                "message_type": message_type,
                "message_id": message_id,
                "body": body,
                "interactive_data": interactive_data,
                "timestamp": timestamp,
                "request_id": request_id
            }
            
            logger.debug(f"[{request_id}] Extracted payload result: {json.dumps(result)}")
            return result
            
        except Exception as e:
            logger.error(f"[{request_id}] Error processing webhook payload: {str(e)}", exc_info=True)
            # Log the payload that caused the error for debugging
            try:
                logger.error(f"[{request_id}] Problem payload: {json.dumps(payload)}")
            except:
                logger.error(f"[{request_id}] Could not serialize problem payload")
            return {} 