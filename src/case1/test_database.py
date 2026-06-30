import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import database


BEIJING_TZ = timezone(timedelta(hours=8))


class DatabaseBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_name = database.DB_NAME
        database.DB_NAME = os.path.join(self.tmpdir.name, "attendance.db")
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.old_db_name
        self.tmpdir.cleanup()

    def fetch_attendance_rows(self):
        conn = sqlite3.connect(database.DB_NAME)
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute("SELECT * FROM attendance ORDER BY id")]
        conn.close()
        return rows

    def test_add_user_stores_beijing_time(self):
        with patch(
            "database.get_beijing_now",
            return_value=datetime(2026, 6, 30, 21, 0, 5, tzinfo=BEIJING_TZ),
            create=True,
        ):
            database.add_user("张三", b"embedding", "avatar.jpg")

        users = database.get_users()
        self.assertEqual(users[0]["created_at"], "2026-06-30 21:00:05")

    def test_add_attendance_records_only_first_checkin_per_beijing_day(self):
        user_id = database.add_user("李四", b"embedding", "avatar.jpg")

        with patch(
            "database.get_beijing_now",
            side_effect=[
                datetime(2026, 6, 30, 21, 0, 0, tzinfo=BEIJING_TZ),
                datetime(2026, 6, 30, 21, 30, 0, tzinfo=BEIJING_TZ),
            ],
            create=True,
        ):
            first = database.add_attendance(user_id, "camera_auto", "first.jpg")
            second = database.add_attendance(user_id, "camera_auto", "second.jpg")

        rows = self.fetch_attendance_rows()
        self.assertEqual(len(rows), 1)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(rows[0]["timestamp"], "2026-06-30 21:00:00")
        self.assertEqual(second["timestamp"], "2026-06-30 21:00:00")

    def test_delete_users_removes_selected_users_and_their_attendance(self):
        first_id = database.add_user("王五", b"embedding-1", "first.jpg")
        second_id = database.add_user("赵六", b"embedding-2", "second.jpg")
        third_id = database.add_user("孙七", b"embedding-3", "third.jpg")
        database.add_attendance(first_id, "manual", "first_attendance.jpg")
        database.add_attendance(second_id, "manual", "second_attendance.jpg")
        database.add_attendance(third_id, "manual", "third_attendance.jpg")

        deleted = database.delete_users([first_id, second_id])

        self.assertEqual(deleted, 2)
        remaining_users = database.get_users()
        self.assertEqual([user["id"] for user in remaining_users], [third_id])
        remaining_attendance = self.fetch_attendance_rows()
        self.assertEqual([row["user_id"] for row in remaining_attendance], [third_id])

    def test_get_attendance_treats_legacy_utc_rows_as_beijing_day(self):
        conn = sqlite3.connect(database.DB_NAME)
        try:
            conn.execute("DELETE FROM users")
            conn.execute("DELETE FROM attendance")
            conn.execute("DELETE FROM metadata WHERE key = ?", (database.BEIJING_MIGRATION_KEY,))
            conn.execute(
                "INSERT INTO users (name, embedding, avatar, created_at) VALUES (?, ?, ?, ?)",
                ("周八", b"embedding", "avatar.jpg", "2026-06-30 13:00:00"),
            )
            user_id = conn.execute("SELECT id FROM users").fetchone()[0]
            conn.execute(
                "INSERT INTO attendance (user_id, timestamp, type, image_path) VALUES (?, ?, ?, ?)",
                (user_id, "2026-06-30 13:05:00", "manual", "legacy.jpg"),
            )
            conn.commit()
        finally:
            conn.close()

        database.init_db()

        with patch(
            "database.get_beijing_now",
            return_value=datetime(2026, 6, 30, 21, 30, 0, tzinfo=BEIJING_TZ),
        ):
            rows = database.get_attendance()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timestamp"], "2026-06-30 21:05:00")
        self.assertEqual(database.get_users()[0]["created_at"], "2026-06-30 21:00:00")


if __name__ == "__main__":
    unittest.main()
