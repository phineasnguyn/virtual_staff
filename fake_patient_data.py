import mysql.connector

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'hospital_rag_db'
}

def seed_patient_records():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("Đang kiểm tra và cập nhật bảng 'patient_records'...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patient_records (
        patient_id VARCHAR(20) PRIMARY KEY,
        full_name VARCHAR(100),
        age INT,
        gender VARCHAR(10),
        chronic_conditions TEXT,
        allergies TEXT,
        past_history TEXT
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    """)

    # TẬP DỮ LIỆU 10 HỒ SƠ "BẪY" DÙNG ĐỂ TEST LOGIC AI
    fake_patients = [
        # 1. Ca Tim mạch cơ bản
        ("BN-001", "Trần Văn Ánh", 65, "Nam", "Tăng huyết áp, Đái tháo đường tuýp 2", "Dị ứng thuốc kháng sinh Penicillin", "Từng bị nhồi máu cơ tim năm 2023"),
        
        # 2. Ca Dị ứng thực phẩm cấp tính
        ("BN-002", "Nguyễn Thị Bình", 28, "Nữ", "Không có bệnh nền", "Dị ứng hải sản gây nổi mề đay, khó thở", "Chưa từng phẫu thuật"),
        
        # 3. Ca đã phẫu thuật tiêu hóa
        ("BN-003", "Lê Hoàng Cường", 45, "Nam", "Viêm loét dạ dày mạn tính", "Không phát hiện dị ứng", "Đã phẫu thuật cắt ruột thừa năm 2015, Cắt túi mật năm 2020"),
        
        # 4. BẪY CHỤP MRI: Bệnh nhân có kim loại trong người
        ("BN-004", "Phạm Văn Dũng", 55, "Nam", "Thoái hóa cột sống", "Không", "Đã phẫu thuật kết hợp xương đùi (có nẹp vít kim loại) năm 2022"),
        
        # 5. BẪY CHỤP CT/X-QUANG: Phụ nữ mang thai
        ("BN-005", "Hoàng Thu Trà", 30, "Nữ", "Mang thai tuần 24 (Tháng thứ 6)", "Dị ứng phấn hoa", "Khỏe mạnh"),
        
        # 6. BẪY DỊ ỨNG THUỐC CẢN QUANG (Cấm tiêm thuốc khi nội soi/chụp chiếu)
        ("BN-006", "Vũ Quốc Hưng", 50, "Nam", "Gout mạn tính", "Sốc phản vệ với Thuốc cản quang có I-ốt", "Sỏi thận"),
        
        # 7. BẪY HÔ HẤP (Hen suyễn)
        ("BN-007", "Đinh Bích Ngọc", 35, "Nữ", "Hen phế quản (Suyễn) nặng", "Dị ứng lông chó mèo", "Thường xuyên nhập viện vì cơn hen cấp"),
        
        # 8. BẪY NHÃN KHOA (Tiểu đường biến chứng)
        ("BN-008", "Ngô Khắc Việt", 60, "Nam", "Đái tháo đường tuýp 1 hơn 10 năm", "Không", "Đã mổ đục thủy tinh thể mắt trái"),
        
        # 9. BẪY NGOẠI KHOA (Đang dùng thuốc chống đông máu - cấm nhổ răng/phẫu thuật bừa bãi)
        ("BN-009", "Lý Mai Lan", 70, "Nữ", "Rung nhĩ, Đang uống thuốc chống đông máu Aspirin hàng ngày", "Không", "Thay van tim nhân tạo năm 2018"),
        
        # 10. Bệnh nhân hoàn toàn khỏe mạnh
        ("BN-010", "Bùi Tấn Phát", 22, "Nam", "Không", "Không", "Sinh viên, thể trạng tốt, chưa từng nằm viện")
    ]

    insert_query = """
    INSERT INTO patient_records 
    (patient_id, full_name, age, gender, chronic_conditions, allergies, past_history)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE 
        chronic_conditions=VALUES(chronic_conditions), 
        allergies=VALUES(allergies), 
        past_history=VALUES(past_history);
    """
    
    cursor.executemany(insert_query, fake_patients)
    conn.commit()
    print(f"=== Đã nạp thành công {cursor.rowcount} hồ sơ bệnh án ===")
    
    # In ra danh sách để QA dễ test
    print("\n[DANH SÁCH MÃ BỆNH NHÂN ĐỂ MÔ PHỎNG QUÉT THẺ]:")
    for bn in fake_patients:
        print(f"- {bn[0]}: {bn[1]} ({bn[2]} tuổi) -> {bn[4]} | Dị ứng: {bn[5]}")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    seed_patient_records()