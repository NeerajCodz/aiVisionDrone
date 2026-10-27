# ESP32-CAM wireless video integration

> Historical design for the original single-camera integration. See the current [Vision Hub setup](../../../README.md) for multiple cameras and unique per-board hostnames.

## Intent

Connect the ESP32-CAM to the existing Vision Hub dashboard over Wi-Fi, show its live video in the dashboard, and make the project's existing vision models available for selection. The dashboard should start in video-only mode so a model is enabled deliberately from its existing selector.

## Goals

- Give the ESP32-CAM firmware a Wi-Fi MJPEG stream endpoint.
- Have `app.py` read that endpoint directly, using a configurable stream URL rather than the current hardcoded address.
- Preserve the dashboard's model selector, annotated video route, and mission log flow.
- Install project dependencies in an isolated Python environment and make the existing face, hand, person, pose, and YOLO models selectable.
- Run the dashboard locally and report the camera URL and connection status.

## Non-goals

- Change or replace the dashboard's visual design.
- Add autonomous flight, control commands, or video recording.
- Make the ESP32-CAM perform neural network inference; processing stays on the computer.
- Keep the separate Raspberry Pi relay in the camera path.

## Constraints and current state

- `app.py` already uses OpenCV `VideoCapture` on an HTTP video URL and serves the processed frames at `/video_feed`.
- `app.py` currently hardcodes `SERVER_URL` to an address on another network. The URL must become configurable, with a clear default for the camera endpoint.
- The startup path currently leaves model selection empty unless `--model` is passed; the requested default is video-only.
- The dashboard enumerates model folders with a `model.json`. Existing model folders include face recognition, hand tracking, person detection, skeleton tracking, and YOLOv8. The YOLO weights file is already present.
- The model modules need `mediapipe`, `face_recognition`/`dlib`, and `ultralytics` in addition to the current requirements. Installing `dlib` may depend on the available Python version and Windows build support.
- The existing hand/person models use MediaPipe's legacy `mp.solutions` API. Pin MediaPipe to 0.10.21 because the Python package removed that API starting with 0.10.30. MediaPipe 0.10.21 and Ultralytics declare different OpenCV wheel packages, so both wrappers are pinned to the matching 4.11.0.86 release; they share the `cv2` namespace.
- `server.py` is written for a Raspberry Pi stream and contains `_name_` typos. It will not be used for this direct camera path.
- The USB-to-serial adapter is detected on COM5 and the Arduino ESP32 platform is installed. The user reports `ESP-32S` printed on the module and identifies the full board as an ESP32-CAM. Use the common AI-Thinker-compatible ESP32-CAM pin map as the initial firmware target, and surface camera initialization failure clearly if the camera-board layout differs.
- Firmware needs the camera's matching pin map and local Wi-Fi credentials. Credentials must stay out of version control.
- Upload may require the board to be put into its bootloader mode using its BOOT/GPIO0 and RESET controls.
- The user wants the dashboard accessible from other devices on the same Wi-Fi. Preserve the app's existing `0.0.0.0` bind.
- Python 3.12.10 is available on the computer; use it for the project's isolated environment.

## Approaches considered

1. **Direct MJPEG pull (selected).** The ESP32-CAM serves an HTTP MJPEG stream and `app.py` opens it directly with OpenCV. This is the smallest fit for the current app, needs no second video service, and keeps inference on the computer. The computer and camera must be able to reach each other on the same network.
2. **Frame-upload receiver.** The camera posts still frames to a Python endpoint, which stores the latest frame for the dashboard. This gives the computer more control over buffering and reconnection, but requires custom camera upload firmware and new receiver logic.

The direct MJPEG approach was selected in conversation because it uses the existing OpenCV stream reader and minimizes moving parts.

## Proposed implementation

- Add an Arduino sketch under a clearly named firmware directory for the confirmed ESP32-CAM variant. It connects to Wi-Fi and serves a browser-viewable MJPEG endpoint; Wi-Fi secrets are loaded from an ignored local header, with a checked-in example template.
- Add an environment-variable setting for the camera stream URL in `app.py`, preserving its existing retry and low-buffer capture behavior.
- Keep the dashboard and inference pipeline intact. The existing models remain selectable; no model is activated until chosen in the UI.
- Create a project-local Python 3.12 virtual environment, install the project's base and model dependencies there, and resolve any Windows/Python incompatibility before launching the app.
- Start the FastAPI dashboard and leave the user with its local address and the camera stream URL to use.

## Decisions left to the builder

- Exact firmware file layout and whether the stream URL is provided as a command-line option or environment variable; prefer the environment variable to match the existing app configuration.
- Appropriate ESP32-CAM JPEG size and quality for reliable Wi-Fi streaming.
- How to avoid making the server's model scanner report the Arduino firmware folder as an AI model.
- A clear user-facing message when the camera URL is unreachable.

## Remaining setup

- Wi-Fi SSID and password are still needed for the camera to join the network. The implementation will provide an ignored local secrets header; credentials do not need to be sent in chat or committed.

## Success criteria

- The firmware builds for the confirmed ESP32-CAM board and can expose an MJPEG stream over Wi-Fi.
- With the camera online, the dashboard shows live video; with a model selected, the existing processor shows annotated video and logs.
- The Python app launches using the project-local environment and does not depend on the Raspberry Pi relay.
- No Wi-Fi password is stored in tracked files.
