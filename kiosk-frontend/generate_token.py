import os
from dotenv import load_dotenv
from livekit import api

# Đọc file .env ở thư mục gốc (g:\RAG\.env)
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

url = os.getenv("LIVEKIT_URL")
api_key = os.getenv("LIVEKIT_API_KEY")
api_secret = os.getenv("LIVEKIT_API_SECRET")

if not all([url, api_key, api_secret]):
    print(r"❌ Lỗi: Không tìm thấy LIVEKIT_URL, LIVEKIT_API_KEY hoặc LIVEKIT_API_SECRET trong file g:\RAG\.env")
    exit(1)

# Bạn có thể đổi tên room nếu muốn, nhưng frontend và backend phải vào chung 1 room.
# Tuy nhiên với LiveKit Agents (Worker), khi Frontend vào room này, Backend sẽ tự động được đánh thức và vào theo.
ROOM_NAME = "kiosk-room"

# Tạo token cho Frontend
token = api.AccessToken(api_key, api_secret) \
    .with_identity("patient-01") \
    .with_name("Bệnh nhân") \
    .with_grants(api.VideoGrants(
        room_join=True,
        room=ROOM_NAME,
    )) \
    .to_jwt()

print("\n" + "="*50)
print("✅ TẠO TOKEN THÀNH CÔNG! HÃY COPY THÔNG TIN SAU VÀO FILE .env.local")
print("="*50)
print(f"VITE_LIVEKIT_URL={url}")
print(f"VITE_LIVEKIT_TOKEN={token}")
print("="*50 + "\n")
