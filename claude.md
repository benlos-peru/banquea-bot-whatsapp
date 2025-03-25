# Banquea WhatsApp Bot - Important Notes

## Bot Purpose
- Send medical questions to users on a scheduled basis
- Process user responses and provide feedback
- Allow users to set their own schedule for receiving questions

## Conversation Flow
1. User initiates conversation (sends "hola")
2. Bot sends template based on user history:
   - First-time users: "bienvenida_banquea" template with Yes/No options
   - Returning users: "confirmacion_pregunta" template asking if they're ready for a new question
3. If No, send goodbye message
4. If Yes, first-time users move to day selection, returning users get a question immediately
5. New user selects day, bot asks for hour (untemplated)
6. User provides hour, bot confirms schedule and sends first question
7. Bot sends questions on schedule
8. After user answers, bot provides feedback on correctness

## Templates
- **bienvenida_banquea**: Initial welcome template with Yes/No buttons (for first-time users)
- **confirmacion_pregunta**: Template asking if they want to receive a question (for returning users)
- **seleccion_fecha**: Template for selecting day of week

## State Machine
- INITIAL (0): New user or reset state
- AWAITING_CONFIRMATION (1): Waiting for Yes/No after welcome message
- AWAITING_DAY (2): Waiting for day selection
- AWAITING_HOUR (3): Waiting for hour input
- SUBSCRIBED (4): User has completed setup
- AWAITING_QUESTION_RESPONSE (5): Waiting for answer to question

## Special Commands
- **%%force_new_question**: Sends a new question immediately

## Message Types
- Interactive button messages (Yes/No responses)
- Interactive list messages (day selection, question answers)
- Text messages (hour selection, commands)

## Database Design
- User table tracks conversation state, preferences, and last question
- Questions stored in in-memory cache for performance
- User responses tracked for analytics

## Technical Implementation
- FastAPI as web framework
- SQLAlchemy for database ORM
- APScheduler for sending questions on schedule
- WhatsApp Cloud API for messaging

## Interactive List Format
- Question ID format: q_{question_id}_opt_{option_number}
- Day selection format: day_{0-6}
- Button IDs: yes_button/no_button

## Important API Details
- Webhook verification is GET request
- Incoming messages are POST requests to webhook endpoint
- Templates must be pre-approved in WhatsApp Business Manager

## Bulk Messaging
- Script `send_bulk_messages.py` sends templates to uncontacted users
- Differentiates between first-time and returning users
- Sends appropriate template based on user history
- Updates user state after sending message
- Limits to 100 users by default to avoid rate limiting
- Command-line option to adjust limit: `python send_bulk_messages.py --limit=50` 