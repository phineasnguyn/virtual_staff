# Hướng dẫn cài đặt môi trường và các package

Để chạy chương trình, bạn cần cài đặt các thư viện phụ thuộc (packages) được liệt kê trong file `requirements.txt`. Dưới đây là các bước hướng dẫn chi tiết:

## Bước 1: Yêu cầu hệ thống
- Đảm bảo máy tính của bạn đã cài đặt **Python** (khuyến nghị phiên bản 3.9 - 3.11).
- Nếu chưa có Python, bạn có thể tải và cài đặt tại [python.org](https://www.python.org/downloads/).

## Bước 2: Tạo môi trường ảo (Virtual Environment)
Việc sử dụng môi trường ảo giúp các package của dự án này không bị xung đột với các dự án khác trên máy tính của bạn.
Mở Terminal (hoặc Command Prompt / PowerShell trên Windows) tại thư mục gốc của dự án (`g:\RAG`) và chạy lệnh sau:

```bash
python -m venv venv
```

## Bước 3: Kích hoạt môi trường ảo
Trước khi cài đặt package, bạn cần kích hoạt môi trường ảo vừa tạo:

- **Trên Windows:**
  ```cmd
  venv\Scripts\activate
  ```

- **Trên macOS/Linux:**
  ```bash
  source venv/bin/activate
  ```
*(Sau khi kích hoạt, bạn sẽ thấy chữ `(venv)` xuất hiện ở đầu dòng lệnh).*

## Bước 4: Cài đặt các package cần thiết
Do dự án có sử dụng phiên bản `torch` (PyTorch) kèm CUDA (`cu124`), bạn nên cài đặt theo lệnh sau để tải đúng phiên bản hỗ trợ GPU (nếu máy có card NVIDIA):

```bash
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu124
```

Nếu trong quá trình cài đặt gặp lỗi liên quan đến phiên bản PyTorch hoặc bạn không sử dụng GPU, bạn có thể chạy lệnh cơ bản sau:
```bash
pip install -r requirements.txt
```

## Bước 5: Kiểm tra cài đặt
Sau khi chạy xong lệnh trên, hệ thống sẽ tự động tải và cài đặt toàn bộ các package cần thiết (như `langchain`, `qdrant-client`, `torch`, `transformers`, v.v.).

Bạn có thể kiểm tra danh sách các package đã cài đặt bằng lệnh:
```bash
pip list
```

---
**Lưu ý bổ sung:**
- Nếu bạn sử dụng hệ thống AI/RAG tích hợp API từ Google (Gemini) hoặc OpenAI, hãy đảm bảo rằng bạn đã tạo file `.env` và cung cấp các khóa API (`API_KEY`) cần thiết.
- Nếu gặp lỗi liên quan đến quyền (permission), hãy thêm `--user` vào cuối lệnh pip hoặc chạy terminal bằng quyền Administrator (trên Windows).
