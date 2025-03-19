import os
import pickle
import numpy as np
from deepface import DeepFace

FACES_DIR = "faces/"  # Thư mục chứa thư mục con của từng người
EMBEDDING_FILE = "embeddings.pkl"
MODEL = "Facenet512"  # Hoặc "SFace" nếu muốn nhanh hơn


def create_embeddings():
    embeddings = {}

    for person in os.listdir(FACES_DIR):
        person_path = os.path.join(FACES_DIR, person)
        if not os.path.isdir(person_path):  # Bỏ qua nếu không phải thư mục
            continue

        for img_name in os.listdir(person_path):
            img_path = os.path.join(person_path, img_name)
            try:
                emb = DeepFace.represent(img_path=img_path, model_name=MODEL)[0]["embedding"]
                embeddings[img_path] = {"name": person, "embedding": emb}
                print(f"✅ Đã xử lý: {img_path}")
            except Exception as e:
                print(f"⚠️ Lỗi với {img_path}: {e}")

    # Lưu embeddings vào file
    with open(EMBEDDING_FILE, "wb") as f:
        pickle.dump(embeddings, f)

    print("🎯 Hoàn tất! Đã lưu embeddings vào", EMBEDDING_FILE)


# Gọi hàm tạo embeddings
create_embeddings()
