import cv2
import threading
import time
import numpy as np
import database
import os
from ascend_inference import FaceSystem


RECOGNITION_THRESHOLD = 0.5


class VideoCamera(object):
    def __init__(self, face_system):
        self.lock = threading.Lock()
        self.face_system = face_system
        self.last_frame = None
        self.last_status = {
            'status': 'idle',
            'name': None,
            'attendance': None,
            'message': '等待识别',
            'time': None,
            'similarity': None,
            'sequence': 0
        }
        self.status_sequence = 0
        self.running = True
        self.last_check_time = 0
        self.check_interval = 2.0 # Check face every 2 seconds
        
        self.video = cv2.VideoCapture(0)
        if not self.video.isOpened():
            print("Error: Could not open video device 0. Please check permissions (sudo chmod 666 /dev/video0).")
            # Don't set running=False here, or at least handle it gracefully.
            # But more importantly, self.lock MUST be initialized before return
            # self.running = False # Let it run but just loop empty?
            # Better: Keep running True but check isOpened in update loop, 
            # and allow retry if needed, or just fail gracefully.
            pass

        # Try to set resolution
        if self.video.isOpened():
            self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Start background thread
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True
        self.thread.start()

    def __del__(self):
        self.running = False
        if hasattr(self, 'video') and self.video.isOpened():
            self.video.release()

    def update(self):
        while self.running:
            if not self.video.isOpened():
                break
                
            success, frame = self.video.read()
            if not success:
                time.sleep(0.1)
                continue
            
            with self.lock:
                self.last_frame = frame.copy()
            
            # Auto Check-in Logic
            current_time = time.time()
            if current_time - self.last_check_time > self.check_interval:
                self.last_check_time = current_time
                self.process_attendance(frame)
            
            time.sleep(0.03) # ~30 FPS

    def get_frame(self):
        with self.lock:
            if self.last_frame is None:
                return None

            frame = self.last_frame.copy()
            # 检测并绘制人脸框
            faces = self.face_system.detect(frame)
            for (x1, y1, x2, y2) in faces:
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)

            ret, jpeg = cv2.imencode('.jpg', frame)
            return jpeg.tobytes()

    def get_snapshot(self):
        with self.lock:
            if self.last_frame is None:
                return None
            return self.last_frame.copy()

    def get_status(self):
        with self.lock:
            return dict(self.last_status)

    def set_status(self, status, name=None, attendance=None, message=None, similarity=None):
        self.status_sequence += 1
        payload = {
            'status': status,
            'name': name,
            'attendance': attendance,
            'message': message,
            'time': database.format_timestamp(database.get_beijing_now()),
            'similarity': similarity,
            'sequence': self.status_sequence
        }
        with self.lock:
            self.last_status = payload

    def find_best_match(self, embedding):
        users = database.get_users()
        max_sim = -1.0
        best_match = None

        for u in users:
            db_emb = np.frombuffer(u['embedding'], dtype=np.float32)
            sim = np.dot(embedding, db_emb) / (np.linalg.norm(embedding) * np.linalg.norm(db_emb) + 1e-6)
            if sim > max_sim:
                max_sim = sim
                best_match = u

        return best_match, max_sim

    def process_attendance(self, frame):
        # Detect
        faces = self.face_system.detect(frame)
        if len(faces) == 0:
            self.set_status('no_face', message='未检测到人脸')
            return

        # Pick largest face
        best_face = max(faces, key=lambda b: (b[2]-b[0]) * (b[3]-b[1]))
        x1, y1, x2, y2 = map(int, best_face)
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        face_img = frame[y1:y2, x1:x2]
        if face_img.size == 0:
            self.set_status('no_face', message='未检测到有效人脸')
            return

        # Recognition
        emb = self.face_system.get_embedding(face_img)

        # Match
        best_match, max_sim = self.find_best_match(emb)
        if not best_match or max_sim <= RECOGNITION_THRESHOLD:
            self.set_status(
                'unregistered',
                message='未注册',
                similarity=float(max_sim)
            )
            print(f"Unregistered face detected ({max_sim:.2f})")
            return

        user_id = best_match['id']
        attendance = database.add_attendance(user_id, 'camera_auto', None)
        if attendance['created']:
            os.makedirs('uploads', exist_ok=True)
            filename = f"attendance_{user_id}_{int(time.time())}.jpg"
            filepath = os.path.join('uploads', filename)
            cv2.imwrite(filepath, face_img)
            database.update_attendance_image(attendance['id'], filename)
            message = f"{best_match['name']} Welcome!"
            attendance_status = 'created'
        else:
            message = f"{best_match['name']} 已经考勤"
            attendance_status = 'already_attended'

        self.set_status(
            'recognized',
            name=best_match['name'],
            attendance=attendance_status,
            message=message,
            similarity=float(max_sim)
        )
        print(f"User {best_match['name']} identified ({max_sim:.2f}) - {attendance_status}")
