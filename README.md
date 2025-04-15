# Banquea WhatsApp Bot

Bot de WhatsApp para envío programado de preguntas médicas y gestión de usuarios, construido con FastAPI, SQLite y la API Cloud de WhatsApp.

---

## Tabla de Contenidos
- [Descripción General](#descripción-general)
- [Arquitectura y Componentes](#arquitectura-y-componentes)
- [Instalación y Configuración](#instalación-y-configuración)
- [Flujo de Usuario y Conversación](#flujo-de-usuario-y-conversación)
- [Templates de WhatsApp](#templates-de-whatsapp)
- [Endpoints y Funciones Principales](#endpoints-y-funciones-principales)
- [Explicación de Archivos](#explicación-de-archivos)
- [Recomendaciones y Notas](#recomendaciones-y-notas)

---

## Descripción General
Este bot permite enviar preguntas médicas a usuarios de WhatsApp en horarios y días personalizados. Los usuarios pueden seleccionar cuándo recibir preguntas, responder con opciones interactivas y recibir retroalimentación inmediata. El sistema gestiona el estado de cada usuario y soporta mensajes masivos y flujos diferenciados para nuevos y antiguos usuarios.

---

## Arquitectura y Componentes
- **Backend:** FastAPI expone endpoints REST y el webhook para WhatsApp.
- **Base de datos:** SQLite (vía SQLAlchemy) almacena usuarios, estados y preferencias.
- **WhatsApp API:** Comunicación con WhatsApp Cloud API para envío/recepción de mensajes, plantillas y listas interactivas.
- **Scheduler:** APScheduler programa el envío automático de preguntas según preferencias del usuario.
- **Scripts CLI:** Herramientas para gestión de usuarios y mensajes masivos.

---

## Instalación y Configuración
1. **Clona el repositorio:**
   ```sh
   git clone <repo_url>
   cd banquea-bot-whatsapp
   ```
2. **Instala dependencias:**
   ```sh
   pip install -r requirements.txt
   ```
3. **Configura variables de entorno en `.env`:**
   - `WHATSAPP_PHONE_NUMBER_ID`
   - `WHATSAPP_BUSINESS_ACCOUNT_ID`
   - `WHATSAPP_ACCESS_TOKEN`
   - `WHATSAPP_VERIFY_TOKEN`
4. **Ejecuta el servidor:**
   ```sh
   uvicorn main:app --reload
   ```
5. **Configura el Webhook en Meta Developers:**
   - Usa el endpoint `/webhook` y el token de verificación.
   - Agrega y aprueba los templates necesarios en WhatsApp Business Manager.

---

## Flujo de Usuario y Conversación
1. **Primer contacto:**
   - El usuario envía "hola".
   - El bot responde con el template `bienvenida` (botones Sí/No).
   - Si acepta, se solicita día (`seleccion_dia`) y hora (`seleccion_hora_minuto`).
   - Se confirma el horario y se envía la primera pregunta.
2. **Usuarios recurrentes:**
   - El usuario puede forzar una nueva pregunta con `%%get_new_question$`.
   - El bot pregunta si desea recibir una nueva pregunta (`confirmacion_pregunta`).
   - Si acepta, se envía la pregunta inmediatamente.
3. **Respuestas:**
   - Las preguntas se envían como mensajes interactivos (listas o botones).
   - El usuario recibe retroalimentación inmediata.

---

## Templates de WhatsApp
- **bienvenida:** Mensaje inicial con botones Sí/No.
- **seleccion_dia:** Lista interactiva para elegir día de la semana.
- **seleccion_hora:** Lista o botones para elegir hora (0-23).
- **confirmacion_pregunta:** Confirmación para recibir nueva pregunta.
- **Otros:** Mensajes de retroalimentación y confirmación.

> **Nota:** Todos los templates deben ser preaprobados en WhatsApp Business Platform y estar en español.

---

## Endpoints y Funciones Principales
- **`POST /webhook`**
  - Recibe mensajes y actualizaciones de WhatsApp.
  - Procesa el payload, extrae datos y delega al manejador de mensajes.
- **`/users/`**
  - CRUD de usuarios (crear, listar, actualizar, eliminar).
- **`/users/contact/`**
  - Inicia el flujo de contacto para usuarios no contactados.
- **Scripts CLI:**
  - `manage_users.py`: Añadir, listar, resetear o eliminar usuarios desde consola.

---

## Explicación de Archivos
- **main.py:** Punto de entrada, inicializa FastAPI y rutas.
- **src/webhook.py:** Define el endpoint `/webhook`, procesa mensajes entrantes y delega según el estado del usuario.
- **src/whatsapp.py:** Cliente para la API de WhatsApp. Métodos para enviar mensajes de texto, plantillas y listas interactivas. Procesa los payloads entrantes y extrae información relevante.
- **src/message_handler.py:** Lógica de conversación y cambio de estado del usuario.
- **src/models.py:** Modelos de base de datos (User, UserState).
- **src/crud.py:** Funciones CRUD para usuarios y estados.
- **src/scheduler.py:** Programación de envíos automáticos según preferencias.
- **src/questions.py:** Carga y gestión de preguntas/respuestas desde CSV en `preguntas/`.
- **src/schemas.py:** Esquemas Pydantic para validación de datos.
- **src/database.py:** Configuración de la base de datos y sesión.
- **src/constants.py:** Constantes globales.
- **manage_users.py:** Script CLI para gestión de usuarios (añadir, listar, resetear, eliminar).
- **preguntas/**: CSVs con preguntas y respuestas correctas/incorrectas.
- **requirements.txt:** Dependencias del proyecto.
- **.env:** Variables de entorno sensibles.
- **notes.md:** Notas técnicas, mapeo de días, templates y detalles de implementación.

---

## Recomendaciones y Notas
- **Siempre consulta el estado actual del usuario en la BD antes de responder.**
- **Todos los mensajes y templates deben estar en español.**
- **Asegúrate de que los templates estén aprobados en WhatsApp Business Platform.**
- **El webhook puede recibir mensajes días después, la lógica debe ser robusta.**
- **Protege los endpoints administrativos con autenticación si se exponen públicamente.**
- **Personaliza los CSV de preguntas según la especialidad médica deseada.**

---
