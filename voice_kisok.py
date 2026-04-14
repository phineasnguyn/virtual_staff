import speech_recognition as sr
import os
import pygame

# BƯỚC QUAN TRỌNG NHẤT: Import "Bộ não" từ file RAG của bạn
# (Giả sử file RAG của bạn tên là virtual_staff_brain_3_0.py)
from virtual_staff_brain_3_0 import process_patient_query, fetch_patient_record, chat_history

# Khởi tạo âm thanh
pygame.mixer.init()

def speak(text):
    """Cái Miệng: Đọc văn bản thành tiếng"""
    print(f"\n LỄ TÂN (Đang nói): {text}")
    voice = "vi-VN-HoaiMyNeural" 
    file_name = "response_audio.mp3"
    
    os.system(f'edge-tts --voice {voice} --text "{text}" --write-media {file_name}')
    pygame.mixer.music.load(file_name)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
    pygame.mixer.music.unload()
    if os.path.exists(file_name): 
        os.remove(file_name)

def listen():
    """Cái Tai: Nghe và chuyển thành Text"""
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("\n Đang lọc ồn...")
        r.adjust_for_ambient_noise(source, duration=1)
        print(" LỄ TÂN ĐANG NGHE... (Hãy nói gì đó)")
        try:
            audio = r.listen(source, timeout=5, phrase_time_limit=10)
            text = r.recognize_google(audio, language="vi-VN")
            print(f" BẠN NÓI: {text}")
            return text
        except Exception:
            return ""

# ==========================================
# VÒNG LẶP CHÍNH CỦA KIOSK (Ghép Não và Tai/Miệng)
# ==========================================
if __name__ == "__main__":
    print("="*50)
    print(" KIOSK LỄ TÂN BỆNH VIỆN BẰNG GIỌNG NÓI ĐÃ BẬT")
    print("="*50)
    
    speak("Hệ thống đã khởi động. Xin chào quý khách!")

    # Có thể giả lập quét mã bệnh nhân ở đây
    current_patient_id = input(" Bác bảo vệ nhập mã bệnh nhân (hoặc Enter nếu khách mới): ").strip()
    record_text = fetch_patient_record(current_patient_id)
    reset_brain_memory() # Dọn sạch trí nhớ cũ trước khi bắt đầu
    print(record_text)

    # Vòng lặp giao tiếp
    while True:
        try:
            # 1. Cái Tai nghe bệnh nhân nói
            user_text = listen()
            
            if user_text:
                if user_text.lower() in ['tắt máy', 'nghỉ thôi', 'tạm biệt']:
                    speak("Dạ, chào tạm biệt và chúc sức khỏe!")
                    break
                
                # 2. Gửi Text vào "Bộ não" RAG để xử lý logic (Python Cảnh sát + AI)
                print(" Bộ não đang suy nghĩ...")
                brain_response = process_patient_query(user_text, record_text)
                
                
                # 3. Lấy kết quả từ Não đưa cho "Cái Miệng" đọc lên
                # Mẹo: Cắt bỏ các ký tự Markdown (**, *, #) để máy đọc mượt hơn, không đọc ký tự đặc biệt
                clean_response_for_voice = brain_response.replace("*", "").replace("#", "").replace("📍", "")
                
                speak(clean_response_for_voice)
                
        except KeyboardInterrupt:
            print("\nĐã tắt Kiosk thủ công.")
            break