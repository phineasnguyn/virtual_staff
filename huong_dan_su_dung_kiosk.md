# Hướng dẫn sử dụng Hệ thống Trợ lý Y tế Ảo (Avatar Kiosk)

Tài liệu này hướng dẫn bạn cách khởi động toàn bộ hệ thống Trợ lý ảo, bao gồm **Backend xử lý AI (Python)** và **Frontend giao diện 3D (React)**.

---

## Phần 1: Khởi động Backend (Bộ não AI)

Backend chịu trách nhiệm xử lý ngôn ngữ, tra cứu cơ sở dữ liệu bệnh nhân/kiến thức y tế (RAG), và nhận diện cảnh báo nguy hiểm.

**Bước 1: Chạy mô hình ngôn ngữ (Local LLM)**
- Hệ thống đang dùng Ollama, vì vậy bạn cần bật ứng dụng **Ollama** lên trước.
- Đảm bảo mô hình bạn đang sử dụng trong code (ví dụ `llama3` hoặc `gemma`) đã được tải sẵn.

**Bước 2: Kích hoạt môi trường ảo (Virtual Environment)**
Mở Terminal ở thư mục `g:\RAG` và chạy:
```cmd
venv\Scripts\activate
```

**Bước 3: Chạy Agent LiveKit**
Bạn chạy file xử lý kết nối thoại thời gian thực (LiveKit Agent):
```cmd
python update_kiosk.py start
# Hoặc lệnh tương ứng với file chạy chính của bạn, ví dụ: 
# python livekit_kiosk.py start
```
*(Hệ thống sẽ kết nối với LiveKit Cloud và báo trạng thái sẵn sàng lắng nghe).*

---

## Phần 2: Khởi động Giao diện 3D (Frontend)

Frontend là nơi bệnh nhân tương tác, nhìn thấy Avatar 3D và giao tiếp trực tiếp qua Microphone.

**Bước 1: Mở Terminal thứ 2**
Di chuyển vào thư mục Frontend:
```cmd
cd g:\RAG\kiosk-frontend
```

**Bước 2: Chạy Server giao diện Web**
```cmd
npm run dev
```

**Bước 3: Truy cập hệ thống**
- Mở trình duyệt Web (khuyên dùng Google Chrome hoặc Edge) và truy cập: `http://localhost:5173`
- Giao diện "Hệ Thống Trợ Lý Y Tế Ảo" sẽ hiện ra.

---

## Phần 3: Kết nối & Sử dụng

Để Frontend và Backend nói chuyện được với nhau, chúng cần kết nối chung vào một "Phòng" (Room) trên LiveKit.

1. Tại màn hình của Web, hệ thống sẽ yêu cầu bạn nhập:
   - **LiveKit Server URL**: (Ví dụ: `wss://<project-id>.livekit.cloud`)
   - **Access Token**: Token kết nối dành cho người dùng (Client Token).
2. **Cách lấy Server URL và Token nhanh nhất:**
   Mình đã viết sẵn một script tự động tạo Token dựa trên file `.env` của Backend. Bạn chỉ cần mở một Terminal tại `g:\RAG` và chạy:
   ```cmd
   python kiosk-frontend\generate_token.py
   ```
   Copy toàn bộ kết quả in ra (bao gồm cả `VITE_LIVEKIT_URL` và `VITE_LIVEKIT_TOKEN`) và dán đè vào file `g:\RAG\kiosk-frontend\.env.local`. Khi có file này, lần sau mở web lên hệ thống sẽ tự động đăng nhập mà không cần hỏi lại.
3. Nhấn **Kết nối tới Avatar**.
4. Trình duyệt sẽ hỏi quyền sử dụng **Microphone**. Hãy bấm **Cho phép (Allow)**.
5. **Bắt đầu trò chuyện**:
   - Bạn chỉ cần nói trực tiếp vào Microphone (ví dụ: *"Chào bác sĩ, tôi bị đau bụng quá"*).
   - Backend sẽ phân tích, phản hồi lại và **Avatar 3D sẽ tự động cử động miệng** trả lời bạn ngay lập tức!

---

## 🛠 Khắc phục sự cố thường gặp (Troubleshooting)

- **Avatar không nhép môi:** Đảm bảo file `doctor.glb.glb` có hỗ trợ Blendshapes (khớp nối miệng) chuẩn của ReadyPlayerMe (cụ thể là `morphTargetDictionary['mouthOpen']`). Nếu dùng mô hình tùy chỉnh khác, bạn có thể cần điều chỉnh lại tên khớp miệng trong file `Avatar.jsx`.
- **Lỗi không kết nối được LiveKit:** Kiểm tra lại URL và API Token. Đảm bảo Backend và Frontend dùng chung dự án trên LiveKit Cloud.
- **Microphone không nhận tiếng:** Kiểm tra nút cấp quyền ở thanh địa chỉ của trình duyệt, hoặc kiểm tra kết nối mạng có bị tường lửa chặn WebRTC hay không.
