import os
import re
import threading
from dotenv import load_dotenv

# Tải biến môi trường (như GOOGLE_API_KEY) từ file .env
load_dotenv()

# ── LOGGER TẬP TRUNG (chống chéo terminal) ───────────────────
_log_lock = threading.Lock()
SEP = "─" * 60

def log_exchange(patient_text: str, bot_text: str) -> None:
    """In một cặp hỏi-đáp hoàn chỉnh, thread-safe."""
    with _log_lock:
        print(f"\n{SEP}")
        print(f" BỆNH NHÂN : {patient_text}")
        print(SEP)
        print(f" LỄ TÂN    : {bot_text}")
        print(f"{SEP}\n")

def log_error(msg: str) -> None:
    with _log_lock:
        print(f"[LỖI] {msg}")
# ─────────────────────────────────────────────────────────────

import random
import time
import mysql.connector
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Literal, List
from mysql.connector import pooling

# --- 1. CẤU HÌNH HỆ THỐNG ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'hospital_rag_db'
}

db_pool = pooling.MySQLConnectionPool(
    pool_name="hospital_pool",
    pool_size=5,
    **DB_CONFIG
)

COLLECTION_NAME = "hospital_vector_index"
RERANK_THRESHOLD = -2.0

print("=== ĐANG KHỞI ĐỘNG HỆ THỐNG LỄ TÂN ẢO ĐIỀU HƯỚNG ===")
embed_model = SentenceTransformer('all-MiniLM-L6-v2')
rerank_model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
qdrant_client = None

def setup_qdrant():
    global qdrant_client
    if qdrant_client is None:
        qdrant_client = QdrantClient(path="./local_qdrant_db")

# Đổi sang sử dụng model Gemini
MODEL_NAME = "gemini-2.0-flash"

# Khởi tạo Gemini bằng ChatGoogleGenerativeAI
llm_generator = ChatGoogleGenerativeAI(
    model=MODEL_NAME,
    temperature=0.2,
    max_tokens=8192,
)

# Lịch sử hội thoại
chat_history = []

# Cache chống xử lý trùng (brain-level dedup — lớp bảo vệ thứ 2)
_query_cache: dict = {}   # key -> timestamp
_QUERY_CACHE_TTL = 25     # giây

# --- 2. ĐỊNH NGHĨA PYDANTIC & PROMPT ---
class RouteStep(BaseModel):
    step_order: int = Field(description="Thứ tự bước đi (1, 2, 3...)")
    service_name: str = Field(description="Tên dịch vụ/xét nghiệm")
    room: str = Field(description="Số phòng và tầng")
    reasoning: str = Field(description="Lý do xếp bước này ở vị trí hiện tại")

class ReceptionDecision(BaseModel):
    internal_assessment: str = Field(
        description="Đánh giá nội bộ: 'Bình thường', 'Cần hỏi thêm', hoặc 'Khẩn cấp'. Tuyệt đối không in cái này ra màn hình."
    )
    is_ready_for_route: bool = Field(
        description="Trả về False NGAY LẬP TỨC nếu trong phần 'ai_response' bạn có đặt ra BẤT KỲ CÂU HỎI NÀO. Chỉ trả về True khi hoàn toàn KHÔNG hỏi thêm."
    )
    ai_response: str = Field(
        description="CÂU TRẢ LỜI: Giao tiếp tự nhiên, thấu cảm. NẾU cần hỏi thêm, BẮT BUỘC ĐẶT CÂU HỎI TRỰC TIẾP (VD: 'Cô chú đau ở vùng nào ạ?')."
    )
    optimized_route: List[RouteStep] = Field(
        description="Danh sách lộ trình. BẮT BUỘC trả lời bằng tiếng Việt. Bước 1 LUÔN LUÔN là một Phòng Khám Lâm Sàng. Bắt buộc để trống nếu is_ready_for_route = False."
    )

GENERATE_PROMPT = """
Bạn là Lễ tân Ảo thông minh tại sảnh bệnh viện. Nhiệm vụ của bạn là lắng nghe, phân loại và điều hướng bệnh nhân linh hoạt nhất có thể.

[TÀI LIỆU QUY TRÌNH HÀNH CHÍNH]:
{context}

[DANH SÁCH DỊCH VỤ & THỜI GIAN]:
{live_services}

[HỒ SƠ BỆNH ÁN](nếu có):
{patient_record}

NGUYÊN TẮC 'ĐÃ HỎI THÌ KHÔNG VẠCH ĐƯỜNG' (ƯU TIÊN SỐ 1):
- Hai hành động "Hỏi thêm triệu chứng" và "Vạch lộ trình" là LOẠI TRỪ LẪN NHAU.
- VÀ NẾU BẠN ĐÃ QUYẾT ĐỊNH HỎI -> BẮT BUỘC ĐỂ TRỐNG DANH SÁCH LỘ TRÌNH.

NGUYÊN TẮC HOẠT ĐỘNG:
1. GIAO TIẾP: Xưng hô ĐÚNG (Dưới 40: Anh/Chị. Trên 40: Cô/Chú). KHÔNG LẶP CÂU HỎI cũ. CẤM XIN PHÉP trước khi vạch đường.
2. SÀNG LỌC: BÁO ĐỘNG ĐỎ nếu nghe "gãy", "chảy máu", "tai nạn", "bỏng", "ngất", "vết thương hở" -> Đi thẳng [Quầy Cấp Cứu Số 1]. DỪNG HỎI NGAY khi đoán được khoa khám (VD: Nội tiêu hóa).
3. HỒ SƠ Y KHOA: TUYỆT ĐỐI tin tưởng [HỒ SƠ BỆNH ÁN]. Không hỏi lại bệnh nền/dị ứng đã có.
4. LÂM SÀNG: Luôn xếp phòng bác sĩ làm Bước 1. TUYỆT ĐỐI KHÔNG chỉ định bệnh nhân đi làm xét nghiệm (Máu, X-Quang...) tự động.
5. CHỐNG ẢO GIÁC: Không bịa khoa/phòng ngoài [DANH SÁCH DỊCH VỤ]. Không chẩn đoán bệnh.
6. NGÔN NGỮ: BẮT BUỘC Tiếng Việt 100%.
"""

structured_generator = llm_generator.with_structured_output(ReceptionDecision, method="json_schema")


# --- 3. CÁC HÀM TRUY XUẤT DỮ LIỆU (ĐÃ SỬA LỖI CONNECTION LEAK) ---
def fetch_text_from_mysql(chunk_ids):
    if not chunk_ids: return []
    conn = db_pool.get_connection()
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        format_strings = ','.join(['%s'] * len(chunk_ids))
        query = f"""
            SELECT c.chunkID, c.chunkText, c.pageNumber, d.filename
            FROM documentChunks c
            JOIN documents d ON c.docID = d.docID
            WHERE c.chunkID IN ({format_strings})
        """
        cursor.execute(query, tuple(chunk_ids))
        return cursor.fetchall()
    except Exception as e:
        log_error(f"Lỗi truy vấn Qdrant text: {e}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def fetch_live_services_from_mysql():
    conn = db_pool.get_connection()
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT service_name, room, current_wait_time_mins, medical_rule FROM hospital_services")
        services = cursor.fetchall()
        services_text = ""
        for s in services:
            services_text += f"- Dịch vụ: {s['service_name']} | Phòng: {s['room']} | Chờ: {s['current_wait_time_mins']} phút | Quy tắc: {s['medical_rule']}\n"
        return services_text
    except Exception as e:
        log_error(f"Lỗi lấy dữ liệu live services: {e}")
        return ""
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def fetch_patient_record(patient_id: str) -> str:
    if not patient_id:
        return "Bệnh nhân mới (Khách vãng lai) - Chưa có hồ sơ trên hệ thống."
        
    conn = db_pool.get_connection()
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM patient_records WHERE patient_id = %s", (patient_id,))
        record = cursor.fetchone()
        
        if record:
            return f"""
            - Tên: {record['full_name']} ({record['age']} tuổi, {record['gender']})
            - Bệnh nền: {record['chronic_conditions']}
            - Dị ứng: {record['allergies']}
            - Tiền sử y khoa: {record['past_history']}
            """
        return "Không tìm thấy mã bệnh nhân. Áp dụng quy trình như Khách vãng lai."
    except Exception as e:
        log_error(f"Lỗi lấy hồ sơ bệnh án: {e}")
        return "Hệ thống SQL đang bận, tạm xử lý như Khách vãng lai."
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


_query_pending: dict = {}
_pending_lock = threading.Lock()

# ══════════════════════════════════════════════════════════════
# --- FAST PATH: Rule-based router (Không đổi) ---
# ══════════════════════════════════════════════════════════════
SYMPTOM_QUESTIONS: dict[str, str] = {
    "đau mắt":    "Dạ, để xác định đúng phòng khám, cô/chú cho biết: đau mắt trái hay phải? Có kèm mờ mắt, đỏ mắt không ạ?",
    "đau đầu":    "Dạ, cô/chú cho biết: đau ở vùng nào (thái dương, trán, gáy)? Có kèm buồn nôn không ạ?",
    "đau bụng":   "Dạ, cô/chú cho biết: đau ở vùng bụng nào (trên, dưới, trái, phải)? Đau từ bao lâu ạ?",
    "đau lưng":   "Dạ, cô/chú đau lưng trên hay dưới? Có lan xuống chân hay tê chân không ạ?",
    "đau ngực":   "Dạ, đau ngực cần đánh giá kỹ. Cô/chú đau ở bên nào? Có khó thở, vã mồ hôi không ạ?",
    "sốt":        "Dạ, cô/chú sốt từ bao lâu? Nhiệt độ cao nhất bao nhiêu độ? Có kèm ho không ạ?",
    "ho":         "Dạ, cô/chú ho khan hay có đờm? Ho từ bao lâu? Có kèm sốt không ạ?",
}

SUFFICIENT_SIGNALS = [
    "trái", "phải", "trên", "dưới", "giữa", "ngày", "tuần", "tháng", 
    "nhói", "âm ỉ", "tiểu đường", "huyết áp", "tim mạch"
]

def quick_route(raw_query: str) -> str | None:
    if len(chat_history) > 0:
        return None
    q = raw_query.lower().strip()
    if any(sig in q for sig in SUFFICIENT_SIGNALS):
        return None
    for symptom, answer in SYMPTOM_QUESTIONS.items():
        if symptom in q: return answer
    return None


# --- 4. LUỒNG XỬ LÝ CHÍNH (ĐÃ SỬA DEADLOCK & ROLE ERROR) ---
def process_patient_query(raw_query: str, patient_record_text: str = "") -> str:
    global chat_history
    cache_key = re.sub(r'[^\w]', '', raw_query).strip().lower()
    now = time.time()
    
    # ── ĐỒNG BỘ CHỐNG SPAM / DEADLOCK (PHẦN 1) ──
    with _pending_lock:
        if cache_key and cache_key in _query_cache:
            elapsed = now - _query_cache[cache_key]
            if elapsed < _QUERY_CACHE_TTL:
                event, result_holder = _query_pending.get(cache_key, (None, None))
                if event:
                    print(f"[XỬ LÝ TRÙNG LẶP] Đang chờ luồng 1 ({elapsed:.1f}s)...")
                    # Rời khỏi lock, chờ thread kia xong
                    _pending_lock.release()
                    event.wait(timeout=355)
                    _pending_lock.acquire() 
                    return result_holder[0] if result_holder else ""
                else:
                    return ""
                    
        # Lần gọi đầu tiên — Đăng ký giữ chỗ
        _query_cache[cache_key] = now
        event = threading.Event()
        result_holder: list = []
        _query_pending[cache_key] = (event, result_holder)

    
    # ── LUỒNG XỬ LÝ CỐT LÕI (Bọc trong TRY/FINALLY Toàn cục) ──
    # Giá trị mặc định nếu xảy ra lỗi
    tts_response = "Dạ, hệ thống đang bận hoặc đường truyền lỗi. Cô/chú vui lòng qua Quầy Hướng dẫn ạ."
    display_response = tts_response
    
    try:
        cleaned_query = raw_query.lower()
        route_text = ""
        pending_whisper_text = None

        # [1] CẤP CỨU NGOẠI KHOA
        emergency_keywords = ["gãy", "chảy máu", "tai nạn", "bỏng", "ngất", "chó cắn", "vết thương hở", "khó thở", "đột quỵ"]
        if any(keyword in cleaned_query for keyword in emergency_keywords):
            tts_response = " **CẢNH BÁO KHẨN CẤP:** Dạ tình trạng rất nguy hiểm. Xin vui lòng BỎ QUA mọi thủ tục, di chuyển thẳng ra [QUẦY CẤP CỨU SỐ 1] ngay lập tức!"
            display_response = tts_response
            print(f"[EMERGENCY] Kích hoạt khẩn cấp cho: '{raw_query[:40]}'")
            return tts_response

        # [2] CẤP CỨU BỆNH NỀN
        HIGH_RISK_RULES = [
            {"conditions": ["tim", "huyết áp", "mạch vành", "nhồi máu"], "triggers": ["mệt", "chóng mặt", "đau vai", "đau lưng"], "check_question": "Dạ, hệ thống chú ý mình có tiền sử tim mạch/huyết áp. Cô/chú có đang cảm thấy đau thắt ngực hay vã mồ hôi lạnh không ạ?", "danger_answers": ["có", "thắt", "vã", "mồ hôi"]},
            {"conditions": ["tiểu đường"], "triggers": ["mệt", "chóng mặt", "đói"], "check_question": "Dạ, hệ thống thấy mình có bệnh nền tiểu đường. Hiện tại cô/chú có bị run rẩy tay chân hay vã mồ hôi không ạ?", "danger_answers": ["có", "run", "vã"]},
        ]

        active_rule = None
        if len(chat_history) > 0 and isinstance(chat_history[-1], AIMessage):
            last_bot_msg = chat_history[-1].content
            for rule in HIGH_RISK_RULES:
                if rule["check_question"] in last_bot_msg:
                    active_rule = rule; break

        if active_rule:
            if any(word in cleaned_query for word in active_rule["danger_answers"]):
                tts_response = " **CẢNH BÁO KHẨN CẤP:** Dấu hiệu biến chứng bệnh nền! Xin vui lòng di chuyển thẳng ra [QUẦY CẤP CỨU SỐ 1] ngay lập tức!"
                display_response = tts_response
                return tts_response
            else:
                # Thay vì dùng SystemMessage, đưa vào chuỗi để nối với truy vấn
                pending_whisper_text = "[HỆ THỐNG]: Rủi ro bệnh nền đã được loại trừ. Hãy hỏi tiếp về triệu chứng ban đầu (thời gian, vị trí, mức độ). TUYỆT ĐỐI CHƯA ĐƯỢC vạch lộ trình."
        elif not active_rule:
            record_lower = patient_record_text.lower()
            for rule in HIGH_RISK_RULES:
                if any(c in record_lower for c in rule["conditions"]) and any(t in cleaned_query for t in rule["triggers"]):
                    tts_response = rule["check_question"]
                    display_response = tts_response
                    return tts_response

        # [3] FAST PATH RULE-BASED
        if not pending_whisper_text:
            quick_answer = quick_route(raw_query)
            if quick_answer:
                tts_response = quick_answer
                display_response = tts_response
                print(f"[FAST PATH] '{raw_query[:40]}' → pre-coded answer")
                return tts_response

        # [4] VECTOR SEARCH & RAG
        setup_qdrant()
        global qdrant_client
            
        query_vector = embed_model.encode(raw_query).tolist()
        search_results = qdrant_client.query_points(collection_name=COLLECTION_NAME, query=query_vector, limit=3).points
        chunk_ids = [hit.id for hit in search_results] if search_results else []
        
        mysql_docs = fetch_text_from_mysql(chunk_ids)
        filtered_context = ""
        if mysql_docs:
            pairs = [[raw_query, doc['chunkText']] for doc in mysql_docs]
            scores = rerank_model.predict(pairs)
            scored_docs = sorted(zip(mysql_docs, scores), key=lambda x: x[1], reverse=True)
            for doc, score in scored_docs:
                if score >= RERANK_THRESHOLD:
                    filtered_context += f"- [Nguồn: {doc['filename']} - Trang {doc['pageNumber']}]: {doc['chunkText']}\n"
        
        if len(filtered_context) > 3000:
            filtered_context = filtered_context[:3000] + "\n...(đã cắt bớt)"
        
        live_services = fetch_live_services_from_mysql()
        if len(live_services) > 2000:
            live_services = live_services[:2000] + "\n...(đã cắt bớt)"
        
        messages = [
            SystemMessage(content=GENERATE_PROMPT.format(
                context=filtered_context,
                live_services=live_services,
                patient_record=patient_record_text
            )),
        ]
        
        recent_history = chat_history[-4:] if len(chat_history) > 4 else chat_history
        messages.extend(recent_history)
        
        # [Sửa lỗi LangChain]: Nối lệnh ẩn trực tiếp vào HumanMessage thay vì dùng SystemMessage đặt sau cùng
        final_query = raw_query
        if pending_whisper_text:
            final_query += f"\n\n{pending_whisper_text}"
        messages.append(HumanMessage(content=final_query))
        
        decision: ReceptionDecision = structured_generator.invoke(messages)
        ai_text_lower = decision.ai_response.lower()

        WRONG_ROLE_SIGNALS = ["xin chào bác sĩ", "bệnh nhân của tôi", "tôi có triệu chứng", "bạn cho tôi biết"]
        if any(sig in ai_text_lower for sig in WRONG_ROLE_SIGNALS):
            log_error(f"[ROLE GUARD] Nhập vai sai: '{decision.ai_response[:80]}'")
            decision.ai_response = "Dạ, để hỗ trợ tốt hơn, cô/chú vui lòng cho biết triệu chứng đau ở vị trí nào và bắt đầu từ bao giờ ạ?"
            decision.is_ready_for_route = False
            decision.optimized_route = []

        question_signals = ["?", "không ạ", "hỏi thêm", "cho biết", "mô tả", "chi tiết hơn"]
        if any(signal in ai_text_lower for signal in question_signals):
            decision.is_ready_for_route = False
            decision.optimized_route = []

        tts_response = decision.ai_response

        if len(decision.optimized_route) > 0:
            if "?" in tts_response:
                tts_response = tts_response.split("?")[0] + "."
            route_text += "\n\n **LỘ TRÌNH KHÁM TỐI ƯU:**"
            for step in decision.optimized_route:
                route_text += f"\n{step.step_order}. **{step.service_name}** ({step.room})"
                route_text += f"\n   ↓ *Lý do:* {step.reasoning}"

        display_response = tts_response + route_text

    except Exception as e:
        log_error(f"Lỗi xử lý LLM/Qdrant: {e}")
        # Mặc định tts_response và display_response đã là fallback error text
    
    finally:
        # ── LƯU LẠI LỊCH SỬ & GIẢI PHÓNG LUỒNG CHỜ (CHẠY TRONG MỌI TÌNH HUỐNG) ──
        log_exchange(raw_query, display_response)
        chat_history.append(HumanMessage(content=raw_query))
        chat_history.append(AIMessage(content=tts_response))
        
        # Tối ưu RAM: Giữ tối đa 20 lượt hội thoại
        if len(chat_history) > 20:
            chat_history = chat_history[-20:]

        # Đánh thức Thread số 2 (nếu có)
        try:
            with _pending_lock:
                entry = _query_pending.pop(cache_key, None)
                if entry:
                    ev, holder = entry
                    holder.append(tts_response)
                    ev.set()  # UNLOCK!
        except Exception as e:
            log_error(f"Lỗi giải phóng lock: {e}")

        return tts_response

def reset_brain_memory():
    global chat_history
    chat_history.clear()
    print(" [HỆ THỐNG]: Đã quét sạch bộ nhớ ngắn hạn của AI!")
    
if __name__ == "__main__":
    print("\n=== HỆ THỐNG ĐIỀU PHỐI BỆNH NHÂN SẴN SÀNG ===")
    last_input_time = time.time()
    timeout_duration = 60 * 60
    
    current_patient_id = input("Mô phỏng Quét mã bệnh nhân (Nhập BN-001... hoặc nhấn Enter): ").strip()
    patient_record_text = fetch_patient_record(current_patient_id)
    
    print("\n[ĐĐ TẢI HỒ SƠ BỆNH ÁN]")
    print(patient_record_text)
    
    while True:
        try:
            current_time = time.time()
            if current_time - last_input_time > timeout_duration:
                chat_history.clear()
                print(f"\n Cuộc trò chuyện đã hết hạn ({timeout_duration // 60} phút). Đã làm mới lịch sử.")
                last_input_time = current_time 
            
            user_input = input("Người bệnh hỏi: ")
            last_input_time = time.time()
            
            if user_input.lower() in ['exit', 'quit']: break
            if user_input.lower() in ['refresh', 'update']:
                chat_history.clear()
                print("Đã làm mới lịch sử hội thoại.")
                continue
            
            if user_input.lower().startswith('bn-'):
                current_patient_id = user_input.strip().upper()
                patient_record_text = fetch_patient_record(current_patient_id)
                chat_history.clear()
                
                print("\n" + "*"*50)
                print("[ĐÃ TẢI HỒ SƠ BỆNH ÁN MỚI]")
                print(patient_record_text)
                print("*"*50 + "\n")
                print(f"Dạ, hệ thống đã nhận hồ sơ của {current_patient_id}. Cô chú cần khám gì ạ?")
                continue
            
            if user_input.strip(): 
                process_patient_query(user_input, patient_record_text)
                
        except KeyboardInterrupt: 
            break