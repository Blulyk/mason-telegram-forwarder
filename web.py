import asyncio
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import requests
from dotenv import dotenv_values, set_key
from flask import Flask, flash, redirect, render_template, request, url_for
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError


DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
CONFIG_FILE = Path(os.getenv("ENV_FILE", DATA_DIR / "config.env"))
LOGIN_STATE_FILE = DATA_DIR / "login_state.json"
RESTART_SIGNAL_FILE = DATA_DIR / "restart_forwarder.signal"
DEFAULT_SESSION_NAME = str(DATA_DIR / "telegram_forwarder_session")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-local-only")


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    ensure_data_dir()
    values = dotenv_values(CONFIG_FILE) if CONFIG_FILE.exists() else {}
    return {
        "TELEGRAM_API_ID": values.get("TELEGRAM_API_ID", ""),
        "TELEGRAM_API_HASH": values.get("TELEGRAM_API_HASH", ""),
        "SOURCE_CHAT": values.get("SOURCE_CHAT", ""),
        "N8N_WEBHOOK_URL": values.get("N8N_WEBHOOK_URL", ""),
        "SESSION_NAME": values.get("SESSION_NAME", DEFAULT_SESSION_NAME),
    }


def save_config(values):
    ensure_data_dir()
    if not CONFIG_FILE.exists():
        CONFIG_FILE.touch(mode=0o600)

    for key, value in values.items():
        set_key(str(CONFIG_FILE), key, value or "", quote_mode="never")


def session_file_for(session_name):
    session_path = Path(session_name)
    if str(session_path).endswith(".session"):
        return session_path
    return Path(f"{session_name}.session")


def session_is_authorized(session_name):
    session_file = session_file_for(session_name)
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


def make_session_snapshot(session_name, destination_session_name):
    source_file = session_file_for(session_name)
    destination_file = session_file_for(destination_session_name)

    if not source_file.exists():
        raise RuntimeError("La sesion de Telegram aun no existe.")

    source = sqlite3.connect(f"file:{source_file}?mode=ro", uri=True, timeout=5)
    destination = sqlite3.connect(destination_file)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def masked(value, visible=4):
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return f"{value[:visible]}{'*' * 12}"


def client_from_config(config):
    api_id = config.get("TELEGRAM_API_ID")
    api_hash = config.get("TELEGRAM_API_HASH")
    session_name = config.get("SESSION_NAME") or DEFAULT_SESSION_NAME

    if not api_id or not api_hash:
        raise RuntimeError("Configura TELEGRAM_API_ID y TELEGRAM_API_HASH primero.")

    Path(session_name).parent.mkdir(parents=True, exist_ok=True)
    return TelegramClient(session_name, int(api_id), api_hash)


async def request_login_code(config, phone):
    if session_is_authorized(config.get("SESSION_NAME") or DEFAULT_SESSION_NAME):
        raise RuntimeError("Ya existe una sesion de Telegram iniciada. No hace falta pedir otro codigo.")

    client = client_from_config(config)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        LOGIN_STATE_FILE.write_text(
            json.dumps({"phone": phone, "phone_code_hash": sent.phone_code_hash}),
            encoding="utf-8",
        )
    finally:
        await client.disconnect()


async def finish_login(config, code, password):
    if not LOGIN_STATE_FILE.exists():
        raise RuntimeError("Primero solicita un codigo de login.")

    state = json.loads(LOGIN_STATE_FILE.read_text(encoding="utf-8"))
    client = client_from_config(config)
    await client.connect()
    try:
        try:
            await client.sign_in(
                phone=state["phone"],
                code=code,
                phone_code_hash=state["phone_code_hash"],
            )
        except SessionPasswordNeededError:
            if not password:
                raise RuntimeError("Esta cuenta tiene 2FA. Introduce la contrasena.")
            await client.sign_in(password=password)
        LOGIN_STATE_FILE.unlink(missing_ok=True)
    finally:
        await client.disconnect()


async def is_authorized(config):
    try:
        client = client_from_config(config)
        await client.connect()
        try:
            return await client.is_user_authorized()
        finally:
            await client.disconnect()
    except Exception:
        return False


async def get_dialogs(config):
    session_name = config.get("SESSION_NAME") or DEFAULT_SESSION_NAME
    if not session_is_authorized(session_name):
        raise RuntimeError("La cuenta de Telegram aun no esta autorizada.")

    with tempfile.TemporaryDirectory() as temp_dir:
        snapshot_session_name = str(Path(temp_dir) / "telegram_forwarder_snapshot")
        make_session_snapshot(session_name, snapshot_session_name)

        snapshot_config = {**config, "SESSION_NAME": snapshot_session_name}
        client = client_from_config(snapshot_config)
        await client.connect()
        try:
            dialogs = []
            async for dialog in client.iter_dialogs(limit=200):
                dialogs.append({"name": dialog.name, "id": dialog.id})
            return dialogs
        finally:
            await client.disconnect()


def config_status(config):
    session_file = session_file_for(config["SESSION_NAME"])
    configured = all(
        config.get(key)
        for key in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "SOURCE_CHAT", "N8N_WEBHOOK_URL")
    )
    return {
        "configured": configured,
        "session_file_exists": session_file.exists(),
        "session_file": str(session_file),
        "config_file": str(CONFIG_FILE),
    }


@app.get("/")
def index():
    config = load_config()
    status = config_status(config)
    authorized = session_is_authorized(config["SESSION_NAME"])
    public_config = {**config, "TELEGRAM_API_HASH": masked(config["TELEGRAM_API_HASH"])}
    return render_template("index.html", config=config, public_config=public_config, status=status, authorized=authorized, dialogs=None)


@app.post("/config")
def update_config():
    current = load_config()
    api_hash = request.form.get("TELEGRAM_API_HASH", "").strip()
    values = {
        "TELEGRAM_API_ID": request.form.get("TELEGRAM_API_ID", "").strip(),
        "TELEGRAM_API_HASH": api_hash if api_hash else current.get("TELEGRAM_API_HASH", ""),
        "SOURCE_CHAT": request.form.get("SOURCE_CHAT", "").strip(),
        "N8N_WEBHOOK_URL": request.form.get("N8N_WEBHOOK_URL", "").strip(),
        "SESSION_NAME": request.form.get("SESSION_NAME", "").strip() or DEFAULT_SESSION_NAME,
    }
    save_config(values)
    flash("Configuracion guardada. Reinicia el servicio forwarder para aplicar SOURCE_CHAT o webhook.", "success")
    return redirect(url_for("index"))


@app.post("/login/request-code")
def login_request_code():
    config = load_config()
    phone = request.form.get("phone", "").strip()
    if not phone:
        flash("Introduce el telefono con prefijo internacional.", "error")
        return redirect(url_for("index"))

    try:
        asyncio.run(request_login_code(config, phone))
        flash("Codigo solicitado. Revisa Telegram e introducelo abajo.", "success")
    except Exception as exc:
        flash(f"No se pudo solicitar el codigo: {exc}", "error")
    return redirect(url_for("index"))


@app.post("/login/verify")
def login_verify():
    config = load_config()
    code = request.form.get("code", "").strip()
    password = request.form.get("password", "").strip()
    if not code:
        flash("Introduce el codigo recibido.", "error")
        return redirect(url_for("index"))

    try:
        asyncio.run(finish_login(config, code, password))
        flash("Login completado. La sesion persistente ya esta creada.", "success")
    except Exception as exc:
        flash(f"No se pudo completar el login: {exc}", "error")
    return redirect(url_for("index"))


@app.post("/dialogs")
def dialogs():
    config = load_config()
    try:
        dialog_list = asyncio.run(get_dialogs(config))
        status = config_status(config)
        authorized = session_is_authorized(config["SESSION_NAME"])
        public_config = {**config, "TELEGRAM_API_HASH": masked(config["TELEGRAM_API_HASH"])}
        return render_template("index.html", config=config, public_config=public_config, status=status, authorized=authorized, dialogs=dialog_list)
    except Exception as exc:
        flash(f"No se pudieron listar chats: {exc}", "error")
        return redirect(url_for("index"))


@app.post("/restart-forwarder")
def restart_forwarder():
    ensure_data_dir()
    RESTART_SIGNAL_FILE.write_text("restart\n", encoding="utf-8")
    flash("Reinicio del forwarder solicitado. Espera unos segundos y revisa los logs.", "success")
    return redirect(url_for("index"))


@app.post("/test-webhook")
def test_webhook():
    config = load_config()
    webhook_url = config.get("N8N_WEBHOOK_URL")
    if not webhook_url:
        flash("Configura N8N_WEBHOOK_URL primero.", "error")
        return redirect(url_for("index"))

    payload = {
        "chat_id": "test",
        "message_id": 0,
        "sender_id": "telegram-forwarder-ui",
        "text": "Prueba desde Telegram Forwarder",
        "date": None,
        "has_media": False,
        "grouped_id": None,
    }
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        flash(f"Webhook probado correctamente. Estado HTTP {response.status_code}.", "success")
    except Exception as exc:
        flash(f"El webhook devolvio error: {exc}", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    ensure_data_dir()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
