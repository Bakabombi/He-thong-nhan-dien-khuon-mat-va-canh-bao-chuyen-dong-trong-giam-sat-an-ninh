import pickle
import cv2
import numpy as np
import threading
import time
import os
from deepface import DeepFace

THRESHOLD = 0.3  # Ngưỡng cosine similarity
EMBEDDING_FILE = "embeddings.pkl"
MODEL = "Facenet512"  # SFace nhanh hơn Facenet512

# Tải database embeddings
if os.path.exists(EMBEDDING_FILE):
    with open(EMBEDDING_FILE, "rb") as f:
        embeddings = pickle.load(f)
    print("✅ Đã tải embeddings database")
else:
    print("❌ Không tìm thấy embeddings.pkl! Hãy chạy script tạo database trước.")
    exit()

# Load mô hình Haar Cascade để nhận diện khuôn mặt
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

def cosine_similarity(vec1, vec2):
    """Tính độ tương đồng cosine giữa 2 vector"""
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

# Biến toàn cục để lưu kết quả nhận diện
recognized_name = "Đang nhận diện..."
last_recognition_time = 0
is_processing = False  # Đánh dấu đang xử lý nhận diện

def recognize_face(face_img):
    """Nhận diện khuôn mặt chạy trên một thread riêng"""
    global recognized_name, last_recognition_time, is_processing
    is_processing = True  # Đánh dấu đang xử lý

    try:
        emb_new = DeepFace.represent(img_path=face_img, model_name=MODEL, enforce_detection=False)[0]["embedding"]

        best_match = None
        highest_similarity = -1  # Giá trị similarity càng cao càng tốt

        for data in embeddings.values():
            similarity = cosine_similarity(np.array(emb_new), np.array(data["embedding"]))
            if similarity > highest_similarity:
                highest_similarity = similarity
                best_match = data["name"]

        if highest_similarity > THRESHOLD:
            recognized_name = best_match
        else:
            recognized_name = "Người lạ"

    except Exception as e:
        recognized_name = "Lỗi nhận diện"
        print("⚠️ Lỗi:", e)

    last_recognition_time = time.time()
    is_processing = False  # Xử lý xong

# Mở webcam
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)

    for (x, y, w, h) in faces:
        face_img = frame[y:y+h, x:x+w]

        # Chỉ nhận diện lại nếu đã qua 1 giây từ lần nhận diện trước
        if time.time() - last_recognition_time > 1.0 and not is_processing:
            threading.Thread(target=recognize_face, args=(face_img,)).start()

        # Vẽ khung nhận diện
        color = (0, 255, 0) if recognized_name != "Người lạ" else (0, 0, 255)
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        cv2.putText(frame, recognized_name, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    cv2.imshow("Face Recognition", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
