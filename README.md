# Banquea WhatsApp Bot

A WhatsApp bot that sends medical questions to users on a scheduled basis.

## Features

- Users can select when they want to receive medical questions (day and time)
- Questions are sent as interactive messages with multiple choice answers
- Users receive feedback on their answers
- Scheduled delivery of questions based on user preferences
- Special command to force a new question at any time
- Different conversation flows for first-time vs. returning users
- Bulk messaging capabilities to initiate conversations with users

## Architecture

- FastAPI backend with webhook for WhatsApp Cloud API
- SQLite database for storing user information and conversation states
- In-memory cache for questions and options
- APScheduler for scheduled message delivery

## Setup

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Configure WhatsApp Cloud API credentials in `.env` file:
   ```
   WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
   WHATSAPP_BUSINESS_ACCOUNT_ID=your_business_account_id
   WHATSAPP_ACCESS_TOKEN=your_access_token
   WHATSAPP_VERIFY_TOKEN=your_verify_token
   ```
4. Run the server:
   ```
   python main.py
   ```

## WhatsApp Integration

To integrate with WhatsApp Cloud API:

1. Create a developer account on [Meta for Developers](https://developers.facebook.com/)
2. Create a WhatsApp Business App
3. Set up webhook with the verify token from your `.env` file
4. Add the required templates to your WhatsApp Business Manager:
   - `bienvenida_banquea`: Initial welcome template with Yes/No buttons (first-time users)
   - `confirmacion_pregunta`: Template asking if user wants to receive a question (returning users)
   - `seleccion_fecha`: Template for selecting day of week

## Testing

You can use the provided script to send a test question to a user:

```
python send_question.py +123456789
```

## Conversation Flow

The bot maintains different conversation flows based on user history:

### First-time Users:
1. User sends "hola" to start
2. Bot asks if they want to receive questions (bienvenida_banquea template)
3. If Yes, bot asks for day preference using interactive list
4. Bot asks for time preference (hour of day)
5. Bot confirms schedule and sends first question

### Returning Users:
1. User sends "hola" to start
2. Bot asks if they're ready for a new question (confirmacion_pregunta template)
3. If Yes, bot immediately sends a new question
4. User can always force a new question with command `%%force_new_question`

## Bulk Messaging

The system includes a script for sending bulk messages to users in the database:

```bash
# Send to 100 users (default)
python send_bulk_messages.py

# Send to a specific number of users
python send_bulk_messages.py --limit=50
```

The script:
- Identifies uncontacted users in the database
- Distinguishes between first-time and returning users
- Sends the appropriate template based on user history
- Updates user status in the database
- Includes delay between messages to avoid rate limiting

## Database

The system uses the following tables:
- Users: Store user information, preferences and conversation state
- Questions: Questions loaded from CSV files
- User Responses: Track user answers for analytics

## Development

The main components are:
- `app/routes.py`: Main webhook handler and conversation logic
- `app/whatsapp.py`: WhatsApp API client for sending messages
- `app/models.py`: Database models
- `app/scheduler.py`: Scheduled tasks for sending questions
- `app/utils.py`: Utility functions for loading and processing data

## Características

- Envío de preguntas médicas aleatorias a usuarios de forma semanal
- Configuración de día y hora preferida por cada usuario
- Captura de respuestas y feedback sobre respuestas correctas/incorrectas
- Blacklist para números que no responden
- API de administración para gestionar usuarios y preguntas

## Requisitos

- Python 3.8+
- FastAPI
- SQLAlchemy
- Pandas
- APScheduler
- Cuenta de Meta Developer
- Número de teléfono registrado para WhatsApp Business

## Instalación

1. Clonar el repositorio:

```bash
git clone https://github.com/your-username/banquea-bot-whatsapp.git
cd banquea-bot-whatsapp
```

2. Crear un entorno virtual:

```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instalar dependencias:

```bash
pip install -r requirements.txt
```

4. Configurar variables de entorno:

```bash
cp .env.example .env
# Editar .env con tus configuraciones
```

## Configuración de WhatsApp Cloud API

Para utilizar la API de WhatsApp Cloud, necesitas seguir estos pasos:

1. **Crear una cuenta en Meta for Developers**:
   - Regístrate en [Meta for Developers](https://developers.facebook.com/)
   - Crea un nuevo proyecto o aplicación

2. **Configurar WhatsApp Business**:
   - Ve a la sección "WhatsApp" > "Getting Started" en tu aplicación
   - Sigue los pasos para configurar tu cuenta de WhatsApp Business
   - Registra un número de teléfono para pruebas o usa un número de teléfono de negocios

3. **Obtener credenciales**:
   - Número de teléfono ID: Se encuentra en la sección "WhatsApp" > "API Setup"
   - ID de cuenta Business: Se encuentra en "WhatsApp" > "Configuration"
   - Token de acceso: Crea un token de acceso permanente en "System Users"

4. **Configurar el Webhook**:
   - En la sección "Webhooks" > "Configure"
   - URL del webhook: `https://tu-dominio.com/webhook`
   - Token de verificación: Usa el mismo que configuraste en `.env` como `WHATSAPP_VERIFY_TOKEN`
   - Selecciona al menos los campos `messages` y `message_deliveries`

5. **Configurar plantillas de mensajes** (Opcional, pero recomendado):
   - Ve a "WhatsApp" > "Message Templates"
   - Crea plantillas para los mensajes iniciales (necesario para enviar el primer mensaje a un usuario)

6. **Actualiza tu archivo `.env`**:
   ```
   WHATSAPP_PHONE_NUMBER_ID=tu_phone_number_id
   WHATSAPP_BUSINESS_ACCOUNT_ID=tu_business_account_id
   WHATSAPP_ACCESS_TOKEN=tu_access_token
   WHATSAPP_VERIFY_TOKEN=tu_verify_token
   ```

7. **Configurar un dominio con SSL**:
   - La API de WhatsApp Cloud solo funciona con webhooks HTTPS
   - Asegúrate de que tu servidor tenga un certificado SSL válido

## Uso

1. Iniciar el servidor:

```bash
python main.py
```

El servidor se ejecutará en `http://localhost:8000` (o el puerto definido en `.env`).

## Endpoints

### API públicos

- `GET /` - Verificación de salud de la API
- `GET /webhook` - Punto de verificación para WhatsApp Cloud API
- `POST /webhook` - Webhook para recibir mensajes de WhatsApp

### API de administración

- `POST /admin/blacklist/{phone_number}` - Agregar un número a la blacklist
- `POST /admin/load-questions` - Cargar preguntas desde archivos CSV
- `GET /admin/users` - Obtener lista de usuarios

## Configuración para Digital Ocean

Para desplegar en un Droplet de Digital Ocean:

1. Crear un Droplet con Ubuntu
2. Conectarse al Droplet por SSH
3. Instalar Python y dependencias:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv nginx -y
```

4. Clonar el repositorio y configurar como se indica en la sección de instalación
5. Configurar Nginx como proxy inverso:

```bash
sudo nano /etc/nginx/sites-available/banquea-bot
```

Agregar:

```
server {
    listen 80;
    server_name your_domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

6. Configurar SSL con Let's Encrypt (requerido para WhatsApp Cloud API):

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your_domain.com
```

7. Activar la configuración y reiniciar Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/banquea-bot /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

8. Configurar el servicio systemd para mantener la API ejecutándose:

```bash
sudo nano /etc/systemd/system/banquea-bot.service
```

Agregar:

```
[Unit]
Description=Banquea WhatsApp Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/banquea-bot-whatsapp
ExecStart=/home/ubuntu/banquea-bot-whatsapp/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

9. Iniciar y habilitar el servicio:

```bash
sudo systemctl start banquea-bot
sudo systemctl enable banquea-bot
```

## Estructura de archivos CSV

El bot utiliza tres archivos CSV ubicados en la carpeta `preguntas/`:

- `preguntas.csv` - Contiene las preguntas
- `respuestas_correctas.csv` - Contiene las respuestas correctas
- `respuestas_incorrectas.csv` - Contiene las respuestas incorrectas

## Licencia

[MIT](LICENSE) 