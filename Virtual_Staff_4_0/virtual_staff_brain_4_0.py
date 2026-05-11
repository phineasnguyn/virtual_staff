"""
virtual_staff_brain_4_0.py
AI Kiosk — Bệnh viện Nam Khoa
Phiên bản 4.0: Hướng dẫn xét nghiệm + Số chờ khám + FAQ + Cấp cứu
"""

import os
import re
import threading
import time
import random
import mysql.connector
from mysql.connector import pooling
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Optional, List

# 0. LOGGER TẬP TRUNG
_log_lock = threading.Lock()
SEP = "─" * 62

def log_chat(patient: str, bot: str) -> None:
    with _log_lock:
        print(f"\n{SEP}")
        print(f" BỆNH NHÂN : {patient}")
        print(SEP)
        print(f" KIOSK     : {bot}")
        print(f"{SEP}\n")

def log_info(msg: str) -> None:
    with _log_lock:
        print(f"[INFO] {msg}")

def log_error(msg: str) -> None:
    with _log_lock:
        print(f"[LỖI] {msg}")

# 1. KẾT NỐI DATABASE
_BASE_DB = {"host": "localhost", "user": "root", "password": ""}
DB_NAME  = "nam_khoa_kiosk_db"

try:
    nk_pool = pooling.MySQLConnectionPool(
        pool_name="nk_pool",
        pool_size=5,
        database=DB_NAME,
        **_BASE_DB
    )
    print(f"[DB] Kết nối pool '{DB_NAME}' thành công.")
except Exception as e:
    nk_pool = None
    print(f"[DB LỖI] Không kết nối được DB: {e}")
    print("  → Chạy 'python fake_data_4_0.py' trước để tạo database!\n")

def _get_conn():
    if nk_pool is None:
        raise RuntimeError("DB pool chưa khởi tạo.")
    return nk_pool.get_connection()

# 2. KHỞI TẠO LLM 
MODEL_NAME = "gemma3:4b"

print(f"[LLM] Đang kết nối model '{MODEL_NAME}'...")
llm = ChatOllama(model=MODEL_NAME, temperature=0.2, num_predict=512, repeat_penalty=1.15)
print("[LLM] Sẵn sàng.\n")

# 3. LỊCH SỬ HỘI THOẠI
chat_history: list = []
_history_lock = threading.Lock()

def reset_memory():
    with _history_lock:
        chat_history.clear()
    log_info("Đã xóa bộ nhớ hội thoại.")

# 4. TRUY VẤN DATABASE
def db_get_lab_order(patient_id: str) -> dict | None:
    """Lấy phiếu chỉ định xét nghiệm của bệnh nhân."""
    conn = _get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT o.order_id, o.patient_name, o.order_date, d.full_name AS doctor_name, d.specialization "
            "FROM lab_orders o JOIN doctors d ON o.doctor_id = d.doctor_id "
            "WHERE o.patient_id = %s ORDER BY o.order_date DESC LIMIT 1",
            (patient_id.upper(),)
        )
        order = cur.fetchone()
        if not order:
            return None
        cur.execute(
            "SELECT i.test_number, i.lab_code, i.status, "
            "r.lab_name, r.room, r.floor, r.directions, r.avg_wait_mins "
            "FROM lab_order_items i JOIN lab_rooms r ON i.lab_code = r.lab_code "
            "WHERE i.order_id = %s AND i.status = 'PENDING'",
            (order["order_id"],)
        )
        items = cur.fetchall()
        
        # TỐI ƯU LỘ TRÌNH (Optimal Routing)
        # Sắp xếp theo Tầng (floor) -> Thời gian chờ ít nhất (avg_wait_mins)
        items.sort(key=lambda x: (x["floor"], x["avg_wait_mins"]))
        
        # Gán lại step_number động cho người dùng dễ hiểu
        for idx, item in enumerate(items, start=1):
            item["step_number"] = idx
            
        order["items"] = items
        return order
    finally:
        cur.close(); conn.close()

def db_issue_token(patient_name: str) -> str:
    """Phát số chờ mới, trả về token_number."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(CAST(token_number AS UNSIGNED)) FROM queue_tokens")
        row = cur.fetchone()
        next_num = (row[0] or 0) + 1
        token_number = f"{next_num:03d}"
        cur.execute(
            "INSERT INTO queue_tokens (patient_name, token_number, status) VALUES (%s, %s, 'WAITING')",
            (patient_name, token_number)
        )
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM queue_tokens WHERE status='WAITING' AND CAST(token_number AS UNSIGNED) < %s", (next_num,))
        ahead = cur.fetchone()[0]
        return token_number, ahead
    finally:
        cur.close(); conn.close()

def db_check_token(token_number: str) -> dict | None:
    """Tra cứu trạng thái số chờ."""
    conn = _get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT token_number, patient_name, status, issued_at, called_at FROM queue_tokens WHERE token_number = %s",
            (token_number.lstrip("0") or "0",)
        )
        # Try exact match first, then numeric
        result = cur.fetchone()
        if not result:
            padded = token_number.zfill(3)
            cur.execute(
                "SELECT token_number, patient_name, status, issued_at, called_at FROM queue_tokens WHERE token_number = %s",
                (padded,)
            )
            result = cur.fetchone()
        if result and result["status"] == "WAITING":
            num_val = int(result["token_number"])
            cur.execute("SELECT COUNT(*) AS c FROM queue_tokens WHERE status='WAITING' AND CAST(token_number AS UNSIGNED) < %s", (num_val,))
            result["ahead"] = cur.fetchone()["c"]
        else:
            if result:
                result["ahead"] = 0
        return result
    finally:
        cur.close(); conn.close()

def db_search_faq(query: str) -> str | None:
    """Tìm câu trả lời FAQ theo từ khóa."""
    conn = _get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT keywords, answer FROM hospital_faq")
        rows = cur.fetchall()
        q_lower = query.lower()
        for row in rows:
            for kw in row["keywords"].split(","):
                if kw.strip() in q_lower:
                    return row["answer"]
        return None
    finally:
        cur.close(); conn.close()


# 5. PHÁT HIỆN Ý ĐỊNH

EMERGENCY_KEYWORDS = [
    "gãy", "chảy máu", "tai nạn", "bỏng", "ngất", "chó cắn",
    "vết thương hở", "khó thở", "tức ngực", "đau ngực", "đau tim",
    "đột quỵ", "sốc", "nhồi máu", "co giật", "bất tỉnh", "hôn mê",
    "máu nhiều", "đau dữ dội", "không chịu được",
]

LAB_KEYWORDS = [
    "xét nghiệm", "phòng xét nghiệm", "lab", "đi xét nghiệm",
    "chỉ định", "bác sĩ chỉ", "phiếu xét nghiệm", "làm xét nghiệm",
    "siêu âm", "x-quang", "xquang", "nội soi", "điện tim",
    "phòng", "ở đâu", "đường đi", "hướng dẫn đi",
]

TOKEN_ISSUE_KEYWORDS = [
    "lấy số", "số thứ tự", "số chờ", "lấy số chờ",
    "đăng ký chờ", "chờ khám", "lấy phiếu chờ",
    "muốn lấy số", "cho tôi số",
]

TOKEN_STATUS_KEYWORDS = [
    "số của tôi", "đến lượt", "gọi chưa", "số bao nhiêu",
    "kiểm tra số", "tra số", "số chờ của tôi", "bao lâu nữa",
    "còn mấy người", "số mấy rồi",
]

ONLINE_CHECKIN_KEYWORDS = [
    "check in", "đã đặt online", "mã qr", "mã đặt", "mã online",
    "tôi đã đăng ký", "có mã", "checkin", "xác nhận số", "lấy số khám"
]

PATIENT_ID_RE = re.compile(r"\bBN[-\s]?(\d{3})\b", re.IGNORECASE)
TOKEN_NUM_RE  = re.compile(r"\b(\d{1,3})\b")
BOOKING_CODE_RE = re.compile(r"\b(ONL\d{3})\b", re.IGNORECASE)

def detect_intent(text: str, state: dict) -> str:
    q = text.lower()
    if any(kw in q for kw in EMERGENCY_KEYWORDS):
        return "EMERGENCY"
    if any(kw in q for kw in ONLINE_CHECKIN_KEYWORDS):
        return "ONLINE_CHECKIN"
    if any(kw in q for kw in TOKEN_STATUS_KEYWORDS):
        return "TOKEN_STATUS"
    if any(kw in q for kw in TOKEN_ISSUE_KEYWORDS):
        return "TOKEN_ISSUE"
    if any(kw in q for kw in LAB_KEYWORDS):
        return "LAB_GUIDANCE"
        
    # Nếu đang trong luồng hướng dẫn xét nghiệm, các từ khóa tiếp nối cũng tính là LAB_GUIDANCE
    if state.get("patient_id"):
        continuation_kws = ["tiếp", "xong", "đi đâu", "rồi sao"]
        if any(kw in q for kw in continuation_kws):
            return "LAB_GUIDANCE"
            
    return "UNKNOWN"

def extract_patient_id(text: str) -> str | None:
    m = PATIENT_ID_RE.search(text)
    return f"BN-{m.group(1)}" if m else None

def extract_token_number(text: str) -> str | None:
    m = TOKEN_NUM_RE.search(text)
    return m.group(1) if m else None

def extract_booking_code(text: str) -> str | None:
    m = BOOKING_CODE_RE.search(text)
    return m.group(1).upper() if m else None

# 6. CÁC HANDLER ĐỘC LẬP

def handle_emergency(query: str) -> str:
    return (
        "CẢNH BÁO KHẨN CẤP!\n"
        "Dạ tình trạng của cô/chú nghe có vẻ nghiêm trọng. "
        "Xin vui lòng **ngay lập tức** di chuyển ra "
        "[PHÒNG CẤP CỨU — cổng chính, rẽ TRÁI ngay lập tức]!\n"
        "Nếu không thể tự di chuyển, hãy gọi to để nhân viên hỗ trợ ạ!"
    )

def handle_lab_guidance(query: str, patient_id: str | None, state: dict) -> str:
    """Hướng dẫn bệnh nhân đến các phòng xét nghiệm theo chỉ định."""
    # Nếu chưa có patient_id → hỏi
    pid = patient_id or state.get("patient_id")
    if not pid:
        state["waiting_for"] = "patient_id_lab"
        return (
            "Dạ, để tra cứu chỉ định xét nghiệm, cô/chú vui lòng cung cấp "
            "**mã bệnh nhân** (ví dụ: BN-012) hoặc nhập tên đầy đủ ạ."
        )

    state["patient_id"] = pid
    order = db_get_lab_order(pid)
    if not order:
        return (
            f"Dạ, hệ thống không tìm thấy phiếu chỉ định xét nghiệm nào "
            f"cho mã **{pid}** ạ. Cô/chú vui lòng kiểm tra lại mã hoặc "
            "hỏi nhân viên tại Quầy Lễ tân số 1 ạ."
        )
        
    if len(order["items"]) == 0:
        return (
            f"Dạ, bệnh nhân **{order['patient_name']} ({pid})** hiện đã hoàn thành tất cả các xét nghiệm ạ. "
            "Cô/chú vui lòng quay lại phòng khám gặp Bác sĩ để nghe kết quả nhé."
        )

    current_step = order["items"][0]
    future_steps = order["items"][1:]

    current_step_text = (
        f"BƯỚC HIỆN TẠI (HỆ THỐNG GHI NHẬN CHƯA KHÁM):\n"
        f"Phòng: {current_step['lab_name']} ({current_step['room']})\n"
        f"Số XN: {current_step['test_number']} — Chờ ~{current_step['avg_wait_mins']} phút\n"
        f"Đường đi: {current_step['directions']}\n"
    )
    
    future_steps_text = ""
    if future_steps:
        for it in future_steps:
            future_steps_text += f"- Bước {it['step_number']}: {it['lab_name']} ({it['room']})\n"
    else:
        future_steps_text = "Không còn phòng nào khác. Đây là bước cuối cùng."

    system_prompt = (
        "Bạn là nhân viên Kiosk hướng dẫn tại bệnh viện Nam Khoa. "
        "Nhiệm vụ: Dựa vào DỮ LIỆU TỪ HỆ THỐNG bên dưới, hướng dẫn bệnh nhân đi khám.\n"
        "QUY TẮC NGHIÊM NGẶT CẦN TUÂN THỦ:\n"
        "1. Bạn CHỈ ĐƯỢC PHÉP hướng dẫn chi tiết đường đi của 'BƯỚC HIỆN TẠI'.\n"
        "2. Nếu bệnh nhân nói họ đã khám xong BƯỚC HIỆN TẠI, BẠN PHẢI TỪ CHỐI TIN HỌ vì hệ thống chưa cập nhật. "
        "Hãy nói: 'Dạ, hệ thống của bệnh viện chưa ghi nhận cô/chú khám xong phòng này. Cô/chú vui lòng đợi Y tá ở phòng khám đánh dấu hoàn thành trên hệ thống rồi quay lại đây hỏi tiếp nhé!'\n"
        "3. Tuyệt đối KHÔNG hướng dẫn đường đi của CÁC BƯỚC SAU ĐÓ. Chỉ có thể nhắc nhẹ tên phòng để bệnh nhân biết.\n"
        "4. Tuyệt đối KHÔNG tự ý chúc mừng hoàn thành hay bịa ra lịch hẹn bác sĩ.\n"
        "Xưng hô: 'cô/chú' hoặc 'anh/chị'. Trả lời tự nhiên, thân thiện bằng Tiếng Việt.\n\n"
        f"THÔNG TIN PHIẾU:\n"
        f"- Bệnh nhân: {order['patient_name']} ({pid})\n"
        f"- Bác sĩ chỉ định: {order['doctor_name']} ({order['specialization']})\n\n"
        f"{current_step_text}\n"
        f"CÁC BƯỚC SAU ĐÓ (Chỉ liệt kê tên phòng, cấm hướng dẫn đường):\n{future_steps_text}"
    )
    messages = [SystemMessage(content=system_prompt)]
    with _history_lock:
        messages.extend(list(chat_history[-4:]))
    messages.append(HumanMessage(content=query))

    try:
        response = llm.invoke(messages)
        return response.content.strip()
    except Exception as e:
        log_error(f"LLM lab guidance: {e}")
        # Fallback: trả về danh sách thô
        fallback = f"Dạ, đây là lộ trình xét nghiệm tối ưu của {order['patient_name']} ({pid}):\n"
        for it in order["items"]:
            fallback += f"  Bước {it['step_number']}: {it['lab_name']} — {it['room']} (Chờ {it['avg_wait_mins']}p)\n  → {it['directions']}\n"
        return fallback

def handle_token_issue(query: str, state: dict) -> str:
    """Phát số chờ khám mới."""
    name = state.get("pending_token_name")
    if not name:
        # Thử trích xuất tên từ câu hỏi
        # Ví dụ: "cho tôi số với, tên tôi là Nguyễn Văn Nam"
        match = re.search(r"(?:tên|là|tên tôi là|tên là)\s+([A-ZÀ-Ỹa-zà-ỹ\s]{4,40})", query, re.IGNORECASE)
        if match:
            name = match.group(1).strip().title()
        else:
            state["waiting_for"] = "token_name"
            return (
                "Dạ, để lấy số chờ, cô/chú vui lòng cho biết "
                "**họ và tên đầy đủ** để hệ thống ghi nhận ạ."
            )

    try:
        token_number, ahead = db_issue_token(name)
        state.pop("pending_token_name", None)
        state.pop("waiting_for", None)
        est_wait = ahead * 10  # ước tính 10 phút/người
        return (
            f"Dạ, hệ thống đã phát số chờ cho **{name}**!\n\n"
            f"Số chờ của cô/chú: {token_number}\n"
            f"Hiện có {ahead} người đứng trước.\n"
            f"Thời gian chờ ước tính: ~{est_wait} phút.\n\n"
            "Cô/chú vui lòng ngồi đợi tại sảnh chờ Tầng 1. "
            "Khi đến lượt, nhân viên sẽ gọi tên qua loa ạ. Chúc cô/chú sức khỏe!"
        )
    except Exception as e:
        log_error(f"Issue token: {e}")
        return "Dạ, hệ thống lấy số đang gặp sự cố. Cô/chú vui lòng ra Quầy Lễ tân số 1 để được hỗ trợ ạ."

def handle_token_status(query: str) -> str:
    """Tra cứu trạng thái số chờ."""
    token_num = extract_token_number(query)
    if not token_num:
        return (
            "Dạ, cô/chú vui lòng cung cấp **số chờ** "
            "(ví dụ: 'Số 042 của tôi đến lượt chưa?') để hệ thống tra cứu ạ."
        )

    result = db_check_token(token_num)
    if not result:
        return f"Dạ, hệ thống không tìm thấy số chờ **{token_num}**. Cô/chú vui lòng kiểm tra lại ạ."

    name = result.get("patient_name", "")
    status = result.get("status", "")
    ahead  = result.get("ahead", 0)

    if status == "WAITING":
        est_wait = ahead * 10
        return (
            f"Dạ, số **{result['token_number']}** ({name}) đang **CHỜ** ạ.\n"
            f"Còn {ahead} người đứng trước.\n"
            f"Ước tính khoảng {est_wait} phút nữa ạ.\n"
            "Mời cô/chú tiếp tục ngồi chờ tại sảnh ạ."
        )
    elif status == "CALLED":
        return (
            f"Số **{result['token_number']}** ({name}) đã được **GỌI** rồi ạ!\n"
            "Cô/chú nhanh vào phòng khám trước khi bị bỏ qua ạ. "
            "Nếu chưa vào kịp, vui lòng báo nhân viên để sắp xếp lại ạ."
        )
    else:
        return (
            f"Số **{result['token_number']}** ({name}) đã **HOÀN THÀNH** lượt khám ạ."
        )

def db_online_checkin(booking_code: str) -> dict | None:
    """Xác thực mã đặt khám online và cấp số khám bệnh."""
    conn = _get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM queue_tokens WHERE booking_code = %s", (booking_code,))
        result = cur.fetchone()
        if not result:
            return None
        
        # Cấp consultation_token nếu chưa có
        if not result["consultation_token"]:
            cur.execute("SELECT MAX(CAST(SUBSTRING(consultation_token, 2) AS UNSIGNED)) AS m FROM queue_tokens WHERE consultation_token IS NOT NULL")
            row = cur.fetchone()
            next_num = (row["m"] or 0) + 1
            c_token = f"C{next_num:03d}"
            
            cur.execute(
                "UPDATE queue_tokens SET consultation_token = %s, status = 'WAITING' WHERE booking_code = %s",
                (c_token, booking_code)
            )
            conn.commit()
            result["consultation_token"] = c_token
            result["status"] = 'WAITING'
        
        return result
    finally:
        cur.close(); conn.close()

def handle_online_checkin(query: str, state: dict) -> str:
    """Xử lý check-in online lấy số khám."""
    code = extract_booking_code(query) or state.get("pending_booking_code")
    if not code:
        state["waiting_for"] = "booking_code"
        return "Dạ, để check-in, cô/chú vui lòng đọc hoặc nhập **Mã đặt khám Online** (ví dụ: ONL001) ạ."
    
    result = db_online_checkin(code)
    state.pop("pending_booking_code", None)
    state.pop("waiting_for", None)
    
    if not result:
        return f"Dạ, hệ thống không tìm thấy mã đặt khám **{code}**. Cô/chú vui lòng kiểm tra lại ạ."
        
    return (
        f"Dạ, check-in thành công cho bệnh nhân **{result['patient_name']}**!\n\n"
        f"Số khám bệnh của cô/chú: {result['consultation_token']}**\n"
        "Cô/chú vui lòng vào phòng chờ và theo dõi màn hình, hoặc gặp bác sĩ chuyên khoa ngay nếu số đã được gọi ạ."
    )

def handle_faq(query: str) -> str:
    """Tra cứu ngân hàng câu hỏi thường gặp."""
    answer = db_search_faq(query)
    if answer:
        return answer
    # Nếu không tìm thấy trong DB → LLM trả lời hoặc placeholder
    return (
        "Dạ, thông tin này hiện chưa có trong hệ thống ạ. "
        "Cô/chú vui lòng hỏi trực tiếp nhân viên tại Quầy Lễ tân số 1 để được hỗ trợ ạ."
    )

def handle_unknown(query: str, state: dict) -> str:
    """LLM xử lý câu hỏi không rõ intent, có thể detect intent từ ngữ cảnh."""
    system_prompt = (
        "Bạn là nhân viên Kiosk thông minh tại bệnh viện Nam Khoa. "
        "Nhiệm vụ: Trả lời ngắn gọn, thân thiện bằng Tiếng Việt. "
        "Nếu câu hỏi liên quan đến y tế chuyên sâu, hướng dẫn bệnh nhân gặp bác sĩ. "
        "Không bịa thông tin. Nếu không biết, nói thẳng và mời ra quầy lễ tân.\n"
        "Các dịch vụ Kiosk có thể hỗ trợ:\n"
        "1. Tra cứu & hướng dẫn phòng xét nghiệm (cần mã BN)\n"
        "2. Lấy số chờ khám\n"
        "3. Kiểm tra số chờ\n"
        "4. Thông tin bệnh viện (giờ làm việc, wifi, nhà vệ sinh...)\n"
    )
    messages = [SystemMessage(content=system_prompt)]
    with _history_lock:
        messages.extend(list(chat_history[-4:]))
    messages.append(HumanMessage(content=query))

    try:
        response = llm.invoke(messages)
        return response.content.strip()
    except Exception as e:
        log_error(f"LLM unknown: {e}")
        return (
            "Dạ, xin lỗi hệ thống gặp sự cố nhỏ. "
            "Cô/chú vui lòng hỏi trực tiếp nhân viên tại Quầy số 1 ạ."
        )


# 7. XỬ LÝ TRẠNG THÁI HỘI THOẠI (STATE MACHINE)

def handle_waiting_state(query: str, state: dict) -> str | None:
    """Xử lý khi đang chờ input từ bệnh nhân (multi-turn)."""
    waiting = state.get("waiting_for")
    if not waiting:
        return None

    if waiting == "patient_id_lab":
        pid = extract_patient_id(query)
        if pid:
            state.pop("waiting_for", None)
            state["patient_id"] = pid
            return handle_lab_guidance(query, pid, state)
        else:
            # Thử tìm kiếm theo tên (hiện tại chưa hỗ trợ → hỏi lại)
            return (
                "Dạ, cô/chú vui lòng cung cấp đúng **mã bệnh nhân** "
                "(ví dụ: BN-012 hoặc BN-045) ạ."
            )

    if waiting == "token_name":
        # Coi toàn bộ input là tên
        name = query.strip().title()
        if len(name) >= 3:
            state["pending_token_name"] = name
            state.pop("waiting_for", None)
            return handle_token_issue(query, state)
        else:
            return "Dạ, cô/chú vui lòng nhập **họ và tên đầy đủ** ạ (ít nhất 3 ký tự)."

    if waiting == "booking_code":
        code = extract_booking_code(query)
        if code:
            state.pop("waiting_for", None)
            state["pending_booking_code"] = code
            return handle_online_checkin(query, state)
        else:
            return "Dạ, mã đặt khám không đúng định dạng. Cô/chú vui lòng nhập lại (ví dụ: ONL001) ạ."

    return None

# 8. HÀM CHÍNH

def process_query(query: str, state: dict) -> str:
    """Nhận câu hỏi và state hiện tại, trả về câu trả lời."""
    q_lower = query.lower().strip()

    # [0] Khẩn cấp — ưu tiên tuyệt đối
    if any(kw in q_lower for kw in EMERGENCY_KEYWORDS):
        response = handle_emergency(query)
        log_chat(query, response)
        with _history_lock:
            chat_history.append(HumanMessage(content=query))
            chat_history.append(AIMessage(content=response))
        return response

    # [1] Xử lý multi-turn state
    state_response = handle_waiting_state(query, state)
    if state_response:
        log_chat(query, state_response)
        with _history_lock:
            chat_history.append(HumanMessage(content=query))
            chat_history.append(AIMessage(content=state_response))
        return state_response

    # [2] Phát hiện intent
    intent = detect_intent(query, state)
    patient_id = extract_patient_id(query) or state.get("patient_id")

    if intent == "LAB_GUIDANCE":
        response = handle_lab_guidance(query, patient_id, state)
    elif intent == "ONLINE_CHECKIN":
        response = handle_online_checkin(query, state)
    elif intent == "TOKEN_ISSUE":
        response = handle_token_issue(query, state)
    elif intent == "TOKEN_STATUS":
        response = handle_token_status(query)
    else:
        # Thử FAQ trước LLM
        faq_answer = db_search_faq(query)
        if faq_answer:
            response = faq_answer
        else:
            response = handle_unknown(query, state)

    log_chat(query, response)
    with _history_lock:
        chat_history.append(HumanMessage(content=query))
        chat_history.append(AIMessage(content=response))
    return response


# 9. MAIN — DEMO TERMINAL

if __name__ == "__main__":
    print("=" * 62)
    print(" KIOSK BỆNH VIỆN NAM KHOA — VIRTUAL STAFF BRAIN 4.0")
    print("=" * 62)
    print("Gõ 'exit' để thoát | 'reset' để xóa lịch sử hội thoại\n")

    # State lưu thông tin xuyên suốt cuộc trò chuyện
    session_state: dict = {}
    last_active = time.time()
    TIMEOUT = 60 * 30  # 30 phút reset session

    while True:
        try:
            # Auto-reset sau timeout
            if time.time() - last_active > TIMEOUT:
                reset_memory()
                session_state.clear()
                print("[HỆ THỐNG] Phiên làm việc hết hạn. Đã làm mới.\n")

            user_input = input("Cô/chú hỏi: ").strip()
            last_active = time.time()

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                print("Tạm biệt! Chúc cô/chú sức khỏe ạ.")
                break
            if user_input.lower() == "reset":
                reset_memory()
                session_state.clear()
                print("[HỆ THỐNG] Đã làm mới phiên làm việc.\n")
                continue

            process_query(user_input, session_state)

        except KeyboardInterrupt:
            print("\nTạm biệt!")
            break
