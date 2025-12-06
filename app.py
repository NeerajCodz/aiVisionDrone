import cv2
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import numpy as np
import os
import importlib.util
import json
import threading
import time
import logs

app = FastAPI(title="AI Drone Vision App")

# Mount static directory
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global State
SERVER_URL = "http://127.0.0.1:8000/video_feed" 
current_model = None
current_model_name = "opencv" # Default
latest_processed_frame = None
model_module = None
video_capture = None
running = True

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
        logs.log("App", f"Loaded model: {model_id}", "INFO")
        return True
    except Exception as e:
        logs.log("App", f"Failed to load model {model_id}: {e}", "ERROR")
        return False

# Initialize with default model
# Auto-load first available model
def init_first_model():
    models_dir = "models"
    if os.path.exists(models_dir):
        for d in os.listdir(models_dir):
            path = os.path.join(models_dir, d)
            if os.path.isdir(path) and os.path.exists(os.path.join(path, "model.json")):
                load_model(d)
                return
    logs.log("App", "No models found in /models directory", "WARNING")

init_first_model()

def processing_loop():
    global latest_processed_frame, video_capture, model_module
    
    # Retry connection logic
    while running:
        if video_capture is None or not video_capture.isOpened():
            try:
                # Try connecting to server
                video_capture = cv2.VideoCapture(SERVER_URL)
                if not video_capture.isOpened():
                    logs.log("App", "Waiting for server feed...", "WARNING")
                    time.sleep(2)
                    continue
                logs.log("App", "Connected to Drone Server Feed", "SUCCESS")
            except Exception as e:
                 logs.log("App", f"Connection error: {e}", "ERROR")
                 time.sleep(2)
                 continue

        ret, frame = video_capture.read()
        if not ret:
            # logs.log("App", "Stream interrupted", "WARNING")
            video_capture.release()
            video_capture = None
            time.sleep(0.5)
            continue
            
        if model_module and hasattr(model_module, 'process_frame'):
            try:
                processed, model_logs = model_module.process_frame(frame)
                latest_processed_frame = processed
                for l in model_logs:
                    logs.log(current_model_name, l, "AI")
            except Exception as e:
                logs.log("App", f"Model processing error: {e}", "ERROR")
                latest_processed_frame = frame # Fallback
        else:
            latest_processed_frame = frame
            
        time.sleep(0.01)

# Start background thread
thread = threading.Thread(target=processing_loop, daemon=True)
thread.start()

@app.get("/")
def read_root():
    return JSONResponse(content={"message": "Go to /static/index.html for the UI"})

@app.get("/api/models")
def list_models():
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

@app.post("/api/select_model")
async def select_model(request: Request):
    data = await request.json()
    model_id = data.get("model_id")
    if load_model(model_id):
        return {"status": "success", "message": f"Switched to {model_id}"}
    else:
        raise HTTPException(status_code=400, detail="Failed to load model")

@app.get("/api/logs")
def get_logs():
    return logs.get_all_logs()

def generate_processed_frames():
    global latest_processed_frame
    while True:
        if latest_processed_frame is not None:
             ret, buffer = cv2.imencode('.jpg', latest_processed_frame)
             if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        else:
            # Yield a loading frame or blank
            blank = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(blank, "Waiting for Feed...", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            ret, buffer = cv2.imencode('.jpg', blank)
            if ret:
                 yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        
        cv2.waitKey(30)

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(generate_processed_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
