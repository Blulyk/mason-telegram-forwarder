import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv, dotenv_values
from telethon import TelegramClient, events


env_file = os.getenv("ENV_FILE", ".env")
load_dotenv(env_file)
if env_file != ".env":
    load_dotenv(".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing {name}")
    return value


def parse_source_chat(source_chat: str):
    source_chat = source_chat.strip()

    try:
        return int(source_chat)
    except ValueError:
        pass

    if source_chat.startswith("https://t.me/"):
        return source_chat.removeprefix("https://t.me/").strip("/")

    if source_chat.startswith("http://t.me/"):
        return source_chat.removeprefix("http://t.me/").strip("/")

    return source_chat


def wait_for_config(path: str):
    if path == ".env":
        return

    while not Path(path).exists():
        logging.warning("Waiting for config file: %s", path)
        time.sleep(10)


wait_for_config(env_file)
load_dotenv(env_file, override=True)

api_id = int(require_env("TELEGRAM_API_ID"))
api_hash = require_env("TELEGRAM_API_HASH")
source_chat = require_env("SOURCE_CHAT")
webhook_url = require_env("N8N_WEBHOOK_URL")
session_name = os.getenv("SESSION_NAME", "telegram_forwarder_session")

session_path = Path(session_name).expanduser()
if session_path.parent != Path("."):
    session_path.parent.mkdir(parents=True, exist_ok=True)

source_chat_parsed = parse_source_chat(source_chat)
client = TelegramClient(str(session_path), api_id, api_hash)


@client.on(events.NewMessage(chats=source_chat_parsed))
async def handler(event):
    message = event.message

    payload = {
        "chat_id": event.chat_id,
        "message_id": message.id,
        "sender_id": message.sender_id,
        "text": event.raw_text or "",
        "date": message.date.isoformat() if message.date else None,
        "has_media": bool(message.media),
        "grouped_id": str(message.grouped_id) if message.grouped_id else None,
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("Message %s forwarded to n8n", message.id)
    except Exception:
        logging.exception("Failed to send message %s to n8n", message.id)


async def main():
    me = await client.get_me()
    username = getattr(me, "username", None) or getattr(me, "first_name", None) or me.id
    logging.info("Logged in as: %s", username)
    logging.info("Listening to chat: %s", source_chat_parsed)


if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
        client.run_until_disconnected()
