# Bệnh Viện Nam Khoa - Kiosk Virtual Staff 4.0

Phiên bản Kiosk Y Tế 4.0 tích hợp luồng khám bệnh nâng cao, hệ thống xếp hàng tự động và tính toán lộ trình tối ưu cho bệnh nhân.

## Tính Năng Mới
- **Hỗ trợ Đăng Ký Online**: Nhận diện bệnh nhân đã đặt trước qua mã (VD: `ONL001`) và tự động cấp Số khám bệnh chuyên khoa.
- **Tính Toán Lộ Trình Xét Nghiệm Tối Ưu**: Sắp xếp thứ tự các phòng khám dựa trên tầng lầu và thời gian chờ ngắn nhất, giúp tối ưu thời gian di chuyển.
- **Hệ Thống Checkpoint**: Theo dõi tiến độ xét nghiệm (PENDING / DONE). Tự động hướng dẫn đường đi tiếp theo hoặc nhắc nhở bệnh nhân quay lại phòng trước đó nếu y tá chưa xác nhận.
- **Khắc Phục Hallucination**: Tích hợp các rào cản prompt ngăn chặn AI tự bịa tiến độ khám khi dữ liệu hệ thống chưa được cập nhật.

## Hướng Dẫn Cài Đặt & Sử Dụng

### 1. Khởi Tạo Dữ Liệu 
Chạy file sinh dữ liệu mẫu để tạo database và populate dữ liệu ban đầu.
```bash
python fake_data_4_0.py
```

### 2. Chạy Kiosk 
Khởi động Kiosk Assistant để tương tác:
```bash
python virtual_staff_brain_4_0.py
```

### 3. Công Cụ Mô Phỏng Checkpoint (Dành cho Tester)
Để kiểm tra tính năng tính toán lộ trình, bạn cần một công cụ giả lập hành động đánh dấu hoàn thành xét nghiệm của Y Tá.
Mở một terminal khác và chạy:
```bash
python simulate_hospital_actions.py
```
Nhập mã Phiếu (VD: `ORD-001` hoặc `001`) và mã Phòng Lab (VD: `LAB_URINE` hoặc `Urine`), sau đó chọn trạng thái `1` (DONE) hoặc `2` (PENDING) để cập nhật tiến trình của bệnh nhân. Kiosk sẽ lập tức thay đổi câu trả lời để phù hợp với trạng thái mới.
