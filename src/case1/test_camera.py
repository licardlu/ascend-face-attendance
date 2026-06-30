import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import numpy as np


fake_cv2 = types.SimpleNamespace(
    imwrite=lambda path, img: True,
    rectangle=lambda *args, **kwargs: None,
    imencode=lambda ext, frame: (True, types.SimpleNamespace(tobytes=lambda: b"jpeg")),
    VideoCapture=lambda index: None,
    CAP_PROP_FRAME_WIDTH=3,
    CAP_PROP_FRAME_HEIGHT=4,
)
fake_ascend = types.SimpleNamespace(FaceSystem=object)
sys.modules.setdefault("cv2", fake_cv2)
sys.modules.setdefault("ascend_inference", fake_ascend)

import camera
import database


BEIJING_TZ = timezone(timedelta(hours=8))


class NoopLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeFaceSystem:
    def __init__(self, embedding):
        self.embedding = embedding.astype(np.float32)

    def detect(self, frame):
        return [np.array([0, 0, frame.shape[1], frame.shape[0]], dtype=np.float32)]

    def get_embedding(self, face_img):
        return self.embedding


class CameraAttendanceTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_name = database.DB_NAME
        database.DB_NAME = os.path.join(self.tmpdir.name, "attendance.db")
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.old_db_name
        self.tmpdir.cleanup()

    def make_camera(self, embedding):
        cam = camera.VideoCamera.__new__(camera.VideoCamera)
        cam.lock = NoopLock()
        cam.face_system = FakeFaceSystem(embedding)
        cam.last_status = {}
        cam.status_sequence = 0
        return cam

    def fetch_attendance_rows(self):
        conn = sqlite3.connect(database.DB_NAME)
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute("SELECT * FROM attendance ORDER BY id")]
        conn.close()
        return rows

    def test_unregistered_face_does_not_create_user_or_attendance(self):
        embedding = np.ones(512, dtype=np.float32)
        frame = np.ones((8, 8, 3), dtype=np.uint8)
        cam = self.make_camera(embedding)

        with patch("camera.print"):
            cam.process_attendance(frame)

        self.assertEqual(database.get_users(), [])
        self.assertEqual(self.fetch_attendance_rows(), [])
        self.assertEqual(cam.last_status["status"], "unregistered")
        self.assertEqual(cam.last_status["message"], "未注册")

    def test_registered_face_records_once_then_reports_already_attended(self):
        embedding = np.ones(512, dtype=np.float32)
        database.add_user("张三", embedding.tobytes(), "avatar.jpg")
        frame = np.ones((8, 8, 3), dtype=np.uint8)
        cam = self.make_camera(embedding)

        with patch(
            "database.get_beijing_now",
            side_effect=[
                datetime(2026, 6, 30, 21, 0, 0, tzinfo=BEIJING_TZ),
                datetime(2026, 6, 30, 21, 0, 0, tzinfo=BEIJING_TZ),
                datetime(2026, 6, 30, 21, 30, 0, tzinfo=BEIJING_TZ),
                datetime(2026, 6, 30, 21, 30, 0, tzinfo=BEIJING_TZ),
            ],
        ), patch("camera.print"):
            cam.process_attendance(frame)
            first_status = dict(cam.last_status)
            cam.process_attendance(frame)
            second_status = dict(cam.last_status)

        rows = self.fetch_attendance_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timestamp"], "2026-06-30 21:00:00")
        self.assertTrue(rows[0]["image_path"].startswith("attendance_"))
        self.assertEqual(first_status["attendance"], "created")
        self.assertEqual(first_status["message"], "张三 Welcome!")
        self.assertEqual(second_status["attendance"], "already_attended")
        self.assertEqual(second_status["message"], "张三 已经考勤")


if __name__ == "__main__":
    unittest.main()
