import random
from db_pipeline_modules.db_utils import init_services_db, get_db_connection

def create_and_seed_services_table():
    # 1. Khởi tạo Database và Bảng từ db_utils
    db_config = init_services_db()

    # 2. Kết nối an toàn qua Context Manager để nạp dữ liệu
    print("Đang nạp dữ liệu và làm mới thời gian chờ ngẫu nhiên...")
    with get_db_connection(db_config) as (conn, cursor):
        # --- DỮ LIỆU GIẢ LẬP ĐẦY ĐỦ CÁC CHUYÊN KHOA ---
        fake_data = [
            # ================= CẬN LÂM SÀNG (XÉT NGHIỆM) =================
            ("TEST_BLOOD", "Xét nghiệm máu tổng quát", "Khoa Xét nghiệm", "Phòng 101 - Tầng 1", 5, random.randint(5, 30), 60, "XÉT NGHIỆM CƠ BẢN: Làm ĐẦU TIÊN. Máy chạy kết quả 60 phút. Nhịn ăn."),
            ("TEST_URINE", "Tổng phân tích nước tiểu", "Khoa Xét nghiệm", "Phòng 102 - Tầng 1", 5, random.randint(5, 15), 30, "XÉT NGHIỆM CƠ BẢN: Thường làm cùng xét nghiệm máu."),
            ("IMG_USG", "Siêu âm tổng quát", "Khoa Chẩn đoán hình ảnh", "Phòng 205 - Tầng 2", 15, random.randint(15, 45), 0, "XÉT NGHIỆM CƠ BẢN: Yêu cầu nhịn tiểu nếu siêu âm ổ bụng/tiết niệu."),
            ("IMG_XRAY", "Chụp X-Quang", "Khoa Chẩn đoán hình ảnh", "Phòng 208 - Tầng 2", 10, random.randint(10, 20), 0, "XÉT NGHIỆM CƠ BẢN: Cần tháo vật dụng kim loại vùng chụp."),
            ("IMG_MRI", "Chụp MRI/CT", "Khoa Chẩn đoán hình ảnh", "Phòng 105 - Tầng 1", 30, random.randint(30, 60), 45, "XÉT NGHIỆM CHUYÊN SÂU: Chờ bác sĩ đọc phim 45p. BẮT BUỘC tháo thiết bị điện tử, kim loại."),
            ("TEST_ECG", "Đo Điện tâm đồ (ECG)", "Khoa Thăm dò chức năng", "Phòng 305 - Tầng 3", 10, random.randint(5, 20), 0, "XÉT NGHIỆM CƠ BẢN: Dành cho bệnh tim mạch, có kết quả in ngay."),
            ("ENDO_STOMACH", "Nội soi dạ dày/đại tràng", "Khoa Thăm dò chức năng", "Phòng 302 - Tầng 3", 20, random.randint(30, 60), 15, "XÉT NGHIỆM CHUYÊN SÂU: Cần chỉ định lâm sàng. Nhịn ăn tuyệt đối."),

            # ================= LÂM SÀNG (CÁC CHUYÊN KHOA) =================
            ("CLINIC_GASTRO", "Khám Tiêu hóa", "Khoa Nội Tiêu hóa", "Phòng 201 - Tầng 2", 15, random.randint(10, 30), 0, "KHÁM LÂM SÀNG: Đau bụng, ợ chua. Cần kết quả máu/siêu âm để chẩn đoán."),
            ("CLINIC_NEURO", "Khám Thần kinh", "Khoa Thần kinh", "Phòng 206 - Tầng 2", 20, random.randint(20, 50), 0, "KHÁM LÂM SÀNG: Đau đầu, chóng mặt, mất ngủ. Có thể cần kết hợp MRI sọ não."),
            ("CLINIC_CARDIO", "Khám Tim mạch", "Khoa Tim mạch", "Phòng 203 - Tầng 2", 15, random.randint(15, 40), 0, "KHÁM LÂM SÀNG: Tức ngực, huyết áp. BẮT BUỘC đo ECG trước khi vào phòng khám."),
            ("CLINIC_RESP", "Khám Hô hấp", "Khoa Hô hấp", "Phòng 204 - Tầng 2", 15, random.randint(15, 40), 0, "KHÁM LÂM SÀNG: Ho kéo dài, khó thở nhẹ. Thường được chỉ định chụp X-Quang phổi."),
            ("CLINIC_ENDO", "Khám Nội tiết", "Khoa Nội tiết", "Phòng 207 - Tầng 2", 15, random.randint(15, 30), 0, "KHÁM LÂM SÀNG: Tiểu đường, tuyến giáp. BẮT BUỘC lấy máu trước, chờ có kết quả xét nghiệm máu mới khám."),
            ("CLINIC_ORTHO", "Khám Cơ Xương Khớp", "Khoa Chấn thương", "Phòng 209 - Tầng 2", 15, random.randint(20, 50), 0, "KHÁM LÂM SÀNG: Đau nhức xương, khớp. Nên chụp X-Quang vùng đau trước khi gặp bác sĩ."),
            
            # --- CÁC KHOA ĐẶC THÙ (Mắt, Răng, Da, Sản) ---
            ("CLINIC_ENT", "Khám Tai Mũi Họng", "Khoa Tai Mũi Họng", "Phòng 210 - Tầng 2", 10, random.randint(5, 20), 0, "KHÁM LÂM SÀNG: Bác sĩ thường nội soi ngay tại phòng, không cần đi nơi khác."),
            ("CLINIC_EYE", "Khám Nhãn khoa (Mắt)", "Khoa Mắt", "Phòng 211 - Tầng 2", 15, random.randint(10, 35), 0, "KHÁM LÂM SÀNG: Giảm thị lực, đau mắt. Có thể phải nhỏ thuốc giãn đồng tử (ngồi chờ 30p mới khám được)."),
            ("CLINIC_DERMA", "Khám Da liễu", "Khoa Da liễu", "Phòng 212 - Tầng 2", 10, random.randint(10, 30), 0, "KHÁM LÂM SÀNG: Ngứa, dị ứng da, bong da, mụn. Thường khám trực tiếp, ít khi xét nghiệm trước."),
            ("CLINIC_DENTAL", "Khám Răng Hàm Mặt", "Khoa Răng Hàm Mặt", "Phòng 215 - Tầng 2", 20, random.randint(15, 45), 0, "KHÁM LÂM SÀNG: Chảy máu nướu, đau răng. Bác sĩ khám trực tiếp, có thể chụp X-Quang răng tại chỗ."),
            ("CLINIC_OBGYN", "Khám Sản Phụ khoa", "Khoa Phụ sản", "Phòng 310 - Tầng 3", 20, random.randint(20, 60), 0, "KHÁM LÂM SÀNG: Khám thai, bệnh lý nữ. Thường kết hợp siêu âm thai/đầu dò.")
        ]

        print("Đang nạp dữ liệu và làm mới thời gian chờ ngẫu nhiên...")
        insert_query = """
        INSERT INTO hospital_services 
        (service_id, service_name, department, room, est_duration_mins, current_wait_time_mins, machine_processing_time, medical_rule)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            current_wait_time_mins = VALUES(current_wait_time_mins),
            machine_processing_time = VALUES(machine_processing_time),
            medical_rule = VALUES(medical_rule);
        """
        
        cursor.executemany(insert_query, fake_data)
        conn.commit()
        
        print(f"=== HOÀN TẤT! Đã nạp thành công {cursor.rowcount} dịch vụ vào SQL ===")

if __name__ == "__main__":
    create_and_seed_services_table()