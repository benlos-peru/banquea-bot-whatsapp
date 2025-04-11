# WhatsApp Bot Implementation Notes

## User Flow
1. **Initial Contact**
   - Users added to database (state: UNCONTACTED)
   - API request triggers contact process
   - Send "bienvenida" template message
   - Send "seleccion_dia" template message
   - Change user state to AWAITING_DAY

2. **Day Selection**
   - User responds with Spanish weekday name (capitalized first letter)
   - Save day selection to database
   - Send "seleccion_hora" template message
   - Change user state to AWAITING_HOUR

3. **Hour Selection**
   - User responds with hour (0-23)
   - Save hour selection to database
   - Send confirmation message (regular text)
   - Change user state to SUBSCRIBED

## Spanish Day Mapping
- "Lunes" -> 0 (Monday)
- "Martes" -> 1 (Tuesday)
- "Miércoles" -> 2 (Wednesday)
- "Jueves" -> 3 (Thursday)
- "Viernes" -> 4 (Friday)
- "Sábado" -> 5 (Saturday)
- "Domingo" -> 6 (Sunday)

## Message Templates
1. **bienvenida**: Initial welcome template
   - Content: Introduction to the medical question service
   - Used when: First contact with user

2. **seleccion_dia**: Day selection template
   - Content: Asks user to select a day of the week
   - Used when: After welcome message

3. **seleccion_hora**: Hour selection template
   - Content: Asks user to select an hour (0-23)
   - Used when: After day selection

## API Endpoints
1. **/users/** - CRUD operations for users
2. **/users/contact/** - Trigger contact process for uncontacted users
3. **/webhook** - WhatsApp webhook for receiving messages

## Implementation Requirements
1. **WebHook Handling**:
   - Process incoming messages based on user state
   - Extract message content (text, interactive responses)
   - Update user state after each successful interaction
   - Store WhatsApp ID when first message is received

2. **User Contact Process**:
   - Endpoint to trigger contact flow for users
   - Send template messages in proper sequence
   - Track message delivery status

3. **Future Considerations**:
   - Scheduling system for sending questions
   - Question selection logic
   - Answer tracking and feedback

## Important Notes
- Webhook calls can be days apart - always retrieve current user state from DB
- All user interactions are in Spanish
- Templates must be pre-approved in WhatsApp Business Platform
- API requests need proper authentication
