import logging
import os
import sqlite3
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
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


def parse_single_source_chat(source_chat: str):
    value = source_chat.strip()

    try:
        return int(value)
    except ValueError:
        pass

    if value.startswith("https://t.me/"):
        return value.removeprefix("https://t.me/").strip("/")

    if value.startswith("http://t.me/"):
        return value.removeprefix("http://t.me/").strip("/")

    return value


def parse_source_chats(source_chat: str):
    chats = [
        parse_single_source_chat(part)
        for part in source_chat.split(",")
        if part.strip()
    ]

    if not chats:
        raise RuntimeError("SOURCE_CHAT must include at least one chat")

    if len(chats) == 1:
        return chats[0]

    return chats


def wait_for_config(path: str):
    if path == ".env":
        return

    while not Path(path).exists():
        logging.warning("Waiting for config file: %s", path)
        time.sleep(10)


def session_file_for(session_name: str) -> Path:
    session_path = Path(session_name).expanduser()
    if str(session_path).endswith(".session"):
        return session_path
    return Path(f"{session_path}.session")


def wait_for_session(session_name: str):
    session_file = session_file_for(session_name)

    while not session_is_authorized(session_file):
        logging.warning(
            "Waiting for authorized Telegram session before starting forwarder: %s",
            session_file,
        )
        time.sleep(10)


def session_is_authorized(session_file: Path) -> bool:
    if not session_file.exists():
        return False

    try:
        connection = sqlite3.connect(f"file:{session_file}?mode=ro", uri=True, timeout=1)
        try:
            row = connection.execute(
                "select auth_key from sessions where auth_key is not null limit 1"
            ).fetchone()
            return bool(row and row[0])
        finally:
            connection.close()
    except sqlite3.Error:
        return False


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

wait_for_session(str(session_path))

source_chat_parsed = parse_source_chats(source_chat)
source_chat_list = (
    source_chat_parsed
    if isinstance(source_chat_parsed, list)
    else [source_chat_parsed]
)
source_chat_ids = {chat for chat in source_chat_list if isinstance(chat, int)}
source_chat_names = {chat for chat in source_chat_list if isinstance(chat, str)}
client = TelegramClient(str(session_path), api_id, api_hash)


@client.on(events.NewMessage())
async def handler(event):
    message = event.message
    chat_id = event.chat_id

    if chat_id not in source_chat_ids:
        return

    payload = {
        "chat_id": chat_id,
        "message_id": message.id,
        "sender_id": message.sender_id,
        "text": event.raw_text or "",
        "date": message.date.isoformat() if message.date else None,
        "has_media": bool(message.media),
        "grouped_id": str(message.grouped_id) if message.grouped_id else None,
    }

    logging.info(
        "Received monitored message %s from chat %s",
        message.id,
        chat_id,
    )

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("Message %s forwarded to n8n", message.id)
    except Exception:
        logging.exception("Failed to send message %s to n8n", message.id)


async def main():
    for source_chat_name in source_chat_names:
        entity = await client.get_entity(source_chat_name)
        resolved_chat_id = int(f"-100{entity.id}") if getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False) else entity.id
        source_chat_ids.add(resolved_chat_id)
        logging.info("Resolved source chat %s to %s", source_chat_name, resolved_chat_id)

    me = await client.get_me()
    username = getattr(me, "username", None) or getattr(me, "first_name", None) or me.id
    logging.info("Logged in as: %s", username)
    logging.info("Listening to chat IDs: %s", sorted(source_chat_ids))


if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
        client.run_until_disconnected()
