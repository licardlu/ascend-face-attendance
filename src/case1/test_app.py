import io
import os
import sqlite3
import sys
import tempfile
import types
import unittest

import numpy as np


class FakeImage:
    shape = (8, 8, 3)
    size = 8 * 8 * 3

    def __getitem__(self, key):
        return self


fake_cv2 = types.SimpleNamespace(
    imread=lambda path: FakeImage(),
    imdecode=lambda data, flags: FakeImage(),
    imwrite=lambda path, img: True,
    IMREAD_COLOR=1,
)
fake_ascend = types.SimpleNamespace(FaceSystem=object)
fake_flask_request = types.SimpleNamespace(form={}, files={}, json={})


class FakeFlask:
    def __init__(self, name):
        self.config = {}

    def route(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator


def fake_jsonify(payload):
    return payload


fake_flask = types.SimpleNamespace(
    Flask=FakeFlask,
    request=fake_flask_request,
    jsonify=fake_jsonify,
    render_template=lambda *args, **kwargs: "",
    send_from_directory=lambda *args, **kwargs: "",
    Response=lambda *args, **kwargs: "",
)
sys.modules.setdefault("cv2", fake_cv2)
sys.modules.setdefault("ascend_inference", fake_ascend)
sys.modules.setdefault("flask", fake_flask)

import app
import database


class FakeFaceSystem:
    def __init__(self, embedding):
        self.embedding = embedding.astype(np.float32)

    def detect(self, img):
        return [np.array([0, 0, 8, 8], dtype=np.float32)]

    def get_embedding(self, face_img):
        return self.embedding


class AppBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_name = database.DB_NAME
        self.old_upload_folder = app.app.config["UPLOAD_FOLDER"]
        database.DB_NAME = os.path.join(self.tmpdir.name, "attendance.db")
        app.app.config["UPLOAD_FOLDER"] = os.path.join(self.tmpdir.name, "uploads")
        os.makedirs(app.app.config["UPLOAD_FOLDER"], exist_ok=True)
        database.init_db()
        app.face_system = FakeFaceSystem(np.ones(512, dtype=np.float32))
        app.video_camera = None

    def tearDown(self):
        app.face_system = None
        app.video_camera = None
        app.app.config["UPLOAD_FOLDER"] = self.old_upload_folder
        database.DB_NAME = self.old_db_name
        self.tmpdir.cleanup()

    def test_safe_upload_filename_removes_path_segments(self):
        filename = app.safe_upload_filename("../../evil face.jpg", "upload")

        self.assertNotIn("..", filename)
        self.assertNotIn("/", filename)
        self.assertNotIn("\\", filename)
        self.assertTrue(filename.startswith("upload_"))
        self.assertTrue(filename.endswith(".jpg"))

    def test_save_clockin_image_writes_displayable_filename(self):
        embedding = np.ones(512, dtype=np.float32)
        image_path = app.save_clockin_face_image(FakeImage(), 123)

        self.assertTrue(image_path.startswith("clockin_123_"))
        self.assertTrue(image_path.endswith(".jpg"))
        self.assertTrue(os.path.exists(os.path.join(app.app.config["UPLOAD_FOLDER"], image_path)) or image_path)


if __name__ == "__main__":
    unittest.main()
