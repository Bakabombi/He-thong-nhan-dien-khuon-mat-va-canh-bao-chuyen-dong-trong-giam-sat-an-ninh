import cv2
import torch
import numpy as np
import telebot
from datetime import datetime
import os
import time
import requests
import threading
import pickle
from queue import Queue
from ultralytics import YOLO
from deepface import DeepFace

# ================= CẤU HÌNH HỆ THỐNG =================
THRESHOLD = 0.3
EMBEDDING_FILE = "embeddings.pkl"
MODEL_NAME = "Facenet512"
FRAME_SIZE = (640, 480)
TELEGRAM_BOT_TOKEN = "7664196118:AAHcWaQcXcwRoSWSPnH6pyUH54LoWofhXQQ"
TELEGRAM_CHAT_ID = "7736232579"
MOTION_THRESHOLD = 1000
ALERT_INTERVAL = 5
VIDEO_RECORD_DURATION = 10
BUZZER_API_URL = "http://192.168.137.121"  # Thay bằng IP thực tế của ESP8266
BUZZER_DURATION = 10  # Thời gian buzzer kêu (giây)

# ================= KHỞI TẠO THÀNH PHẦN =================
print("[Hệ thống] Đang khởi động các thành phần...")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
yolo = YOLO("yolov8s.pt")
task_queue = Queue()
cap = cv2.VideoCapture(0)
is_recording = False

# ================= QUẢN LÝ TRẠNG THÁI =================
class SystemState:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_alert = 0
        self.recognized_name = "Đang nhận diện..."


system_state = SystemState()

# ================= XỬ LÝ EMBEDDINGS =================
try:
    if os.path.exists(EMBEDDING_FILE):
        with open(EMBEDDING_FILE, 'rb') as f:
            embeddings = pickle.load(f)
        print(f"[Nhận diện] Đã tải {len(embeddings)} embeddings từ file")
    else:
        raise FileNotFoundError("Không tìm thấy file embeddings!")
except Exception as e:
    print(f"[Lỗi] {str(e)}")
    exit()

# ================= HÀM ĐIỀU KHIỂN BUZZER =================
def trigger_buzzer():
    """Gửi yêu cầu HTTP đến ESP8266 để bật buzzer trong 10 giây"""
    try:
        print("[Buzzer] 🚨 Gửi yêu cầu bật buzzer...")
        # Gửi yêu cầu bật buzzer
        response = requests.get(f"{BUZZER_API_URL}/buzzer/on", timeout=5)
        if response.status_code == 200:
            print("[Buzzer] ✅ Buzzer đã được bật")
        else:
            print(f"[Buzzer] ⚠ Lỗi khi bật buzzer: {response.status_code}")

        # Chờ 10 giây
        time.sleep(BUZZER_DURATION)

        # Gửi yêu cầu tắt buzzer
        response = requests.get(f"{BUZZER_API_URL}/buzzer/off", timeout=5)
        if response.status_code == 200:
            print("[Buzzer] ✅ Buzzer đã tắt")
        else:
            print(f"[Buzzer] ⚠ Lỗi khi tắt buzzer: {response.status_code}")
    except requests.RequestException as e:
        print(f"[Lỗi Buzzer] ❌ Không thể kết nối đến ESP8266: {str(e)}")

# ================= TIỆN ÍCH HỆ THỐNG =================
def get_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def create_directory(path):
    try:
        os.makedirs(path, exist_ok=True)
        print(f"[Hệ thống] Đã tạo thư mục {path}")
    except Exception as e:
        print(f"[Lỗi] Không thể tạo thư mục {path}: {str(e)}")

# ================= XỬ LÝ TELEGRAM =================
def send_to_telegram(photo_path, caption="📸 Ảnh từ camera"):
    try:
        with open(photo_path, "rb") as photo:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                files={"photo": photo},
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
            )
        print(f"[Telegram] Đã gửi ảnh: {photo_path}")
    except Exception as e:
        print(f"[Telegram] Lỗi gửi ảnh: {e}")

def send_video_to_telegram(video_path, caption="🎥 Video từ camera"):
    try:
        with open(video_path, "rb") as video:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo",
                files={"video": video},
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
            )
        print(f"[Telegram] Đã gửi video: {video_path}")
    except Exception as e:
        print(f"[Telegram] Lỗi gửi video: {e}")

def send_warning():
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": "⚠ Cảnh báo! Phát hiện người lạ!"}
        )
        print("[Cảnh báo] Đã gửi cảnh báo đến Telegram")
    except Exception as e:
        print(f"[Cảnh báo] Lỗi gửi cảnh báo: {e}")

# ================= XỬ LÝ LỆNH TELEGRAM =================
@bot.message_handler(commands=['photo'])
def capture_photo(message):
    print(f"[Telegram] Nhận lệnh chụp ảnh từ {message.from_user.username}")
    try:
        ret, frame = cap.read()
        if ret:
            create_directory("manual_captures")
            img_name = f"manual_captures/photo_{get_timestamp()}.jpg"
            cv2.imwrite(img_name, frame)
            print(f"[Hệ thống] Đã lưu ảnh thủ công: {img_name}")
            send_to_telegram(img_name)
            bot.reply_to(message, "📤 Ảnh đã được gửi!")
        else:
            print("[Hệ thống] Lỗi đọc frame từ camera")
            bot.reply_to(message, "❌ Không thể chụp ảnh!")
    except Exception as e:
        print(f"[Lỗi] {str(e)}")
        bot.reply_to(message, f"⚠ Lỗi hệ thống: {str(e)}")

@bot.message_handler(commands=['record'])
def record_video(message):
    global is_recording
    print(f"[Telegram] Nhận lệnh ghi video từ {message.from_user.username}")
    if is_recording:
        print("[Hệ thống] Đang ghi video khác")
        bot.reply_to(message, "⏳ Đang trong quá trình quay video khác...")
        return

    is_recording = True
    bot.reply_to(message, "🎥 Bắt đầu quay video...")

    try:
        create_directory("videos")
        video_name = f"videos/video_{get_timestamp()}.avi"
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        frame_size = (int(cap.get(3)), int(cap.get(4)))
        out = cv2.VideoWriter(video_name, fourcc, 20.0, frame_size)

        start_time = time.time()
        print(f"[Hệ thống] Bắt đầu ghi video {video_name}")
        while time.time() - start_time < VIDEO_RECORD_DURATION:
            ret, frame = cap.read()
            if ret:
                out.write(frame)

        out.release()
        print(f"[Hệ thống] Đã lưu video: {video_name}")
        send_video_to_telegram(video_name)
        bot.reply_to(message, "📤 Video đã được gửi!")
    except Exception as e:
        print(f"[Lỗi] Ghi video: {str(e)}")
        bot.reply_to(message, f"⚠ Lỗi khi quay video: {str(e)}")
    finally:
        is_recording = False

@bot.message_handler(commands=['warning'])
def send_bot_warning(message):
    try:
        print(f"[Telegram] Kích hoạt cảnh báo thủ công bởi {message.from_user.username}")
        send_warning()
        bot.reply_to(message, "⚠ Đã gửi cảnh báo!")
    except Exception as e:
        print(f"[Lỗi] {str(e)}")
        bot.reply_to(message, f"⚠ Lỗi hệ thống: {str(e)}")

# ================= LOGIC GIÁM SÁT CHÍNH =================
def async_worker():
    print("[Hệ thống] Worker bất đồng bộ đã khởi động")
    while True:
        task = task_queue.get()
        try:
            print(f"[Task] Đang xử lý task ({task_queue.qsize()} task chờ)")
            task()
        except Exception as e:
            print(f"[Lỗi Task] {str(e)}")
        task_queue.task_done()

threading.Thread(target=async_worker, daemon=True).start()

def process_alert(frame, faces, person_boxes):
    try:
        timestamp = get_timestamp()
        img_path = f"alerts/alert_{timestamp}.jpg"
        create_directory("alerts")

        # Vẽ các khung phát hiện
        for (x1, y1, x2, y2) in person_boxes:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)

        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        # Xử lý nhận diện
        best_match = "Người lạ"
        max_sim = 0
        recognition_result = ""
        caption = ""

        if len(person_boxes) > 0:
            if len(faces) > 0:
                try:
                    x, y, w, h = faces[0]
                    face_img = frame[y:y + h, x:x + w]

                    embedding = DeepFace.represent(
                        img_path=face_img,
                        model_name=MODEL_NAME,
                        enforce_detection=False,
                        detector_backend="opencv"
                    )[0]["embedding"]

                    # Tìm khuôn mặt khớp nhất
                    current_max_sim = 0
                    current_best_match = "Người lạ"

                    for name, data in embeddings.items():
                        sim = np.dot(embedding, data["embedding"]) / (
                                np.linalg.norm(embedding) * np.linalg.norm(data["embedding"]))
                        if sim > current_max_sim and sim > THRESHOLD:
                            current_max_sim = sim
                            current_best_match = os.path.basename(os.path.dirname(name))

                    best_match = current_best_match
                    max_sim = current_max_sim

                    if best_match != "Người lạ":
                        recognition_result = f"{best_match} ({max_sim:.2f})"
                        caption = f"✅ Nhận diện: {best_match} (Độ chính xác: {max_sim:.2f})"
                        print(f"[Nhận diện] ✅ Kết quả: {recognition_result}")
                    else:
                        recognition_result = "Khuôn mặt không khớp"
                        caption = "⚠️ Cảnh báo! Khuôn mặt không khớp với database"
                        print(f"[Nhận diện] ⚠️ Kết quả: Khuôn mặt không khớp")
                        # Kích hoạt buzzer khi phát hiện người lạ
                        threading.Thread(target=trigger_buzzer, daemon=True).start()
                        send_warning()

                except Exception as e:
                    print(f"[Lỗi Nhận diện] ❌ {str(e)}")
                    recognition_result = "Lỗi nhận diện khuôn mặt"
                    caption = "❌ Lỗi! Không thể nhận diện khuôn mặt"
            else:
                recognition_result = "Không phát hiện khuôn mặt"
                caption = "🔔 Phát hiện người nhưng không nhận diện được khuôn mặt"
                print(f"[Nhận diện] 🔔 Không phát hiện khuôn mặt")
                # Kích hoạt buzzer khi không nhận diện được khuôn mặt
                threading.Thread(target=trigger_buzzer, daemon=True).start()
                send_warning()
        else:
            recognition_result = "Không có người"
            caption = "ℹ️ Không phát hiện người trong khung hình"
            print(f"[Nhận diện] ℹ️ Không có người")

        # Thêm văn bản lên ảnh
        font = cv2.FONT_HERSHEY_DUPLEX
        font_scale = 0.8
        font_color = (255, 255, 255)  # Màu trắng
        thickness = 2
        line_spacing = 30

        time_text = f"Time: {timestamp}"
        status_text = f"Status: {recognition_result}"

        position_time = (10, 30)
        position_status = (10, 30 + line_spacing)

        text_size_time, _ = cv2.getTextSize(time_text, font, font_scale, thickness)
        text_size_status, _ = cv2.getTextSize(status_text, font, font_scale, thickness)
        background_top_left = (5, 5)
        background_bottom_right = (
            max(text_size_time[0], text_size_status[0]) + 15,
            30 + 2 * line_spacing
        )
        cv2.rectangle(frame, background_top_left, background_bottom_right, (0, 0, 0), -1)

        cv2.putText(frame, time_text, position_time, font, font_scale, font_color, thickness)
        cv2.putText(frame, status_text, position_status, font, font_scale, font_color, thickness)

        # Lưu ảnh
        cv2.imwrite(img_path, frame)
        print(f"[Cảnh báo] 💾 Đã lưu ảnh cảnh báo: {img_path}")

        # Gửi thông báo tới Telegram
        send_to_telegram(img_path, caption)

    except Exception as e:
        print(f"[Lỗi Xử lý Cảnh báo] ❌ {str(e)}")

def camera_loop():
    print("[Hệ thống] ✅ Luồng camera đã khởi động")
    prev_frame = None

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("[Lỗi] ❌ Không đọc được frame từ camera")
            break

        # Phát hiện chuyển động
        motion_detected = False
        if prev_frame is not None:
            gray1 = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(gray1, gray2)
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for c in contours:
                if cv2.contourArea(c) > MOTION_THRESHOLD:
                    motion_detected = True
                    break

        if motion_detected:
            print("[Phát hiện] 🔔 Phát hiện chuyển động")
            results = yolo(frame, verbose=False)
            person_boxes = []

            for r in results:
                for box in r.boxes:
                    if int(box.cls) == 0:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        person_boxes.append((x1, y1, x2, y2))

            if person_boxes:
                print(f"[Phát hiện] 👤 Tìm thấy {len(person_boxes)} người")
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 5)

                current_time = time.time()
                if current_time - system_state.last_alert > ALERT_INTERVAL:
                    task_queue.put(lambda: process_alert(frame.copy(), faces, person_boxes))
                    with system_state.lock:
                        system_state.last_alert = current_time
                    print("[Cảnh báo] 🚨 Đã thêm task cảnh báo vào hàng đợi")

        prev_frame = frame.copy()
        cv2.imshow("Security System", frame)

        if cv2.waitKey(1) == ord('q'):
            print("[Hệ thống] ⏹️ Đang tắt camera...")
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    print("[Hệ thống] Đang khởi tạo thư mục...")
    create_directory("alerts")
    create_directory("manual_captures")
    create_directory("videos")

    print("[Hệ thống] Khởi động thành công!")
    threading.Thread(target=camera_loop, daemon=True).start()
    bot.polling(none_stop=True)