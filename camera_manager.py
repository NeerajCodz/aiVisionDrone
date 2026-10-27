"""Independent camera capture and model state for the dashboard."""
import importlib.util
import json
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit
from uuid import uuid4

import cv2
import numpy as np

import logs


ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "models"


def get_models():
    models = []
    for path in sorted(MODELS_DIR.iterdir()):
        metadata = path / "model.json"
        if path.is_dir() and metadata.is_file():
            with metadata.open(encoding="utf-8") as handle:
                model = json.load(handle)
            model["id"] = path.name
            models.append(model)
    return models


def validate_name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
        raise ValueError("Camera name must contain 1 to 100 characters.")
    return value.strip()


def validate_url(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError("Enter a valid HTTP or HTTPS camera stream URL.")
    value = value.strip()
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or
                parsed.username is not None or parsed.password is not None or
                parsed.fragment or any(ch.isspace() for ch in value)):
            raise ValueError
        # Accessing port validates malformed or out-of-range port numbers.
        parsed.port
    except ValueError:
        raise ValueError("Enter an HTTP or HTTPS stream URL without embedded credentials.") from None
    return value


def load_model_module(model_id):
    if model_id not in {item["id"] for item in get_models()}:
        raise ValueError("Unknown model.")
    path = MODELS_DIR / model_id / "main.py"
    spec = importlib.util.spec_from_file_location(f"camera_model_{uuid4().hex}", path)
    if spec is None or spec.loader is None:
        raise ValueError("Model could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "process_frame", None)):
        raise ValueError("Model has no frame processor.")
    return module


class Camera:
    def __init__(self, config, webcam=False):
        self.id = config["id"]
        self.name = config["name"]
        self.url = config["url"]
        self._webcam = webcam
        self._model_id = None
        self._model = None
        self._frame = None
        self._status = "connecting"
        self._error = None
        self._lock = threading.RLock()
        self.selection_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None

    def snapshot(self):
        with self._lock:
            return {"id": self.id, "name": self.name, "url": self.url,
                    "status": self._status, "model_id": self._model_id,
                    "error": self._error}

    def frame(self):
        with self._lock:
            return self._frame

    def start(self):
        self._thread = threading.Thread(target=self._run, name=f"camera-{self.id}", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)

    @property
    def stopped(self):
        return self._stop.is_set()

    def update(self, name, url):
        with self._lock:
            changed = self.url != url
            self.name, self.url = name, url
            if changed:
                self._webcam = False
                self._status, self._error, self._frame = "connecting", None, None
                self._wake.set()

    def set_model(self, model_id, module):
        with self._lock:
            self._model_id, self._model = model_id, module

    def _set_state(self, status, error=None, clear_frame=False):
        with self._lock:
            self._status, self._error = status, error
            if clear_frame:
                self._frame = None

    def _open(self, source):
        if isinstance(source, int):
            return cv2.VideoCapture(source)
        # Open/read deadlines keep a disconnected camera from blocking shutdown forever.
        return cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
        ])

    def _run(self):
        delay = 2
        while not self._stop.is_set():
            with self._lock:
                self._wake.clear()
                source = 0 if self._webcam else self.url
                self._status, self._error = "connecting", None
            capture = None
            try:
                capture = self._open(source)
                if not capture.isOpened():
                    raise RuntimeError("Could not open camera stream")
                if self._wake.is_set() or self._stop.is_set():
                    continue
                self._set_state("online")
                delay = 2
                logs.log(f"Camera {self.id}", "Connected to camera stream", "SUCCESS")
                while not self._stop.is_set() and not self._wake.is_set():
                    ok, frame = capture.read()
                    if self._wake.is_set() or self._stop.is_set():
                        break
                    if not ok or frame is None:
                        raise RuntimeError("Camera stream disconnected")
                    with self._lock:
                        model, model_id = self._model, self._model_id
                    if model is not None:
                        try:
                            frame, messages = model.process_frame(frame)
                            for message in messages:
                                logs.log(f"{self.id}/{model_id}", str(message), "AI")
                        except Exception as exc:
                            logs.log(f"Camera {self.id}", f"Model processing failed: {exc}", "ERROR")
                    if frame is not None and not self._wake.is_set() and not self._stop.is_set():
                        with self._lock:
                            # A URL change clears the last image and must not be
                            # overwritten by a frame from the previous source.
                            if not self._wake.is_set() and not self._stop.is_set():
                                self._frame = frame
            except Exception as exc:
                if not self._stop.is_set() and not self._wake.is_set():
                    self._set_state("offline", str(exc), clear_frame=True)
                    logs.log(f"Camera {self.id}", f"Stream unavailable; retrying in {delay}s", "WARNING")
            finally:
                if capture is not None:
                    capture.release()
            if not self._stop.is_set() and not self._wake.is_set():
                self._wake.wait(delay)
                delay = min(delay * 2, 30)


class CameraManager:
    def __init__(self, config_path, default_url, webcam=False):
        self.path = Path(config_path)
        self._lock = threading.RLock()
        self._workers = {}
        self._started = False
        self._webcam = webcam
        self._ephemeral_id = None
        if self.path.exists():
            try:
                with self.path.open(encoding="utf-8") as handle:
                    data = json.load(handle)
                self._configs = self._validate_configs(data)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                # Preserve a broken config rather than silently replacing it.
                raise RuntimeError(f"Could not read camera configuration: {exc}") from exc
        else:
            self._configs = ([{"id": uuid4().hex, "name": "Camera 1",
                               "url": validate_url(default_url), "model_id": None}]
                             if default_url else [])
            self._save()
        if webcam and not self._configs:
            self._ephemeral_id = uuid4().hex
            self._configs.append({"id": self._ephemeral_id, "name": "Webcam",
                                  "url": "webcam://0", "model_id": None})

    @staticmethod
    def _validate_configs(data):
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("cameras"), list):
            raise ValueError("Expected version 1 camera configuration.")
        configs, ids, urls = [], set(), set()
        for item in data["cameras"]:
            if not isinstance(item, dict):
                raise ValueError("Invalid camera entry.")
            camera_id = item["id"]
            if not isinstance(camera_id, str) or not camera_id.isalnum() or camera_id in ids:
                raise ValueError("Invalid or duplicate camera ID.")
            name, url = validate_name(item["name"]), validate_url(item["url"])
            model_id = item.get("model_id")
            if model_id is not None and not isinstance(model_id, str):
                raise ValueError("Invalid model ID.")
            if url in urls:
                raise ValueError("Duplicate camera URL.")
            ids.add(camera_id)
            urls.add(url)
            configs.append({"id": camera_id, "name": name, "url": url, "model_id": model_id})
        return configs

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            saved = [item for item in self._configs if item["id"] != self._ephemeral_id]
            json.dump({"version": 1, "cameras": saved}, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, self.path)

    def start(self, startup_model=None):
        with self._lock:
            if self._started:
                return
            self._started = True
            for index, config in enumerate(self._configs):
                camera = Camera(config, webcam=self._webcam and index == 0)
                self._workers[config["id"]] = camera
                model_id = startup_model if index == 0 and startup_model else config.get("model_id")
                if model_id:
                    try:
                        camera.set_model(model_id, load_model_module(model_id))
                    except Exception as exc:
                        logs.log(f"Camera {camera.id}", f"Could not load model {model_id}: {exc}", "ERROR")
                camera.start()

    def stop(self):
        with self._lock:
            workers = list(self._workers.values())
            self._workers = {}
            self._started = False
        for worker in workers:
            worker.stop()

    def list(self):
        with self._lock:
            return [self._workers[c["id"]].snapshot() for c in self._configs if c["id"] in self._workers]

    def get(self, camera_id):
        with self._lock:
            camera = self._workers.get(camera_id)
            if camera is None:
                raise KeyError(camera_id)
            return camera

    def first(self):
        with self._lock:
            return self._workers.get(self._configs[0]["id"]) if self._configs else None

    def add(self, name, url):
        name, url = validate_name(name), validate_url(url)
        with self._lock:
            if any(item["url"] == url for item in self._configs):
                raise ValueError("That camera URL is already configured.")
            config = {"id": uuid4().hex, "name": name, "url": url, "model_id": None}
            self._configs.append(config)
            try:
                self._save()
            except OSError:
                self._configs.pop()
                raise
            camera = Camera(config)
            self._workers[camera.id] = camera
            if self._started:
                camera.start()
            return camera.snapshot()

    def update(self, camera_id, name=None, url=None):
        with self._lock:
            camera = self.get(camera_id)
            config = next(item for item in self._configs if item["id"] == camera_id)
            new_name = validate_name(name) if name is not None else config["name"]
            new_url = validate_url(url) if url is not None else config["url"]
            if any(item["id"] != camera_id and item["url"] == new_url for item in self._configs):
                raise ValueError("That camera URL is already configured.")
            old = config.copy()
            old_ephemeral_id = self._ephemeral_id
            if camera_id == self._ephemeral_id and new_url != config["url"]:
                self._ephemeral_id = None
            config.update(name=new_name, url=new_url)
            try:
                self._save()
            except OSError:
                config.update(old)
                self._ephemeral_id = old_ephemeral_id
                raise
            camera.update(new_name, new_url)
            return camera.snapshot()

    def remove(self, camera_id):
        with self._lock:
            camera = self.get(camera_id)
            index = next(i for i, item in enumerate(self._configs) if item["id"] == camera_id)
            config = self._configs.pop(index)
            try:
                self._save()
            except OSError:
                self._configs.insert(index, config)
                raise
            del self._workers[camera_id]
        camera.stop()

    def select_model(self, camera_id, model_id):
        camera = self.get(camera_id)
        with camera.selection_lock:
            if model_id is not None and not isinstance(model_id, str):
                raise ValueError("Invalid model ID.")
            try:
                module = load_model_module(model_id) if model_id else None
            except Exception as exc:
                logs.log(f"Camera {camera_id}", f"Model load failed: {exc}", "ERROR")
                raise ValueError("Failed to load model.") from exc
            with self._lock:
                if self._workers.get(camera_id) is not camera:
                    raise KeyError(camera_id)
                config = next(item for item in self._configs if item["id"] == camera_id)
                previous = config.get("model_id")
                config["model_id"] = model_id or None
                try:
                    self._save()
                except OSError:
                    config["model_id"] = previous
                    raise
                camera.set_model(model_id or None, module)
                return camera.snapshot()


def placeholder_frame():
    blank = np.zeros((360, 640, 3), dtype=np.uint8)
    cv2.putText(blank, "Waiting for camera...", (110, 180), cv2.FONT_HERSHEY_SIMPLEX,
                1, (150, 150, 150), 2)
    return blank
