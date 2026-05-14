const apiKeyInput = document.querySelector("#apiKey");
const saveKeyButton = document.querySelector("#saveKey");
const statusEl = document.querySelector("#status");
const hintEl = document.querySelector("#hint");
const qrBox = document.querySelector("#qrBox");

apiKeyInput.value = localStorage.getItem("waBridgeApiKey") || "";

saveKeyButton.addEventListener("click", () => {
  localStorage.setItem("waBridgeApiKey", apiKeyInput.value.trim());
  refresh();
});

function headers() {
  return { "X-Api-Key": localStorage.getItem("waBridgeApiKey") || "" };
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: headers() });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function refresh() {
  try {
    const status = await fetchJson("/api/status");
    statusEl.textContent = status.ready ? "Conectado" : status.hasQr ? "Escanea QR" : "Arrancando";
    statusEl.className = `pill ${status.ready ? "ok" : ""}`;
    hintEl.textContent = status.lastError || (status.ready ? "Sesion lista para enviar mensajes." : "Escanea el QR cuando aparezca.");

    const qr = await fetchJson("/api/qr");
    if (qr.qrDataUrl) {
      qrBox.innerHTML = `<img src="${qr.qrDataUrl}" alt="QR de WhatsApp" />`;
    } else if (status.ready) {
      qrBox.textContent = "Sesion conectada";
    } else {
      qrBox.textContent = "Esperando QR";
    }
  } catch (error) {
    statusEl.textContent = "Sin conexion";
    statusEl.className = "pill error";
    hintEl.textContent = "Guarda la API key correcta de Umbrel.";
    qrBox.textContent = error.message;
  }
}

refresh();
setInterval(refresh, 5000);
