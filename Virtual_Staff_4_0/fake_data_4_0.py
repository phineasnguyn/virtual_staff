"""
fake_data_4_0.py
Tạo database `nam_khoa_kiosk_db` và insert toàn bộ dữ liệu mẫu cho
Virtual Staff Brain 4.0 — Bệnh viện Nam Khoa.

Chạy 1 lần: python fake_data_4_0.py
"""

import mysql.connector
import random
from datetime import datetime, timedelta

# ─── CẤU HÌNH ──────────────────────────────────────────────────
DB_CONFIG = {"host": "localhost", "user": "root", "password": ""}
DB_NAME   = "nam_khoa_kiosk_db"

# ─── 1. DỮ LIỆU GỐC ────────────────────────────────────────────

DOCTORS = [
    ("DR-001", "BS. Nguyễn Văn Hùng",  "Chuyên khoa Nam học",             "P.301 - Tầng 3", "Thứ 2-6: 7:30-11:30, 13:30-16:30"),
    ("DR-002", "BS. Trần Minh Đức",    "Chuyên khoa Tiết niệu",            "P.302 - Tầng 3", "Thứ 2-6: 7:30-11:30, 13:30-16:30"),
    ("DR-003", "BS. Lê Quang Vinh",    "Chuyên khoa Nam học & Sinh sản",   "P.303 - Tầng 3", "Thứ 2-7: 7:30-11:30"),
    ("DR-004", "BS. Phạm Thanh Long",  "Chuyên khoa Tiết niệu - Thận",     "P.304 - Tầng 3", "Thứ 2-6: 13:30-17:00"),
    ("DR-005", "BS. Hoàng Đức Thịnh",  "Chuyên khoa Nam khoa tổng quát",   "P.305 - Tầng 3", "Thứ 2-7: 7:30-12:00"),
]

LAB_ROOMS = [
    # code, tên phòng, phòng, tầng, hướng dẫn đường đi, thời gian chờ TB
    ("LAB_BLOOD",  "Xét nghiệm máu tổng quát",   "P.101 - Tầng 1", 1,
     "Từ sảnh chính đi thẳng khoảng 20m, rẽ phải, phòng đầu tiên bên trái ạ.", 20),
    ("LAB_URINE",  "Xét nghiệm nước tiểu",        "P.102 - Tầng 1", 1,
     "Từ sảnh chính đi thẳng khoảng 20m, rẽ phải, phòng thứ hai bên trái ạ.", 10),
    ("LAB_ULTRA",  "Siêu âm bụng tổng quát",      "P.103 - Tầng 1", 1,
     "Từ sảnh chính đi thẳng đến cuối hành lang, rẽ trái, phòng cuối cùng bên phải ạ.", 30),
    ("LAB_RESULT", "Nhận kết quả xét nghiệm",     "P.104 - Tầng 1", 1,
     "Từ sảnh chính đi thẳng, phòng cuối cùng bên phải ngay cạnh quầy thu ngân ạ.", 5),
    ("LAB_XRAY",   "Chụp X-Quang",                "P.201 - Tầng 2", 2,
     "Lên thang máy hoặc cầu thang bộ đến Tầng 2, ra khỏi thang rẽ phải, đi khoảng 15m, phòng đầu tiên bên phải ạ.", 25),
    ("LAB_ENDO",   "Nội soi tiết niệu",           "P.202 - Tầng 2", 2,
     "Lên thang máy hoặc cầu thang bộ đến Tầng 2, đi thẳng, rẽ trái tại ngã tư, phòng đầu tiên bên trái ạ.", 45),
    ("LAB_BIOPSY", "Sinh thiết mô",               "P.203 - Tầng 2", 2,
     "Lên thang máy hoặc cầu thang bộ đến Tầng 2, đi thẳng, rẽ trái tại ngã tư, phòng thứ hai bên trái ạ.", 60),
    ("LAB_ECG",    "Điện tim & Đo huyết áp",      "P.204 - Tầng 2", 2,
     "Lên thang máy hoặc cầu thang bộ đến Tầng 2, ra khỏi thang rẽ phải, đi thẳng đến cuối hành lang ạ.", 15),
]

# Tổ hợp xét nghiệm điển hình cho bệnh nhân nam khoa
LAB_COMBOS = [
    ["LAB_BLOOD", "LAB_URINE"],
    ["LAB_BLOOD", "LAB_URINE", "LAB_ULTRA"],
    ["LAB_BLOOD", "LAB_URINE", "LAB_XRAY"],
    ["LAB_BLOOD", "LAB_URINE", "LAB_ECG"],
    ["LAB_BLOOD", "LAB_URINE", "LAB_ULTRA", "LAB_XRAY"],
    ["LAB_BLOOD", "LAB_URINE", "LAB_BIOPSY"],
    ["LAB_BLOOD", "LAB_URINE", "LAB_ENDO"],
    ["LAB_BLOOD", "LAB_URINE", "LAB_ULTRA", "LAB_BIOPSY"],
    ["LAB_BLOOD", "LAB_ECG"],
    ["LAB_BLOOD", "LAB_URINE", "LAB_ENDO", "LAB_XRAY"],
]

LAST_NAMES  = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Đặng", "Bùi",
               "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Đinh", "Tô", "Từ", "Cao", "Võ"]
MID_NAMES   = ["Văn", "Đức", "Minh", "Quang", "Công", "Bá", "Hữu", "Thế", "Anh", "Tuấn",
               "Khắc", "Trọng", "Gia", "Tiến", "Xuân"]
FIRST_NAMES = ["Hùng", "Mạnh", "Dũng", "Tuấn", "Long", "Sơn", "Tùng", "Thắng", "Hải", "Bình",
               "Lâm", "Nam", "Hòa", "Khoa", "Đạt", "Tâm", "Phát", "Thành", "Trung", "Hiếu",
               "Phúc", "Quyết", "Hưng", "Đông", "Việt"]

FAQ_DATA = [
    ("giờ làm việc, mở cửa, đóng cửa, giờ hoạt động, làm việc",
     "Bệnh viện làm việc mấy giờ?",
     "Bệnh viện Nam Khoa làm việc Thứ 2 đến Thứ 7: sáng 7:00–11:30, chiều 13:00–17:00 ạ. Chủ Nhật bệnh viện nghỉ."),
    ("wifi, mật khẩu wifi, mạng internet, kết nối mạng",
     "Wifi bệnh viện ở đâu?",
     "Bệnh viện có Wifi miễn phí tên mạng 'BV_NamKhoa_Guest'. Cô/chú hỏi nhân viên lễ tân để lấy mật khẩu ạ."),
    ("nhà vệ sinh, toilet, wc, phòng vệ sinh",
     "Nhà vệ sinh ở đâu?",
     "Nhà vệ sinh nằm ở cuối hành lang Tầng 1, ngay cạnh cầu thang bộ ạ. Tầng 2 cũng có nhà vệ sinh ở phía bên trái thang máy ạ."),
    ("bãi đỗ xe, gửi xe, giữ xe, xe máy, ô tô",
     "Bãi giữ xe ở đâu?",
     "Bãi giữ xe nằm tại tầng hầm (B1) hoặc khu vực phía sau bệnh viện ạ. Phí giữ xe máy 5.000đ/lượt, ô tô 20.000đ/lượt."),
    ("canteen, căng tin, ăn uống, cửa hàng, quán ăn",
     "Căng-tin bệnh viện ở đâu?",
     "Căng-tin bệnh viện ở góc phải sảnh Tầng 1, phục vụ từ 6:30–17:00 ạ. Có đồ ăn nhẹ, nước uống và suất cơm trưa ạ."),
    ("atm, rút tiền, ngân hàng",
     "ATM ở đâu?",
     "Cây ATM đặt tại sảnh chính Tầng 1, gần cổng ra vào ạ. Hỗ trợ thẻ Visa, Mastercard và các thẻ ATM nội địa ạ."),
    ("thang máy, elevator, lên tầng",
     "Thang máy ở đâu?",
     "Thang máy nằm chính giữa sảnh chính ạ. Cô/chú đi thẳng từ cổng vào khoảng 15m là thấy biển chỉ dẫn ạ."),
    ("bảo hiểm, bhyt, bảo hiểm y tế",
     "Bệnh viện có nhận bảo hiểm y tế không?",
     "Bệnh viện hiện đang cập nhật thông tin về bảo hiểm y tế ạ. Cô/chú vui lòng hỏi trực tiếp quầy lễ tân số 1 để được tư vấn chính xác nhất ạ."),
    ("giá khám, chi phí, phí khám, bao nhiêu tiền",
     "Giá khám bao nhiêu?",
     "Giá khám tham khảo: Khám tổng quát từ 200.000đ, khám chuyên khoa từ 300.000đ. Chi phí xét nghiệm tùy theo chỉ định của bác sĩ ạ. Cô/chú có thể hỏi chi tiết tại quầy thu ngân ạ."),
    ("đặt lịch, hẹn khám, đăng ký, lịch khám",
     "Cách đặt lịch hẹn?",
     "Cô/chú có thể đặt lịch qua số hotline của bệnh viện hoặc đến trực tiếp quầy đăng ký Tầng 1 ạ. Thông tin hotline sẽ được cập nhật sớm ạ."),
    ("cấp cứu, phòng cấp cứu, emergency",
     "Phòng cấp cứu ở đâu?",
     "Phòng Cấp Cứu ở ngay cổng chính bên trái, có biển đỏ lớn ạ. Cô/chú đi thẳng từ cổng chính, rẽ trái ngay lập tức ạ."),
    ("thuốc, quầy thuốc, nhà thuốc, pharmacy",
     "Quầy thuốc ở đâu?",
     "Quầy thuốc bệnh viện nằm ở góc trái sảnh Tầng 1 ạ. Mở cửa cùng giờ bệnh viện, từ 7:00 đến 17:00 ạ."),
    ("thanh toán, thu ngân, trả tiền, nộp tiền",
     "Quầy thu ngân ở đâu?",
     "Quầy thu ngân nằm ở cuối hành lang Tầng 1, cạnh phòng nhận kết quả P.104 ạ. Cô/chú thanh toán sau khi có chỉ định từ bác sĩ ạ."),
]

# ─── 2. TẠO DB & BẢNG ──────────────────────────────────────────

def create_schema(cursor, conn):
    cursor.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")
    cursor.execute(f"CREATE DATABASE {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cursor.execute(f"USE {DB_NAME}")
    conn.commit()

    cursor.execute("""
        CREATE TABLE doctors (
            doctor_id      VARCHAR(10)  PRIMARY KEY,
            full_name      VARCHAR(100) NOT NULL,
            specialization VARCHAR(150),
            room           VARCHAR(50),
            schedule       VARCHAR(200)
        ) CHARACTER SET utf8mb4
    """)
    cursor.execute("""
        CREATE TABLE lab_rooms (
            lab_code      VARCHAR(20)  PRIMARY KEY,
            lab_name      VARCHAR(100) NOT NULL,
            room          VARCHAR(50),
            floor         TINYINT,
            directions    TEXT,
            avg_wait_mins INT DEFAULT 15
        ) CHARACTER SET utf8mb4
    """)
    cursor.execute("""
        CREATE TABLE lab_orders (
            order_id     VARCHAR(10)  PRIMARY KEY,
            patient_id   VARCHAR(10)  NOT NULL,
            patient_name VARCHAR(100),
            doctor_id    VARCHAR(10),
            order_date   DATE,
            FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id)
        ) CHARACTER SET utf8mb4
    """)
    cursor.execute("""
        CREATE TABLE lab_order_items (
            item_id     INT AUTO_INCREMENT PRIMARY KEY,
            order_id    VARCHAR(10),
            step_number TINYINT,
            lab_code    VARCHAR(20),
            test_number VARCHAR(20),
            status      ENUM('PENDING', 'DONE') DEFAULT 'PENDING',
            FOREIGN KEY (order_id)  REFERENCES lab_orders(order_id),
            FOREIGN KEY (lab_code) REFERENCES lab_rooms(lab_code)
        ) CHARACTER SET utf8mb4
    """)
    cursor.execute("""
        CREATE TABLE queue_tokens (
            token_id           INT AUTO_INCREMENT PRIMARY KEY,
            patient_name       VARCHAR(100),
            booking_source     ENUM('ONLINE','OFFLINE') DEFAULT 'OFFLINE',
            booking_code       VARCHAR(20) UNIQUE,
            token_number       VARCHAR(10),
            consultation_token VARCHAR(10),
            status             ENUM('WAITING','CALLED','DONE') DEFAULT 'WAITING',
            issued_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            called_at          DATETIME
        ) CHARACTER SET utf8mb4
    """)
    cursor.execute("""
        CREATE TABLE hospital_faq (
            faq_id   INT AUTO_INCREMENT PRIMARY KEY,
            keywords TEXT,
            question VARCHAR(250),
            answer   TEXT
        ) CHARACTER SET utf8mb4
    """)
    conn.commit()
    print("  [OK] Schema tạo xong.")

# ─── 3. INSERT DỮ LIỆU ─────────────────────────────────────────

def insert_doctors(cursor, conn):
    cursor.executemany(
        "INSERT INTO doctors VALUES (%s,%s,%s,%s,%s)", DOCTORS
    )
    conn.commit()
    print(f"  [OK] Đã insert {len(DOCTORS)} bác sĩ.")

def insert_lab_rooms(cursor, conn):
    cursor.executemany(
        "INSERT INTO lab_rooms VALUES (%s,%s,%s,%s,%s,%s)", LAB_ROOMS
    )
    conn.commit()
    print(f"  [OK] Đã insert {len(LAB_ROOMS)} phòng xét nghiệm.")

def insert_lab_orders(cursor, conn):
    doctor_ids  = [d[0] for d in DOCTORS]
    today       = datetime.today()
    order_rows  = []
    item_rows   = []

    for i in range(1, 51):
        patient_id   = f"BN-{i:03d}"
        patient_name = f"{random.choice(LAST_NAMES)} {random.choice(MID_NAMES)} {random.choice(FIRST_NAMES)}"
        doctor_id    = random.choice(doctor_ids)
        order_date   = (today - timedelta(days=random.randint(0, 3))).strftime("%Y-%m-%d")
        order_id     = f"ORD-{i:03d}"

        order_rows.append((order_id, patient_id, patient_name, doctor_id, order_date))

        combo = random.choice(LAB_COMBOS)
        for step, lab_code in enumerate(combo, start=1):
            test_number = f"XN{i:03d}-{step:02d}"
            item_rows.append((order_id, step, lab_code, test_number))

    cursor.executemany(
        "INSERT INTO lab_orders VALUES (%s,%s,%s,%s,%s)", order_rows
    )
    cursor.executemany(
        "INSERT INTO lab_order_items (order_id, step_number, lab_code, test_number) VALUES (%s,%s,%s,%s)",
        item_rows
    )
    conn.commit()
    print(f"  [OK] Đã insert 50 lab orders với {len(item_rows)} xét nghiệm.")

def insert_queue_tokens(cursor, conn):
    now     = datetime.now()
    rows    = []
    statuses_pool = (
        ["WAITING"] * 40 + ["CALLED"] * 20 + ["DONE"] * 40
    )
    random.shuffle(statuses_pool)

    used_names = set()
    for i in range(1, 101):
        while True:
            name = f"{random.choice(LAST_NAMES)} {random.choice(MID_NAMES)} {random.choice(FIRST_NAMES)}"
            if name not in used_names:
                used_names.add(name)
                break
        
        status = statuses_pool[i - 1]
        booking_source = random.choice(["ONLINE", "OFFLINE"])
        
        # Token number là số thứ tự xếp hàng chung
        token_number = f"Q{i:03d}"
        
        if booking_source == "ONLINE":
            booking_code = f"ONL{i:03d}"
            # Nếu đang chờ, nghĩa là chưa check-in -> chưa có số khám.
            # Nếu đã CALLED hoặc DONE, coi như đã check-in và có số khám.
            consultation_token = f"C{i:03d}" if status != "WAITING" else None
        else:
            booking_code = None
            consultation_token = f"C{i:03d}"

        issued_at    = now - timedelta(minutes=random.randint(5, 120))
        called_at    = (issued_at + timedelta(minutes=random.randint(5, 40))) if status in ("CALLED", "DONE") else None
        
        rows.append((name, booking_source, booking_code, token_number, consultation_token, status, issued_at, called_at))

    cursor.executemany(
        "INSERT INTO queue_tokens (patient_name, booking_source, booking_code, token_number, consultation_token, status, issued_at, called_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        rows
    )
    conn.commit()
    print(f"  [OK] Đã insert 100 số chờ (40 WAITING | 20 CALLED | 40 DONE).")

def insert_faq(cursor, conn):
    cursor.executemany(
        "INSERT INTO hospital_faq (keywords, question, answer) VALUES (%s,%s,%s)",
        FAQ_DATA
    )
    conn.commit()
    print(f"  [OK] Đã insert {len(FAQ_DATA)} câu FAQ.")

# ─── 4. MAIN ───────────────────────────────────────────────────

def main():
    print("=== TẠO DATABASE nam_khoa_kiosk_db ===\n")
    conn   = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("[1] Tạo schema...")
    create_schema(cursor, conn)
    cursor.execute(f"USE {DB_NAME}")

    print("[2] Insert dữ liệu...")
    insert_doctors(cursor, conn)
    insert_lab_rooms(cursor, conn)
    insert_lab_orders(cursor, conn)
    insert_queue_tokens(cursor, conn)
    insert_faq(cursor, conn)

    cursor.close()
    conn.close()
    print("\n=== HOÀN THÀNH! Database sẵn sàng cho Brain 4.0 ===")

if __name__ == "__main__":
    main()
