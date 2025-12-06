# app.py
import cv2
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import numpy as np
import os
import importlib.util
import json
import threading
import time
import logs
import argparse
from contextlib import asynccontextmanager

# === CRITICAL FIX: Increase FFmpeg timeouts (prevents 30s disconnects) ===
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "timeout|60000000;"          # 60 seconds connect timeout
    "rw_timeout|60000000;"       # 60 seconds read/write timeout
    "analyzeduration|20000000;"  # Give stream time to be analyzed
    "probesize|50000000;"        # Larger probe buffer
    "rtsp_transport|tcp"         # Force TCP for RTSP (if ever used)
)

# === FastAPI with modern lifespan ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    print("[INFO] Starting AI Drone Vision App...")
    models = get_models()
    os.makedirs("static", exist_ok=True)
    with open(os.path.join("static", "models.json"), 'w') as f:
        json.dump(models, f, indent=2)
    logs.log("App", f"Generated static models.json with {len(models)} models", "INFO")

    # Start processing thread
    thread = threading.Thread(target=processing_loop, daemon=True)
    thread.start()

    yield  # App runs here

    # --- Shutdown ---
    global running
    running = False
    logs.log("App", "Shutting down...", "INFO")


app = FastAPI(title="AI Drone Vision App", lifespan=lifespan)

# Mount static files
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/css", StaticFiles(directory="static/css"), name="css")
app.mount("/js", StaticFiles(directory="static/js"), name="js")

# === Global State ===
SERVER_URL = "http://10.52.156.118:8000/video_feed"  # Change if needed
current_model = None
current_model_name = "opencv"  # Default fallback
latest_processed_frame = None
model_module = None
video_capture = None
running = True
standalone_mode = False


def get_models():
    models_dir = "models"
    model_list = []
    if os.path.exists(models_dir):
        for d in os.listdir(models_dir):
            path = os.path.join(models_dir, d)
            if os.path.isdir(path):
                json_path = os.path.join(path, "model.json")
                if os.path.exists(json_path):
                    with open(json_path, 'r') as f:
                        meta = json.load(f)
                        meta['id'] = d
                        model_list.append(meta)
    return model_list


def load_model(model_id):
    global model_module, current_model_name
    model_path = os.path.join("models", model_id, "main.py")
    if not os.path.exists(model_path):
        logs.log("App", f"Model {model_id} not found", "ERROR")
        return False

    try:
        spec = importlib.util.spec_from_file_location("model_main", model_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        model_module = module
        current_model_name = model_id
        logs.log("App", f"Loaded model: {model_id}", "SUCCESS")
        return True
    except Exception as e:
        logs.log("App", f"Failed to load model {model_id}: {e}", "ERROR")
        return False


def processing_loop():
    global latest_processed_frame, video_capture, model_module, standalone_mode

    retry_delay = 2
    while running:
        if video_capture is None or not video_capture.isOpened():
            while running:
                try:
                    logs.log("App", "Connecting to video source...", "INFO")
                    if standalone_mode:
                        video_capture = cv2.VideoCapture(0)
                        logs.log("App", "Opened laptop webcam", "SUCCESS")
                    else:
                        video_capture = cv2.VideoCapture(SERVER_URL)
                        # Optimize for low latency
                        video_capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        video_capture.set(cv2.CAP_PROP_FPS, 30)

                    if video_capture.isOpened():
                        logs.log("App", "Connected to Drone Server Feed", "SUCCESS")
                        retry_delay = 2  # Reset backoff
                        break
                    else:
                        raise Exception("VideoCapture failed to open")
                except Exception as e:
                    if video_capture:
                        video_capture.release()
                        video_capture = None
                    logs.log("App", f"Connection failed: {e}. Retrying in {retry_delay}s...", "WARNING")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30)  # Exponential backoff

        ret, frame = video_capture.read()
        if not ret:
            logs.log("App", "Frame read failed. Reconnecting...", "WARNING")
            video_capture.release()
            video_capture = None
            time.sleep(0.5)
            continue

        # Process frame with current model
        if model_module and hasattr(model_module, 'process_frame'):
            try:
                processed, model_logs = model_module.process_frame(frame)
                latest_processed_frame = processed
                for l in model_logs:
                    logs.log(current_model_name, l, "AI")
            except Exception as e:
                logs.log("App", f"Model processing error: {e}", "ERROR")
                latest_processed_frame = frame
        else:
            latest_processed_frame = frame

        time.sleep(0.01)  # ~100 FPS processing max


# === Routes ===
@app.get("/")
def read_root():
    return FileResponse("static/index.html")


@app.get("/api/models")
def list_models():
    return get_models()


@app.post("/api/select_model")
async def select_model(request: Request):
    data = await request.json()
    model_id = data.get("model_id")
    if load_model(model_id):
        return {"status": "success", "message": f"Switched to model: {model_id}"}
    else:
        raise HTTPException(status_code=400, detail="Failed to load model")


@app.get("/api/logs")
def get_logs():
    return logs.get_all_logs()


def generate_processed_frames():
    global latest_processed_frame
    while True:
        if latest_processed_frame is not None:
            ret, buffer = cv2.imencode('.jpg', latest_processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        else:
            # Placeholder frame
            blank = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(blank, "Waiting for video feed...", (200, 360),
                        cv2.FONT_HERSHEY_SIMPLEX, 2, (100, 200, 255), 4)
            ret, buffer = cv2.imencode('.jpg', blank)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

        time.sleep(0.033)  # ~30 FPS output


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(generate_processed_frames(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


# === Main ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Drone Vision App")
    parser.add_argument("--standalone", action="store_true", help="Use laptop webcam instead of drone")
    parser.add_argument("--model", type=str, help="Load specific model on startup", default=None)
    args = parser.parse_args()

    if args.standalone:
        standalone_mode = True
        logs.log("App", "Running in standalone (webcam) mode", "INFO")

    if args.model:
        logs.log("App", f"Loading requested model: {args.model}", "INFO")
        if not load_model(args.model):
            logs.log("App", f"Could not load model: {args.model}", "ERROR")
    else:
        logs.log("App", "No model specified. Running in Video Only mode.", "INFO")

    print("\nAI Drone Vision Server Running → http://localhost:5000")
    print("Press CTRL+C to stop\n")
    uvicorn.run(app, host="0.0.0.0", port=5000)