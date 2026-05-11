import mysql.connector

DB_CONFIG = {"host": "localhost", "user": "root", "password": "", "database": "nam_khoa_kiosk_db"}

def update_lab_status(order_id: str, lab_code: str, status: str):
    """Giả lập Y tá cập nhật trạng thái xét nghiệm."""
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE lab_order_items SET status = %s WHERE order_id = %s AND lab_code = %s",
            (status, order_id, lab_code)
        )
        if cur.rowcount > 0:
            conn.commit()
            print(f"✅ Đã chuyển trạng thái thành {status} cho {lab_code} của phiếu {order_id}.")
        else:
            print(f"❌ Không tìm thấy xét nghiệm {lab_code} trong phiếu {order_id} (hoặc trạng thái đã là {status} rồi).")
    except Exception as e:
        print(f"Lỗi: {e}")
    finally:
        cur.close()
        conn.close()

def display_pending_orders():
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT order_id, patient_id FROM lab_orders ORDER BY order_id LIMIT 5")
        orders = cur.fetchall()
        print("Các phiếu xét nghiệm gần đây (chọn 1 phiếu để test):")
        for o in orders:
            cur.execute("SELECT lab_code, status FROM lab_order_items WHERE order_id = %s", (o["order_id"],))
            items = cur.fetchall()
            print(f" - {o['order_id']} (BN: {o['patient_id']}): " + ", ".join([f"{it['lab_code']}({it['status']})" for it in items]))
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    print("=== CÔNG CỤ MÔ PHỎNG CHECKPOINT BỆNH VIỆN ===")
    display_pending_orders()
    
    print("\nNhập thông tin để cập nhật trạng thái xét nghiệm:")
    o_id = input("Order ID (VD: 001 hoặc ORD-001): ").strip().upper()
    l_code = input("Mã phòng Lab (VD: Urine hoặc LAB_URINE): ").strip().upper()
    action = input("Chọn trạng thái (1 cho DONE, 2 cho PENDING) [mặc định: 1]: ").strip()
    
    if o_id and l_code:
        # Tự động thêm tiền tố nếu người dùng nhập tắt
        if o_id.isdigit():
            o_id = f"ORD-{int(o_id):03d}"
        elif not o_id.startswith("ORD-"):
            o_id = f"ORD-{o_id}"
            
        if not l_code.startswith("LAB_"):
            l_code = f"LAB_{l_code}"
            
        target_status = "PENDING" if action == "2" else "DONE"
        update_lab_status(o_id, l_code, target_status)
    else:
        print("Đã hủy.")
