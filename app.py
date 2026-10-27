"""Vision Hub dashboard and camera API."""
import argparse
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import time

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from camera_manager import CameraManager, get_models, placeholder_frame
import logs


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("AIVISION_CAMERAS_FILE", ROOT / "camera_config.json"))
DEFAULT_CAMERA_URL = os.environ.get("AIVISION_CAMERA_URL", "").strip() or None
standalone_mode = False
startup_model = None
manager = None


@asynccontextmanager
async def lifespan(app):
    global manager
    manager = CameraManager(CONFIG_PATH, DEFAULT_CAMERA_URL, webcam=standalone_mode)
    manager.start(startup_model=startup_model)
    logs.log("App", f"Vision Hub started with {len(manager.list())} cameras", "INFO")
    try:
        yield
    finally:
        manager.stop()
        logs.log("App", "Shutting down", "INFO")


app = FastAPI(title="Vision Hub", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.mount("/css", StaticFiles(directory=ROOT / "static" / "css"), name="css")
app.mount("/js", StaticFiles(directory=ROOT / "static" / "js"), name="js")


class CameraCreate(BaseModel):
    name: str
    url: str


class CameraUpdate(BaseModel):
    name: str | None = None
    url: str | None = None


class ModelSelection(BaseModel):
    model_id: str | None = None


def camera_or_404(camera_id):
    try:
        return manager.get(camera_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Camera not found") from None


@app.get("/")
def read_root():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/models")
def list_models():
    return get_models()


@app.get("/api/cameras")
def list_cameras():
    return manager.list()


@app.post("/api/cameras", status_code=201)
def add_camera(payload: CameraCreate):
    try:
        return manager.add(payload.name, payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.patch("/api/cameras/{camera_id}")
def update_camera(camera_id: str, payload: CameraUpdate):
    try:
        return manager.update(camera_id, payload.name, payload.url)
    except KeyError:
        raise HTTPException(status_code=404, detail="Camera not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.delete("/api/cameras/{camera_id}", status_code=204)
def delete_camera(camera_id: str):
    try:
        manager.remove(camera_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Camera not found") from None


@app.post("/api/cameras/{camera_id}/model")
def select_camera_model(camera_id: str, payload: ModelSelection):
    try:
        return manager.select_model(camera_id, payload.model_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Camera not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.post("/api/select_model")
def select_model(payload: ModelSelection):
    """Keep the original single-camera selector available for existing clients."""
    camera = manager.first()
    if camera is None:
        raise HTTPException(status_code=404, detail="Add a camera first")
    select_camera_model(camera.id, payload)
    return {"status": "success", "message": f"Switched to model: {payload.model_id or 'Video Only'}"}


@app.get("/api/logs")
def get_logs():
    return logs.get_all_logs()


def generate_processed_frames(camera):
    # A shared capture/processor feeds every viewer without opening extra ESP32 connections.
    _, blank = cv2.imencode(".jpg", placeholder_frame())
    blank_bytes = blank.tobytes()
    while camera is None or not camera.stopped:
        frame = camera.frame() if camera is not None else None
        if frame is None:
            encoded = blank_bytes
        else:
            ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            encoded = jpeg.tobytes() if ok else blank_bytes
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded + b"\r\n"
        time.sleep(0.033)


@app.get("/api/cameras/{camera_id}/stream")
def camera_stream(camera_id: str):
    camera = camera_or_404(camera_id)
    return StreamingResponse(generate_processed_frames(camera),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(generate_processed_frames(manager.first()),
                             media_type="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vision Hub")
    parser.add_argument("--standalone", action="store_true", help="Use a laptop webcam for the first camera")
    parser.add_argument("--model", help="Load a model for the first camera on startup")
    args = parser.parse_args()
    standalone_mode = args.standalone
    startup_model = args.model
    print("Vision Hub running at http://localhost:5000")
    uvicorn.run(app, host="0.0.0.0", port=5000)
