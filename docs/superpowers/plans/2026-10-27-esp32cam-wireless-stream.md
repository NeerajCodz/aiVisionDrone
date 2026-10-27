# ESP32-CAM Wireless Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream live ESP32-CAM video over Wi-Fi into the AI Vision Drone dashboard and make the existing vision models runnable from the dashboard.

**Architecture:** The ESP32-CAM serves an MJPEG endpoint at `/stream` on port 81. The existing FastAPI app opens that endpoint with OpenCV, processes frames with the selected model, and serves its existing annotated feed and logs. The app remains reachable from devices on the same Wi-Fi.

**Tech Stack:** Arduino ESP32 core 3.3.12, ESP32-CAM camera driver, C++ Arduino sketch, Python 3.12 virtual environment, FastAPI, OpenCV 4.11.0.86, MediaPipe 0.10.21, face-recognition/dlib, Ultralytics YOLOv8.

**Spec:** `docs/superpowers/specs/2026-10-27-esp32cam-mjpeg-integration-design.md`

## Global Constraints

- Use a project-local Python 3.12 virtual environment.
- Use the direct ESP32-CAM MJPEG stream; do not add a video relay service.
- Keep Wi-Fi credentials in an ignored local firmware header, never in tracked files.
- Preserve LAN dashboard access by binding to `0.0.0.0`.
- Keep model selection explicit; start in video-only mode.
- Pin MediaPipe 0.10.21 for the legacy `mp.solutions` API used by the existing models; align the OpenCV standard and contrib wheels at 4.11.0.86.
- Use the common AI-Thinker-compatible ESP32-CAM pin map for the board identified by the user as ESP-32S, and report camera initialization errors clearly.

## Review Focus

- Missing or invalid Wi-Fi credentials: firmware should explain that it cannot connect and should not print the password.
- Camera initialization or pin-map mismatch: log a clear failure rather than starting a blank stream silently.
- Camera hostname unavailable: expose the stream URL in serial output and allow the Python app URL to be overridden.
- Camera offline or stream endpoint unreachable: keep the FastAPI app alive and retry with bounded backoff.
- Optional AI dependency unavailable: report which model failed to load while keeping video-only mode usable.

---

### Task 1: Add ESP32-CAM stream firmware and local secrets handling

**Files:**
- Create: `firmware/esp32cam/esp32cam.ino`
- Create: `firmware/esp32cam/secrets.example.h`
- Modify: `.gitignore`

**Interfaces:**
- Firmware serves `http://esp32cam.local:81/stream` as `multipart/x-mixed-replace` MJPEG.
- `secrets.example.h` documents `WIFI_SSID` and `WIFI_PASSWORD`; local `secrets.h` supplies them and is ignored by Git.
- Serial startup output reports the actual DHCP address, stream URL, and camera initialization status.

- [x] Create a sketch configured for the common AI-Thinker ESP32-CAM pin map, QVGA frames, JPEG capture, and a bounded Wi-Fi connection wait.
- [x] Serve an MJPEG multipart response at port 81 path `/stream`; keep the board's root page simple and show the stream URL.
- [x] Add mDNS host `esp32cam.local` and print the DHCP URL over serial as a fallback.
- [x] Add a secrets header template and ignore only the local secrets file; confirm no credentials are tracked.
- [x] Compile for `esp32:esp32:esp32cam` with the installed Arduino CLI.
- [ ] Upload on COM5 after Wi-Fi credentials are configured and the board is in bootloader mode.

### Task 2: Connect the FastAPI app to the camera and install model dependencies

**Files:**
- Modify: `app.py`
- Modify: `requirements.txt`

**Interfaces:**
- `AIVISION_CAMERA_URL` selects the MJPEG source and defaults to `http://esp32cam.local:81/stream`.
- The existing `/video_feed`, `/api/models`, `/api/select_model`, and `/api/logs` routes remain the dashboard contract.
- Existing model folders remain selectable; no model is automatically selected.

- [x] Replace the hardcoded `SERVER_URL` with `AIVISION_CAMERA_URL` and set the direct-stream default above.
- [x] Keep the existing low-buffer OpenCV capture and retry behavior; log the URL used and make failed camera connection visible in app logs.
- [x] Add the missing `mediapipe` and `ultralytics` requirements for existing model modules; retain the existing face-recognition/dlib requirements.
- [x] Confirm that model discovery continues to expose face recognition, hand tracking, person detection, skeleton tracking, and YOLOv8.

### Task 3: Set up the environment and run the dashboard

**Files:**
- Create: `.venv/` (ignored local environment)
- Modify: `.gitignore` (ignore `.venv/`)
- Modify: `static/models.json` only if regeneration by app startup requires it

**Interfaces:**
- Launch command: `.venv\Scripts\python.exe app.py` from the project root.
- Local dashboard: `http://localhost:5000/`.
- LAN dashboard: `http://<computer-LAN-IP>:5000/`.

- [x] Create `.venv` with Python 3.12 and install `requirements.txt` plus all existing model dependencies into it.
- [x] Resolve the Windows wheel/build issue for `dlib` without weakening or removing the face-recognition model.
- [x] Launch the dashboard without `--model`, confirm it starts in video-only mode, and leave it running in the current session.
- [ ] If `esp32cam.local` does not resolve, set `AIVISION_CAMERA_URL` to the DHCP URL printed by the firmware and relaunch the app.
- [ ] Confirm the dashboard is reachable over Wi-Fi and, when the camera is powered and online, the dashboard shows the camera feed.
- [x] Select each model from the dashboard and confirm all five load without disabling the other models.

## Manual Run Verification

Firmware compilation, app startup, dashboard HTTP routes, and all five model selections were verified. Board upload, serial startup, a live camera stream, and access from a second Wi-Fi device remain pending the local Wi-Fi credentials and Windows firewall access for the current Public network profile.
