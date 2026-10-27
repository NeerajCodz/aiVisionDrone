(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const state = { cameras: [], models: [], logs: [], clearedLogs: new Set(), serverOnline: false, polling: false };
  const cards = new Map();
  const dialog = $("#cameraDialog");
  const form = $("#cameraForm");
  const nameInput = $("#cameraName");
  const urlInput = $("#cameraUrl");
  const formError = $("#formError");
  const notice = $("#notice");
  let editingId = null;
  let noticeTimer;

  async function api(path, options = {}) {
    const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
    let body = null;
    try { body = await response.json(); } catch (_) { /* A response without JSON is still handled below. */ }
    if (!response.ok) {
      const detail = body && body.detail;
      throw new Error(typeof detail === "string" ? detail : "Request failed (" + response.status + ")");
    }
    return body;
  }

  function showNotice(message) {
    notice.textContent = message;
    notice.hidden = false;
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => { notice.hidden = true; }, 8000);
  }

  function setServerStatus(online) {
    state.serverOnline = online;
    ["#serverDot", "#sidebarDot", "#metricDot"].forEach((selector) => {
      const dot = $(selector);
      dot.classList.toggle("online", online);
      dot.classList.toggle("offline", !online);
      dot.classList.remove("connecting");
    });
    $("#serverStatus").textContent = online ? "Server online" : "Server unavailable";
    $("#sidebarStatus").textContent = online ? "Server online" : "Disconnected";
    $("#metricStatus").textContent = online ? "Online" : "Unavailable";
    $("#metricDetail").textContent = online ? "Server is responding" : "Check the server connection";
  }

  function openCameraDialog(camera = null) {
    editingId = camera ? camera.id : null;
    form.reset();
    formError.hidden = true;
    formError.textContent = "";
    $("#dialogTitle").textContent = camera ? "Edit camera" : "Add a camera";
    $("#saveCamera").textContent = camera ? "Save changes" : "Add camera";
    nameInput.value = camera ? camera.name : "";
    urlInput.value = camera ? camera.url : "";
    dialog.showModal();
    nameInput.focus();
  }

  function closeCameraDialog() {
    if (dialog.open) dialog.close();
  }

  document.querySelectorAll("[data-open-camera]").forEach((button) => button.addEventListener("click", () => openCameraDialog()));
  document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", closeCameraDialog));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    formError.hidden = true;
    const name = nameInput.value.trim();
    const url = urlInput.value.trim();
    let parsed;
    try { parsed = new URL(url); } catch (_) { parsed = null; }
    if (!name || !parsed || !["http:", "https:"].includes(parsed.protocol)) {
      formError.textContent = "Enter a camera name and a valid HTTP or HTTPS stream URL.";
      formError.hidden = false;
      return;
    }
    const save = $("#saveCamera");
    save.disabled = true;
    try {
      const path = editingId ? "/api/cameras/" + encodeURIComponent(editingId) : "/api/cameras";
      const updatedId = editingId;
      await api(path, { method: editingId ? "PATCH" : "POST", body: JSON.stringify({ name, url }) });
      closeCameraDialog();
      await pollCameras();
      if (updatedId && cards.has(updatedId)) {
        const image = $(".camera-feed", cards.get(updatedId));
        image.src = streamUrl(updatedId);
      }
    } catch (error) {
      formError.textContent = error.message;
      formError.hidden = false;
    } finally {
      save.disabled = false;
    }
  });

  function streamUrl(id) {
    return "/api/cameras/" + encodeURIComponent(id) + "/stream?t=" + Date.now();
  }

  function cameraById(id) {
    return state.cameras.find((camera) => String(camera.id) === String(id));
  }

  function fillModelOptions(select) {
    const previous = select.value;
    const fragment = document.createDocumentFragment();
    const videoOnly = document.createElement("option");
    videoOnly.value = "";
    videoOnly.textContent = "Video only";
    fragment.append(videoOnly);
    state.models.forEach((model) => {
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = model.name || model.id;
      fragment.append(option);
    });
    select.replaceChildren(fragment);
    select.value = previous;
  }

  function makeCard(camera) {
    const card = $("#cameraCardTemplate").content.firstElementChild.cloneNode(true);
    const id = String(camera.id);
    card.dataset.cameraId = id;
    const select = $(".model-select", card);
    const image = $(".camera-feed", card);
    fillModelOptions(select);
    image.src = streamUrl(id);
    image.addEventListener("error", () => {
      if (!card.isConnected) return;
      setTimeout(() => { if (card.isConnected) image.src = streamUrl(id); }, 5000);
    });
    $(".edit-camera", card).addEventListener("click", () => {
      const current = cameraById(id);
      if (current) openCameraDialog(current);
    });
    $(".delete-camera", card).addEventListener("click", async () => {
      const current = cameraById(id);
      if (!current || !window.confirm('Remove "' + current.name + '" from Vision Hub?')) return;
      try {
        await api("/api/cameras/" + encodeURIComponent(id), { method: "DELETE" });
        await pollCameras();
      } catch (error) { showNotice("Could not remove camera: " + error.message); }
    });
    select.addEventListener("change", async () => {
      const selected = select.value;
      select.disabled = true;
      try {
        await api("/api/cameras/" + encodeURIComponent(id) + "/model", {
          method: "POST",
          body: JSON.stringify({ model_id: selected || null }),
        });
        await pollCameras();
      } catch (error) {
        const current = cameraById(id);
        select.value = current && current.model_id ? current.model_id : "";
        showNotice("Could not change model: " + error.message);
      } finally { select.disabled = false; }
    });
    cards.set(id, card);
    return card;
  }

  function updateCard(card, camera, index) {
    const name = camera.name || "Camera";
    const cameraStatus = state.serverOnline ? camera.status : "offline";
    $(".camera-name", card).textContent = name;
    $(".camera-feed", card).alt = "Live feed from " + name;
    $(".feed-index", card).textContent = "CAM / " + String(index + 1).padStart(2, "0");
    $(".edit-camera", card).setAttribute("aria-label", "Edit " + name);
    $(".delete-camera", card).setAttribute("aria-label", "Remove " + name);
    const select = $(".model-select", card);
    select.setAttribute("aria-label", "AI model for " + name);
    if (document.activeElement !== select && !select.disabled) select.value = camera.model_id || "";
    const dot = $(".camera-status .status-dot", card);
    dot.className = "status-dot " + (cameraStatus === "online" ? "online" : cameraStatus === "connecting" ? "connecting" : "offline");
    $(".status-text", card).textContent = cameraStatus === "online" ? "Live" : cameraStatus === "connecting" ? "Connecting" : "Offline";
    const placeholder = $(".feed-placeholder", card);
    placeholder.hidden = cameraStatus === "online";
    $(".placeholder-title", card).textContent = cameraStatus === "connecting" ? "Connecting to camera" : "Camera offline";
    $(".placeholder-detail", card).textContent = state.serverOnline ? "The feed will appear when the camera is online." : "Waiting for the Vision Hub server.";
  }

  function renderCameras() {
    const grid = $("#cameraGrid");
    const activeIds = new Set(state.cameras.map((camera) => String(camera.id)));
    for (const [id, card] of cards) {
      if (!activeIds.has(id)) {
        $(".camera-feed", card).removeAttribute("src");
        card.remove();
        cards.delete(id);
      }
    }
    state.cameras.forEach((camera, index) => {
      const id = String(camera.id);
      const card = cards.get(id) || makeCard(camera);
      updateCard(card, camera, index);
      if (grid.children[index] !== card) grid.insertBefore(card, grid.children[index] || null);
    });
    $("#emptyState").hidden = !state.serverOnline || state.cameras.length > 0;
    $("#serverNotice").hidden = state.serverOnline;
    $("#cameraCount").textContent = state.cameras.length;
    $("#navCameraCount").textContent = state.cameras.length;
    $("#feedCount").textContent = state.cameras.length;
    $("#onlineCount").textContent = state.serverOnline ? state.cameras.filter((camera) => camera.status === "online").length : "—";
    $("#modelCount").textContent = state.models.length;
  }

  async function pollCameras() {
    if (state.polling) return;
    state.polling = true;
    try {
      const cameras = await api("/api/cameras");
      if (!Array.isArray(cameras)) throw new Error("Invalid camera list");
      state.cameras = cameras;
      setServerStatus(true);
    } catch (_) {
      setServerStatus(false);
    } finally {
      renderCameras();
      state.polling = false;
    }
  }

  async function loadModels() {
    try {
      const models = await api("/api/models");
      if (!Array.isArray(models)) throw new Error("Invalid model list");
      const changed = JSON.stringify(state.models) !== JSON.stringify(models);
      state.models = models;
      if (changed) cards.forEach((card) => {
        const select = $(".model-select", card);
        if (select.disabled || document.activeElement === select) return;
        fillModelOptions(select);
        const camera = cameraById(card.dataset.cameraId);
        if (camera) select.value = camera.model_id || "";
      });
      $("#modelCount").textContent = models.length;
    } catch (_) {
      $("#modelCount").textContent = "—";
    }
  }

  function logKey(log) {
    return JSON.stringify([log.timestamp, log.source, log.level, log.message]);
  }

  function renderLogs() {
    const container = $("#logsContainer");
    const visible = state.logs.filter((log) => !state.clearedLogs.has(logKey(log))).slice(-50).reverse();
    const fragment = document.createDocumentFragment();
    visible.forEach((log) => {
      const row = document.createElement("div");
      row.className = "log-entry " + (["error", "warning", "success"].includes(String(log.level).toLowerCase()) ? String(log.level).toLowerCase() : "");
      const time = document.createElement("span");
      time.className = "log-time";
      time.textContent = log.timestamp || "";
      const source = document.createElement("span");
      source.className = "log-source";
      source.textContent = log.source || "System";
      const message = document.createElement("span");
      message.className = "log-message";
      message.textContent = log.message || "";
      row.append(time, source, message);
      fragment.append(row);
    });
    if (!visible.length) {
      const empty = document.createElement("div");
      empty.className = "log-empty";
      empty.textContent = "No activity to show.";
      fragment.append(empty);
    }
    container.replaceChildren(fragment);
  }

  async function pollLogs() {
    try {
      const logs = await api("/api/logs");
      if (Array.isArray(logs)) {
        state.logs = logs;
        const currentKeys = new Set(logs.map(logKey));
        state.clearedLogs = new Set([...state.clearedLogs].filter((key) => currentKeys.has(key)));
        renderLogs();
      }
    } catch (_) { /* Camera polling reports the connection state. */ }
  }

  $("#clearLogs").addEventListener("click", () => {
    state.logs.forEach((log) => state.clearedLogs.add(logKey(log)));
    renderLogs();
  });

  loadModels();
  pollCameras();
  pollLogs();
  setInterval(pollCameras, 4000);
  setInterval(pollLogs, 3000);
  setInterval(loadModels, 30000);
})();
