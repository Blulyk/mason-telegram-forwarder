# Telegram Forwarder hacia n8n

Este proyecto escucha mensajes nuevos de un chat concreto de Telegram usando Telethon con una cuenta real de Telegram, y envía cada mensaje como JSON a un webhook de n8n.

No usa un bot para leer el chat origen. Telethon inicia sesión como cliente de una cuenta normal de Telegram.

## Archivos

- `app.py`: servicio principal.
- `web.py`: panel web de gestion.
- `list_chats.py`: lista tus chats para encontrar `SOURCE_CHAT`.
- `requirements.txt`: dependencias Python.
- `.env.example`: plantilla de configuración sin secretos.
- `Dockerfile`: imagen del servicio.
- `docker-compose.yml`: interfaz web y forwarder con reinicio automático.
- `data/`: carpeta persistente para la sesión de Telethon cuando se usa Docker.
- `umbrel-app-store.yml`, `mason-telegram-forwarder/` y `mason-waha/`: tienda comunitaria de Umbrel con Telegram Forwarder y WAHA.

## Conseguir TELEGRAM_API_ID y TELEGRAM_API_HASH

1. Entra en https://my.telegram.org.
2. Inicia sesión con tu cuenta de Telegram.
3. Ve a `API development tools`.
4. Crea una aplicación.
5. Copia `api_id` y `api_hash`.

Guarda esos valores solo en `.env`. No los pegues en el código ni los subas a Git.

## Configurar .env

Copia la plantilla:

```bash
cp .env.example .env
```

Edita `.env`:

```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SOURCE_CHAT=-1001234567890
N8N_WEBHOOK_URL=https://mi-dominio.com/webhook/telegram-forward
SESSION_NAME=/data/telegram_forwarder_session
MAX_MEDIA_BYTES=10485760
```

`SOURCE_CHAT` puede ser:

- un ID numérico, por ejemplo `-1001234567890`
- varios IDs separados por coma, por ejemplo `-1001234567890,-1009876543210`
- un username, por ejemplo `mi_canal`
- un enlace tipo `https://t.me/mi_canal`

Si cada valor parece número, el script lo convierte a `int`. Para varios chats se recomienda usar IDs numéricos.

## Panel web

Con Docker Compose puedes levantar la interfaz:

```bash
docker compose up -d --build
```

Abre:

```text
http://localhost:8080
```

Desde el panel puedes:

- guardar `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `SOURCE_CHAT` y `N8N_WEBHOOK_URL`
- pedir el código de Telegram
- completar login con código y 2FA
- listar chats
- probar el webhook de n8n

El forwarder lee la configuración desde:

```text
./data/config.env
```

Si cambias `SOURCE_CHAT` o `N8N_WEBHOOK_URL`, reinicia el servicio para aplicar la nueva configuración:

```bash
docker compose restart forwarder
```

## Primer login con Telegram

La primera ejecución tiene que ser interactiva para crear el archivo de sesión.

Con Docker Compose:

```bash
docker compose up -d --build
```

Despues entra en `http://localhost:8080` y usa la seccion `Login Telegram`.

También puedes hacerlo sin Docker:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Pasos del login:

1. Crea `.env` desde `.env.example`.
2. Rellena `TELEGRAM_API_ID` y `TELEGRAM_API_HASH`.
3. Ejecuta `python app.py` manualmente la primera vez.
4. Introduce el teléfono con prefijo internacional, por ejemplo `+34XXXXXXXXX`.
5. Introduce el código que llega a Telegram.
6. Introduce la contraseña 2FA si la cuenta la tiene.
7. Verifica que se crea el archivo de sesión.
8. Para el script con `Ctrl+C`.
9. Déjalo arrancando como servicio con Docker Compose.

Con la configuración de Docker, la sesión queda en:

```text
./data/telegram_forwarder_session.session
```

Ese archivo permite volver a arrancar sin pedir código cada vez.

## Listar chats

Después del primer login, ejecuta:

```bash
docker compose run --rm web python list_chats.py
```

O sin Docker:

```bash
python list_chats.py
```

Verás algo así:

```text
Nombre del chat => -1001234567890
```

Copia el ID correcto en `SOURCE_CHAT`.

## Configurar n8n

1. Crea un workflow nuevo en n8n.
2. Añade un nodo `Webhook`.
3. Método: `POST`.
4. Path: `telegram-forward`.
5. Prueba primero con la Test URL.
6. Cuando funcione, copia la Production URL.
7. Pon la Production URL en `N8N_WEBHOOK_URL`.
8. Activa el workflow.

Importante: si usas la Production URL, el workflow debe estar activo. La Test URL solo funciona mientras n8n está escuchando la prueba.

El JSON recibido tendrá esta forma:

```json
{
  "chat_id": -1001234567890,
  "message_id": 123,
  "sender_id": 987654321,
  "text": "Mensaje recibido",
  "date": "2026-05-12T12:34:56+00:00",
  "has_media": false,
  "grouped_id": null
}
```

Desde n8n puedes reenviar ese contenido a WhatsApp usando el proveedor que prefieras, por ejemplo WhatsApp Cloud API, Twilio, Evolution API, Waha u otro gateway compatible.

Cuando el mensaje de Telegram incluye una foto, el forwarder anade estos campos:

```json
{
  "has_media": true,
  "media_type": "photo",
  "media_mime_type": "image/jpeg",
  "media_filename": "telegram_123.jpg",
  "media_size": 123456,
  "media_base64": "..."
}
```

`text` contiene el caption si la foto venia con texto. `MAX_MEDIA_BYTES` limita el tamano maximo de la imagen descargada desde Telegram; por defecto son 10 MB.

## n8n: texto, foto y foto con texto hacia WAHA

Para reenviar a WhatsApp con WAHA, deja el Webhook de Telegram Forwarder como entrada y anade un nodo `IF`.

Importante: WAHA Core gratis envia texto con `sendText`, pero `sendImage` requiere WAHA Plus en el motor `NOWEB`. Si usas WAHA Core, el forwarder seguira entregando la foto a n8n como base64, pero necesitas WAHA Plus u otro sender compatible con envio de imagenes a grupos para completar el reenvio multimedia.

Condicion del `IF`:

```text
{{$json.body.media_base64}}
```

Si existe `media_base64`, llama a WAHA `sendImage`:

```text
POST http://192.168.1.153:3000/api/sendImage
```

Headers:

```text
Accept: application/json
Content-Type: application/json
X-Api-Key: <API key de WAHA>
```

Body JSON:

```json
{
  "session": "default",
  "chatId": "120363424946565150@g.us",
  "file": {
    "mimetype": "{{$json.body.media_mime_type}}",
    "filename": "{{$json.body.media_filename}}",
    "data": "{{$json.body.media_base64}}"
  },
  "caption": "{{$json.body.text}}"
}
```

Si no existe `media_base64`, llama a WAHA `sendText`:

```text
POST http://192.168.1.153:3000/api/sendText
```

Body JSON:

```json
{
  "session": "default",
  "chatId": "120363424946565150@g.us",
  "text": "{{$json.body.text}}"
}
```

## Levantar como servicio

Cuando ya existe la sesión y `SOURCE_CHAT` está configurado:

```bash
docker compose up -d --build
```

El servicio tiene:

```yaml
restart: unless-stopped
```

Eso hace que se reinicie si falla y que vuelva a arrancar tras reiniciar el servidor, siempre que Docker arranque con el sistema.

## Ver logs

```bash
docker compose logs -f forwarder
```

Logs de la interfaz:

```bash
docker compose logs -f web
```

## Reiniciar

```bash
docker compose restart forwarder
docker compose restart web
```

## Umbrel Community App Store

El repositorio esta preparado como Community App Store de Umbrel:

```text
umbrel-app-store.yml
mason-telegram-forwarder/
  umbrel-app.yml
  docker-compose.yml
  exports.sh
  icon.svg
mason-waha/
  umbrel-app.yml
  docker-compose.yml
  exports.sh
  icon.svg
mason-whatsapp-bridge/
  umbrel-app.yml
  docker-compose.yml
  exports.sh
  icon.svg
```

Para instalarla como tienda comunitaria:

1. Espera a que GitHub Actions publique `ghcr.io/blulyk/telegram-forwarder:0.2.0`.
2. En Umbrel, ve a App Store y anade `https://github.com/Blulyk/mason-telegram-forwarder` como Community App Store.
3. Instala `Telegram Forwarder`, `WAHA` o `WhatsApp Bridge` desde la tienda comunitaria.

Si Umbrel no muestra la actualizacion, fuerza el refresco por SSH:

```bash
cd ~/umbrel
sudo scripts/repo update
sudo scripts/app update mason-telegram-forwarder
```

En versiones antiguas puede ser:

```bash
sudo ~/umbrel/scripts/repo update
sudo ~/umbrel/scripts/app update mason-telegram-forwarder
```

## WAHA en Umbrel para WhatsApp

La app `WAHA` usa la imagen oficial `devlikeapro/waha:noweb` y monta la carpeta persistente de sesiones en:

```text
${APP_DATA_DIR}/sessions -> /app/.sessions
```

La interfaz ya viene incluida en WAHA. Al abrir la app desde Umbrel entra directamente a:

```text
/dashboard
```

Credenciales y API key:

- Usuario: `admin`
- API key: el password de app que muestra Umbrel en `Show default credentials`.
- El dashboard queda protegido por Umbrel y no pide un segundo login propio de WAHA.
- El motor usado es `NOWEB`, mas ligero que `WEBJS` porque no levanta Chromium.

Primer setup:

1. Instala `WAHA` desde la tienda `Mason Apps`.
2. Abre la app y entra al dashboard.
3. Usa la API key que muestra Umbrel si el dashboard la pide para conectar con el servidor.
4. Arranca la sesion `default`.
5. Escanea el QR desde WhatsApp: `Dispositivos vinculados` -> `Vincular dispositivo`.
6. Espera a que la sesion quede en estado `WORKING`.

Para enviar desde n8n usando WAHA:

1. Anade un nodo `HTTP Request`.
2. Metodo: `POST`.
3. URL:

```text
http://umbrel.local:3000/api/sendText
```

Si n8n no resuelve `umbrel.local`, usa la IP de tu Umbrel:

```text
http://192.168.1.153:3000/api/sendText
```

4. Headers:

```text
Content-Type: application/json
Accept: application/json
X-Api-Key: <password/API key de WAHA en Umbrel>
```

5. Body JSON para un grupo:

```json
{
  "session": "default",
  "chatId": "120363000000000000@g.us",
  "text": "{{$json.body.text}}"
}
```

Los grupos de WhatsApp usan IDs terminados en `@g.us`. Puedes ver chats y grupos desde el dashboard de WAHA o desde Swagger en la misma app.

Seguridad:

- No publiques WAHA a Internet sin una capa extra de seguridad.
- Mantener `WAHA_API_KEY` activo es obligatorio para que `/api/*` no quede abierto.
- No borres la carpeta persistente de sesiones o tendras que escanear el QR otra vez.

## WhatsApp Bridge gratis para texto y fotos

`WhatsApp Bridge` es una alternativa ligera basada en `whatsapp-web.js` para enviar texto, fotos, y fotos con caption desde n8n sin WAHA Plus.

Primer setup:

1. Instala `WhatsApp Bridge` desde la tienda `Mason Apps`.
2. Abre la app.
3. Pega como API key la contraseña que muestra Umbrel en `Show default credentials`.
4. Escanea el QR desde WhatsApp.
5. Espera a que el estado sea `Conectado`.

Endpoint unico para n8n:

```text
POST http://192.168.1.153:8090/api/send
```

Headers:

```text
Accept: application/json
Content-Type: application/json
X-Api-Key: <API key de WhatsApp Bridge>
```

Texto solo:

```json
{
  "chatId": "120363424946565150@g.us",
  "text": "{{$json.body.text}}"
}
```

Foto sola o foto con caption:

```json
{
  "chatId": "120363424946565150@g.us",
  "text": "{{$json.body.text}}",
  "file": {
    "mimetype": "{{$json.body.media_mime_type}}",
    "filename": "{{$json.body.media_filename}}",
    "data": "{{$json.body.media_base64}}"
  }
}
```

Para evitar mandar `file` vacio en mensajes de texto, usa un nodo `IF` en n8n:

- Si `{{$json.body.media_base64}}` existe, manda el body con `file`.
- Si no existe, manda solo `chatId` y `text`.

## Parar

```bash
docker compose down
```

No borres `./data` si quieres conservar la sesión.

## Actualizar

Para actualizar dependencias o código:

```bash
docker compose up -d --build
```

No uses comandos que borren volúmenes o la carpeta `data`, porque perderías la sesión y tendrías que iniciar sesión otra vez.

## Seguridad

- No compartas `.env`.
- No compartas `*.session`.
- No subas `data/` a Git.
- El archivo `.session` equivale a una sesión iniciada de Telegram.
- Si sospechas que la sesión se ha expuesto, cierra sesiones desde Telegram y crea una nueva.
- No pegues `TELEGRAM_API_HASH` en chats, issues ni logs.

## Criterios de funcionamiento

- `python app.py` permite iniciar sesión con tu cuenta real de Telegram.
- `python list_chats.py` lista IDs de chats.
- `SOURCE_CHAT` limita la escucha a un solo chat.
- Cada mensaje nuevo genera un POST al webhook de n8n.
- Si n8n devuelve error, queda registrado en logs y el proceso sigue vivo.
- Docker Compose reinicia el servicio si falla.
- El archivo `.session` queda persistido en `./data`.
