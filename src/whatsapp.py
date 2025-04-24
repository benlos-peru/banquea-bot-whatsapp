import httpx
import os
from dotenv import load_dotenv
import json
import logging
import requests
import uuid
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
        
    def process_webhook_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming webhook payload from WhatsApp.
        
        Args:
            payload: The webhook payload from WhatsApp
            
        Returns:
            Dict with extracted message information
        """
        try:
            request_id = str(uuid.uuid4())[:8]  # Generate a short request ID for logging
            logger.info(f"[{request_id}] Processing webhook payload")
            
            # Check for required fields
            if "object" not in payload:
                logger.warning(f"[{request_id}] Missing 'object' field in payload")
                return {}
                
            if payload["object"] != "whatsapp_business_account":
                logger.warning(f"[{request_id}] Object is not 'whatsapp_business_account': {payload['object']}")
                return {}
                
            if "entry" not in payload or not payload["entry"]:
                logger.warning(f"[{request_id}] Missing 'entry' field in payload")
                return {}
                
            # Get the first entry
            entry = payload["entry"][0]
            logger.debug(f"[{request_id}] Entry data: {json.dumps(entry)}")
            
            if "changes" not in entry or not entry["changes"]:
                logger.warning(f"[{request_id}] Entry missing 'changes' field")
                return {}
            
            changes = entry["changes"][0]
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
            
            elif message_type == "button":
                # Handle direct button messages (from templates)
                button_data = message.get("button", {})
                body = button_data.get("text", "")
                payload = button_data.get("payload", "")
                
                logger.info(f"[{request_id}] Button message - Text: {body}, Payload: {payload}")
                
                # Treat button messages similar to button_reply for consistency
                interactive_data = {
                    "reply_type": "template_button",
                    "title": body,
                    "payload": payload
                }
            
            # Contact info if available
            contact_name = None
            if "contacts" in value and value["contacts"]:
                contact = value["contacts"][0]
                if "profile" in contact:
                    contact_name = contact["profile"].get("name")
                    logger.info(f"[{request_id}] Contact name: {contact_name}")
            
            # Log the message data
            logger.info(f"[{request_id}] Processed message: type={message_type}, body={body}, interactive_data={json.dumps(interactive_data)}")
            
            # Return structured information
            result = {
                "type": "message",
                "from_number": from_number,
                "message_type": message_type,
                "message_id": message_id,
                "body": body,
                "interactive_data": interactive_data,
                "timestamp": timestamp,
                "contact_name": contact_name,
                "request_id": request_id
            }
            
            logger.debug(f"[{request_id}] Extracted payload result: {json.dumps(result)}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing webhook payload: {str(e)}", exc_info=True)
            # Log the payload that caused the error for debugging
            try:
                logger.error(f"Problem payload: {json.dumps(payload)}")
            except:
                logger.error(f"Could not serialize problem payload")
            return {}
            
    async def send_text_message(self, to_number: str, message_text: str) -> bool:
        """
        Send a plain text message to a WhatsApp user.
        
        Args:
            to_number: The recipient's phone number
            message_text: The message text to send
            
        Returns:
            bool: True if successful, False otherwise
        """
        endpoint = f"{self.api_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message_text
            }
        }
        
        try:
            logger.info(f"Sending text message to {to_number}: {message_text[:50]}...")
            # Serialize payload preserving Unicode
            payload_str = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            response = requests.post(endpoint, headers=headers, data=payload_str)
            response_data = response.json()
            
            if response.status_code == 200:
                logger.info(f"Message sent successfully. Message ID: {response_data.get('messages', [{}])[0].get('id')}")
                return True
            else:
                logger.error(f"Failed to send message. Status code: {response.status_code}, Response: {json.dumps(response_data)}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}", exc_info=True)
            return False
            
    async def send_template_message(self, to_number: str, template_name: str, language: str = "es", components: List[Dict] = None) -> bool:
        """
        Send a template message to a WhatsApp user.
        
        Args:
            to_number: The recipient's phone number
            template_name: The name of the template to use
            language: The language code (default: "es")
            components: Template components for customization (optional)
            
        Returns:
            bool: True if successful, False otherwise
        """
        endpoint = f"{self.api_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8"
        }
        
        template_data = {
            "name": template_name,
            "language": {
                "code": language
            }
        }
        
        if components:
            template_data["components"] = components
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "template",
            "template": template_data
        }
        
        try:
            logger.info(f"Sending template message '{template_name}' to {to_number}")
            payload_str = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            response = requests.post(endpoint, headers=headers, data=payload_str)
            response_data = response.json()
            
            if response.status_code == 200:
                logger.info(f"Template message sent successfully. Message ID: {response_data.get('messages', [{}])[0].get('id')}")
                return True
            else:
                logger.error(f"Failed to send template message. Status code: {response.status_code}, Response: {json.dumps(response_data)}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending template message: {str(e)}", exc_info=True)
            return False
    
    async def send_interactive_list_message(self, to_number: str, header_text: str, body_text: str, footer_text: str, button_text: str, sections: List[Dict]) -> bool:
        """
        Send an interactive list message to a WhatsApp user.
        
        Args:
            to_number: The recipient's phone number
            header_text: Text for the header section
            body_text: Text for the main body section
            footer_text: Text for the footer section
            button_text: Text for the button that opens the list
            sections: List of sections with rows (options)
            
        Returns:
            bool: True if successful, False otherwise
        """
        endpoint = f"{self.api_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": header_text
                },
                "body": {
                    "text": body_text
                },
                "footer": {
                    "text": footer_text
                },
                "action": {
                    "button": button_text,
                    "sections": sections
                }
            }
        }
        
        try:
            logger.info(f"Sending interactive list message to {to_number}")
            payload_str = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            response = requests.post(endpoint, headers=headers, data=payload_str)
            response_data = response.json()
            
            if response.status_code == 200:
                logger.info(f"Interactive list message sent successfully. Message ID: {response_data.get('messages', [{}])[0].get('id')}")
                return True
            else:
                logger.error(f"Failed to send interactive list message. Status code: {response.status_code}, Response: {json.dumps(response_data)}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending interactive list message: {str(e)}", exc_info=True)
            return False