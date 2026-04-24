import os
from dotenv import load_dotenv
from google import genai

# Nạp API Key từ file .env
load_dotenv()
api_key = os.environ.get("GOOGLE_API_KEY")

if not api_key:
    print("Không tìm thấy GOOGLE_API_KEY. Hãy kiểm tra lại file .env!")
else:
    # Khởi tạo Client theo chuẩn mới của Google
    client = genai.Client(api_key=api_key)
    
    print("=== DANH SÁCH CÁC MODEL BẠN ĐƯỢC PHÉP DÙNG ===")
    try:
        # Lấy danh sách model
        for model in client.models.list():
            print(model.name)
    except Exception as e:
        print(f"Lỗi khi lấy danh sách: {e}")