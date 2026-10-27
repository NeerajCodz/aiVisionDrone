import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

import app
from camera_manager import CameraManager


class FakeCapture:
    def __init__(self, source, *args):
        self.source = source

    def isOpened(self):
        return "camera-offline" not in str(self.source)

    def read(self):
        time.sleep(0.01)
        value = 40 if "camera-one" in str(self.source) else 100
        return True, np.full((24, 32, 3), value, dtype=np.uint8)

    def release(self):
        pass


class FakeModel:
    def process_frame(self, frame):
        return frame + 10, []


def wait_until(predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Camera did not reach the expected state")


class MultipleCameraApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config = Path(self.directory.name) / "camera_config.json"
        self.patches = [
            patch.object(app, "CONFIG_PATH", self.config),
            patch.object(app, "DEFAULT_CAMERA_URL", None),
            patch.object(app, "standalone_mode", False),
            patch.object(app, "startup_model", None),
            patch("camera_manager.cv2.VideoCapture", FakeCapture),
            patch("camera_manager.load_model_module", return_value=FakeModel()),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(app.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for item in reversed(self.patches):
            item.stop()
        self.directory.cleanup()

    def add_camera(self, name, url):
        response = self.client.post("/api/cameras", json={"name": name, "url": url})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_cameras_stream_and_select_models_independently(self):
        self.assertEqual(self.client.get("/api/cameras").json(), [])
        first = self.add_camera("Front", "http://camera-one:81/stream")
        second = self.add_camera("Rear", "http://camera-two:81/stream")
        self.assertNotEqual(first["id"], second["id"])
        wait_until(lambda: all(c["status"] == "online" for c in self.client.get("/api/cameras").json()))

        response = self.client.post(f"/api/cameras/{first['id']}/model", json={"model_id": "example"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["model_id"], "example")
        wait_until(lambda: app.manager.get(first["id"]).frame() is not None and
                   int(app.manager.get(first["id"]).frame()[0, 0, 0]) == 50)
        self.assertEqual(int(app.manager.get(second["id"]).frame()[0, 0, 0]), 100)
        self.assertIsNone(app.manager.get(second["id"]).snapshot()["model_id"])
        chunk = next(app.generate_processed_frames(app.manager.get(first["id"])))
        self.assertTrue(chunk.startswith(b"--frame\r\nContent-Type: image/jpeg"))

        saved = json.loads(self.config.read_text(encoding="utf-8"))["cameras"]
        self.assertEqual([item["model_id"] for item in saved], ["example", None])
        restored = CameraManager(self.config, None)
        restored.start()
        try:
            self.assertEqual([item["model_id"] for item in restored.list()], ["example", None])
        finally:
            restored.stop()
        self.assertEqual(self.client.delete(f"/api/cameras/{first['id']}").status_code, 204)
        self.assertEqual([c["id"] for c in self.client.get("/api/cameras").json()], [second["id"]])
        self.assertEqual(self.client.get(f"/api/cameras/{first['id']}/stream").status_code, 404)

    def test_invalid_or_duplicate_urls_are_rejected_and_updates_persist(self):
        camera = self.add_camera("Front", "http://camera-one:81/stream")
        for url in ("file:///etc/passwd", "http://user:pass@camera/stream", "http://camera:99999/"):
            self.assertEqual(self.client.post("/api/cameras", json={"name": "Bad", "url": url}).status_code, 400)
        self.assertEqual(self.client.post("/api/cameras", json={"name": "Duplicate", "url": camera["url"]}).status_code, 400)
        response = self.client.patch(f"/api/cameras/{camera['id']}",
                                     json={"name": "Entrance", "url": "http://camera-new:81/stream"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "Entrance")
        saved = json.loads(self.config.read_text(encoding="utf-8"))["cameras"]
        self.assertEqual(saved[0]["url"], "http://camera-new:81/stream")
        self.assertEqual(self.client.post(f"/api/cameras/{camera['id']}/model", json={"model_id": None}).status_code, 200)

    def test_offline_camera_does_not_stop_other_feed(self):
        offline = self.add_camera("Offline", "http://camera-offline:81/stream")
        online = self.add_camera("Online", "http://camera-two:81/stream")
        wait_until(lambda: app.manager.get(offline["id"]).snapshot()["status"] == "offline" and
                   app.manager.get(online["id"]).snapshot()["status"] == "online")
        self.assertIsNone(app.manager.get(offline["id"]).frame())
        wait_until(lambda: app.manager.get(online["id"]).frame() is not None)
        self.assertEqual(int(app.manager.get(online["id"]).frame()[0, 0, 0]), 100)

    def test_empty_configuration_is_not_reseeded(self):
        self.assertEqual(self.client.get("/api/cameras").json(), [])
        restored = CameraManager(self.config, "http://old-name:81/stream")
        self.assertEqual(restored._configs, [])

    def test_standalone_creates_a_temporary_webcam(self):
        manager = CameraManager(Path(self.directory.name) / "standalone.json", None, webcam=True)
        manager.start()
        try:
            self.assertEqual(manager.list()[0]["name"], "Webcam")
            self.assertEqual(json.loads(manager.path.read_text(encoding="utf-8"))["cameras"], [])
        finally:
            manager.stop()


if __name__ == "__main__":
    unittest.main()
