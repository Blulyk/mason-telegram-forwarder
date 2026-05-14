import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import qrcode from "qrcode";
import pkg from "whatsapp-web.js";

const { Client, LocalAuth, MessageMedia } = pkg;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = Number(process.env.PORT || 8090);
const API_KEY = process.env.API_KEY || "";
const DATA_DIR = process.env.DATA_DIR || "/data";
const MAX_BODY_SIZE = process.env.MAX_BODY_SIZE || "25mb";

const app = express();
app.use(express.json({ limit: MAX_BODY_SIZE }));
app.use(express.static(path.join(__dirname, "public")));

let currentQr = null;
let currentQrDataUrl = null;
let ready = false;
let authenticated = false;
let lastError = null;
let me = null;

function requireApiKey(req, res, next) {
  if (!API_KEY) {
    return res.status(500).json({ error: "API_KEY is not configured" });
  }

  if (req.header("X-Api-Key") !== API_KEY) {
    return res.status(401).json({ error: "Unauthorized" });
  }

  next();
}

function normalizeChatId(chatId) {
  if (!chatId || typeof chatId !== "string") {
    throw new Error("chatId is required");
  }
  return chatId.trim();
}

function mediaFromPayload(file) {
  if (!file) return null;

  if (file.data) {
    if (!file.mimetype) throw new Error("file.mimetype is required when file.data is used");
    return new MessageMedia(file.mimetype, file.data, file.filename || "telegram-media");
  }

  if (file.url) {
    return MessageMedia.fromUrl(file.url, { unsafeMime: true });
  }

  return null;
}

const client = new Client({
  authStrategy: new LocalAuth({
    clientId: "default",
    dataPath: path.join(DATA_DIR, "auth"),
  }),
  puppeteer: {
    executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || "/usr/bin/chromium",
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--no-first-run",
      "--no-zygote",
    ],
  },
});

client.on("qr", async (qr) => {
  currentQr = qr;
  currentQrDataUrl = await qrcode.toDataURL(qr);
  ready = false;
  authenticated = false;
  lastError = null;
  console.log("QR received. Open the dashboard to scan it.");
});

client.on("authenticated", () => {
  authenticated = true;
  lastError = null;
  console.log("WhatsApp authenticated.");
});

client.on("ready", async () => {
  ready = true;
  currentQr = null;
  currentQrDataUrl = null;
  lastError = null;
  me = client.info || null;
  console.log("WhatsApp Bridge is ready.");
});

client.on("auth_failure", (message) => {
  ready = false;
  authenticated = false;
  lastError = `Authentication failure: ${message}`;
  console.error(lastError);
});

client.on("disconnected", (reason) => {
  ready = false;
  authenticated = false;
  lastError = `Disconnected: ${reason}`;
  console.warn(lastError);
});

app.get("/api/status", requireApiKey, (req, res) => {
  res.json({
    ready,
    authenticated,
    hasQr: Boolean(currentQrDataUrl),
    lastError,
    me,
  });
});

app.get("/api/qr", requireApiKey, (req, res) => {
  res.json({
    qr: currentQr,
    qrDataUrl: currentQrDataUrl,
    ready,
    authenticated,
    lastError,
  });
});

app.get("/api/groups", requireApiKey, async (req, res) => {
  if (!ready) return res.status(409).json({ error: "WhatsApp session is not ready" });

  const chats = await client.getChats();
  const groups = chats
    .filter((chat) => chat.isGroup)
    .map((chat) => ({
      id: chat.id._serialized,
      name: chat.name,
      participants: chat.participants?.length || null,
    }));
  res.json(groups);
});

app.post("/api/send", requireApiKey, async (req, res) => {
  if (!ready) return res.status(409).json({ error: "WhatsApp session is not ready" });

  try {
    const chatId = normalizeChatId(req.body.chatId);
    const text = req.body.text || req.body.caption || "";
    const media = await mediaFromPayload(req.body.file);

    let message;
    if (media) {
      message = await client.sendMessage(chatId, media, { caption: text });
    } else {
      if (!text) throw new Error("text is required when no file is provided");
      message = await client.sendMessage(chatId, text);
    }

    res.json({
      ok: true,
      id: message.id?._serialized || null,
      timestamp: message.timestamp || null,
    });
  } catch (error) {
    console.error("Failed to send message", error);
    res.status(400).json({ error: error.message || String(error) });
  }
});

app.post("/api/logout", requireApiKey, async (req, res) => {
  await client.logout();
  ready = false;
  authenticated = false;
  currentQr = null;
  currentQrDataUrl = null;
  res.json({ ok: true });
});

app.get("*", (req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

client.initialize();

app.listen(PORT, "0.0.0.0", () => {
  console.log(`WhatsApp Bridge listening on port ${PORT}`);
});
