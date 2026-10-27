# Vision Hub developer guide

Vision Hub brings multiple network camera feeds into one dashboard and runs the selected vision model for each feed on the server. The ESP32-CAM firmware produces MJPEG; the Python application connects to each camera directly, runs inference, and serves the dashboard. See [README.md](README.md) for installation, flashing, and camera setup.

## Project layout

```text
app.py                  FastAPI application and camera processing
logs.py                 In-memory event log
firmware/esp32cam/      ESP32-CAM sketch and Wi-Fi template
models/                 Model modules and metadata
static/                 Dashboard HTML, CSS, and JavaScript
requirements.txt        Python and model dependencies
server.py               Legacy Raspberry Pi relay; not used by Vision Hub
```

The project runs directly from its existing checkout directory. The directory name does not need to match the product name.

## Camera interface

Each ESP32-CAM serves MJPEG at `http://<camera-ip>:81/stream`. The sketch prints its DHCP address and its unique `esp32cam-<suffix>.local` hostname to the serial monitor at 115200 baud. The dashboard registers a name and stream URL for each camera; use the numeric IP printed by the board if `.local` resolution is unavailable. Camera configuration is local to the server machine.

The server exposes these routes for the dashboard:

| Route | Purpose |
| --- | --- |
| `GET /api/cameras` | List configured cameras and their state |
| `POST /api/cameras` | Add a camera |
| `PATCH /api/cameras/{id}` | Change a camera's configuration |
| `DELETE /api/cameras/{id}` | Remove a camera |
| `POST /api/cameras/{id}/model` | Set a camera's model, or clear it with a null `model_id` |
| `GET /api/cameras/{id}/stream` | View that camera's processed MJPEG stream |
| `GET /api/models` | List available models |
| `GET /api/logs` | Read recent events |

`POST /api/cameras` accepts JSON such as `{"name":"Workshop", "url":"http://192.168.1.42:81/stream"}`. The model route accepts `{"model_id":"yolov8"}` or `{"model_id":null}` for video-only mode.

`AIVISION_CAMERA_URL` can seed the first camera when there is no saved camera configuration. `AIVISION_CAMERAS_FILE` overrides the default `camera_config.json` path. `--standalone` uses the local webcam for the first camera; `--model` selects a model for the first camera for that run. New cameras start in video-only mode, and saved model selections are restored on restart. See `python app.py --help` for the current arguments.

## Adding a model

Create a folder under `models/` containing `model.json` metadata and `main.py`. The module must expose `process_frame(frame)` and return `(processed_frame, log_messages)`. Dependencies should be added to `requirements.txt`; a model should not change camera state or assume it is the only active feed. Models are discovered from folders containing `model.json`.

MediaPipe is pinned to the legacy release used by the existing hand and pose modules. Both OpenCV distribution names are pinned to the same release because MediaPipe and Ultralytics declare different packages that share the `cv2` namespace. Upgrade those dependencies together and check all model selectors after changing them.

## Local configuration and access

- `firmware/esp32cam/secrets.h` contains local Wi-Fi credentials and is ignored by Git. Start from `secrets.example.h`; never commit credentials.
- Camera URLs are stored locally in `camera_config.json`, which is ignored by Git. The camera API accepts HTTP(S) URLs and rejects embedded usernames or passwords.
- The dashboard binds to `0.0.0.0:5000` so other devices on the network can connect. The current application has no login; use it on a trusted network and restrict firewall access to the intended clients.
- `server.py` is an older Pi relay and is not required for the ESP32-CAM path.
