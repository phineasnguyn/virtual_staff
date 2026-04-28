import os
import re
import threading

# ── LOGGER TẬP TRUNG (chống chèo terminal) ───────────────────
_log_lock = threading.Lock()
SEP = "─" * 60

def log_exchange(patient_text: str, bot_text: str) -> None:
    """In một cặp hỏi-đáp hoàn chỉnh, thread-safe."""
    with _log_lock:
        print(f"\n{SEP}")
        print(f" BENH NHAN : {patient_text}")
        print(SEP)
        print(f" LE TAN    : {bot_text}")
        print(f"{SEP}\n")

def log_error(msg: str) -> None:
    with _log_lock:
        print(f"[LOI] {msg}")
# ─────────────────────────────────────────────────────────────
import random
import time
import mysql.connector
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder
from langchain_community.llms import Ollama
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Literal, List
from mysql.connector import pooling


# --- 1. CẤU HÌNH HỆ THỐNG ---
BASE_DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': ''
}

# Khởi tạo 3 Connection Pools độc lập cho 3 Database
rag_pool = pooling.MySQLConnectionPool(
    pool_name="rag_pool",
    pool_size=5,
    database="hospital_rag_db",
    **BASE_DB_CONFIG
)

service_pool = pooling.MySQLConnectionPool(
    pool_name="service_pool",
    pool_size=5,
    database="hospital_services_db",
    **BASE_DB_CONFIG
)

patient_pool = pooling.MySQLConnectionPool(
    pool_name="patient_pool",
    pool_size=5,
    database="patient_records_db",
    **BASE_DB_CONFIG
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

MODEL_NAME = "gemma3:4b"  # 3.3GB VRAM — Tốt hơn 3b, vừa khít bộ nhớ 4GB

ollama_rewriter = Ollama(model=MODEL_NAME, temperature=0.1)
ollama_generator = ChatOllama(
    model=MODEL_NAME,
    temperature=0.2,
    num_predict=600,      # [GUARD] ngăn sinh vòng lặp dài
    repeat_penalty=1.15,  # [GUARD] phạt lặp từ
)

# Lịch sử hội thoại
chat_history = []
_history_lock = threading.Lock()  # [THREAD-SAFE] bảo vệ chat_history khỏi data race

# Cache chống xử lý trùng (brain-level dedup — lớp bảo vệ thứ 2)
_query_cache: dict = {}   # key -> timestamp
_QUERY_CACHE_TTL = 25     # giây

# --- 2. ĐỊNH NGHĨA PROMPT VÀ PYDANTIC (ĐIỀU HƯỚNG TỐI ƯU) ---
REWRITE_PROMPT = PromptTemplate(
    input_variables=["raw_query"],
    template="""Bạn là một Lễ tân bệnh viện. Hãy viết lại câu hỏi của người bệnh thành câu truy vấn ngắn. 
    Chỉ giữ lại các từ khóa về: thủ tục, bảo hiểm, giá tiền, phòng ban, hoặc mô tả triệu chứng.
    Câu của người bệnh: {raw_query}
    Câu truy vấn chuẩn:"""
)

# Cấu trúc từng bước di chuyển
class RouteStep(BaseModel):
    step_order: int = Field(description="Thứ tự bước đi (1, 2, 3...)")
    service_id: str = Field(description="Mã dịch vụ (VD: CLINIC_GASTRO, TEST_BLOOD)")
    service_name: str = Field(description="Tên dịch vụ/xét nghiệm")
    room: str = Field(description="Số phòng và tầng")
    reasoning: str = Field(description="Lý do xếp bước này ở vị trí hiện tại")

class ReceptionDecision(BaseModel):
    internal_assessment: str = Field(
        description="Đánh giá nội bộ: 'Bình thường', 'Cần hỏi thêm', hoặc 'Khẩn cấp'. (Ví dụ: 'Triệu chứng quá chung chung, cần hỏi thêm' hoặc 'Dấu hiệu nôn ra máu là cấp cứu, phải báo ngay' hoặc 'Triệu chứng rõ ràng, có thể vạch lộ trình'). Tuyệt đối không in cái này ra màn hình."
    )
    is_ready_for_route: bool = Field(
        description="Trả về False NGAY LẬP TỨC nếu trong phần 'ai_response' bạn có đặt ra BẤT KỲ CÂU HỎI NÀO cho bệnh nhân. Chỉ trả về True khi bạn hoàn toàn KHÔNG hỏi thêm gì nữa."
    )
    ai_response: str = Field(
        description="CÂU TRẢ LỜI: Giao tiếp tự nhiên, thấu cảm. NẾU thiếu dữ kiện và cần hỏi thêm, bạn BẮT BUỘC PHẢI ĐẶT CÂU HỎI TRỰC TIẾP, RÕ RÀNG (VD: 'Cô chú đau ở vùng nào ạ?', 'Đau từ bao giờ ạ?'). TUYỆT ĐỐI KHÔNG ĐƯỢC trả lời chung chung kiểu 'Tôi cần hỏi thêm một vài thông tin, có thể cho tôi biết thêm được không?'"
    )
    optimized_route: List[RouteStep] = Field(
        description="Danh sách lộ trình. BẮT BUỘC trả lời bằng tiếng Việt. Bước 1 LUÔN LUÔN là một Phòng Khám Lâm Sàng (VD: Khám Nội, Khám Ngoại, Khám Hô hấp) để gặp bác sĩ. TUYỆT ĐỐI KHÔNG xếp bệnh nhân đi Xét nghiệm, Chụp chiếu trước khi gặp bác sĩ. Bắt buộc để trống nếu is_ready_for_route = False."
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
- Dù hồ sơ bệnh án có rõ ràng đến đâu, nếu triệu chứng người bệnh khai hiện chưa rõ vị trí/mức độ, bạn BẮT BUỘC phải hỏi.
- VÀ NẾU BẠN ĐÃ QUYẾT ĐỊNH HỎI -> BẮT BUỘC ĐỂ TRỐNG DANH SÁCH LỘ TRÌNH. Tuyệt đối không được "vừa hỏi vừa chỉ đường".

NGUYÊN TẮC HOẠT ĐỘNG VÀ VẠCH LỘ TRÌNH TOÀN DIỆN:

1. GIAO TIẾP & CÁ NHÂN HÓA (Hồ sơ bệnh án):
   - BẮT BUỘC chọn ĐÚNG 1 từ xưng hô duy nhất dựa vào tuổi và giới tính trong hồ sơ (Dưới 40 tuổi: dùng "Anh" hoặc "Chị". Trên 40 tuổi: dùng "Cô" hoặc "Chú").
   - CHỐNG LẶP CÂU HỎI: BẮT BUỘC đọc kỹ lịch sử hội thoại. Tuyệt đối KHÔNG ĐƯỢC hỏi lại những triệu chứng đã hỏi ở lượt trước.
   - CẤM XIN PHÉP (QUAN TRỌNG): Khi đã thu thập đủ dữ kiện để vạch lộ trình, TUYỆT ĐỐI KHÔNG hỏi những câu như "Cô/chú có đồng ý không?", "Có muốn tôi hướng dẫn không?". BẮT BUỘC phải chốt câu nói bằng một câu khẳng định (VD: "Mời cô chú đi theo lộ trình sau:") và vạch lộ trình NGAY LẬP TỨC.
   
2. ĐÁNH GIÁ SÀNG LỌC (Triage & Cấp Cứu):
   - BÁO ĐỘNG ĐỎ (CẤP CỨU NGOẠI KHOA/NỘI KHOA): NẾU bệnh nhân nhắc đến BẤT KỲ từ khóa nào sau đây: "gãy", "chảy máu", "tai nạn", "bỏng", "ngất", "chó cắn", "vết thương hở" -> BẮT BUỘC ĐÁNH GIÁ ĐÂY LÀ CA CẤP CỨU. Lập tức hướng dẫn đi thẳng ra [Quầy Cấp Cứu Số 1]. TUYỆT ĐỐI KHÔNG được hỏi thêm bất cứ câu nào.
   - MỤC TIÊU TỐI THƯỢNG LÀ PHÂN LUỒNG NHANH CHÓNG: Bạn là Lễ tân, KHÔNG PHẢI BÁC SĨ. Bạn CHỈ hỏi thêm NẾU thông tin hiện tại chưa đủ để xác định bệnh nhân cần đi khám chuyên khoa nào.
     + Ví dụ 1: "Tôi bị đau bụng" -> Quá chung chung, cần hỏi thêm vị trí hoặc biểu hiện đi kèm để phân biệt Nội hay Ngoại khoa.
     + Ví dụ 2: "Tôi bị đau bụng kèm táo bón" -> Đã ĐỦ dữ kiện để xếp vào Nội Tiêu Hóa. Bạn phải VẠCH LỘ TRÌNH NGAY, TUYỆT ĐỐI KHÔNG hỏi thêm!
     + LƯU Ý 1: Nếu thực sự phải hỏi, HÃY ĐẶT ĐÚNG 1 CÂU HỎI MỞ DUY NHẤT để lấy thông tin (Ví dụ: "Dạ, cô/chú đau ở vùng nào của bụng ạ?").
     + LƯU Ý 2: KHÔNG SỬ DỤNG câu hỏi dạng Có/Không (Ví dụ: Đừng hỏi "Có bị nôn không?").
     + LƯU Ý 3: Bỏ qua ngay các câu chào hỏi dài dòng kiểu "Tôi rất tiếc khi nghe...", hãy đi thẳng vào câu hỏi luôn.
   - Bệnh cũ tái phát: Nếu triệu chứng trùng với hồ sơ bệnh án, hãy hỏi thêm 1-2 câu để rõ vị trí và thời gian đau trước khi vạch lộ trình.
   - CẦU DAO DỪNG HỎI (QUAN TRỌNG NHẤT): 
     + NGAY KHI bạn có thể suy luận được một Khoa Khám Bệnh phù hợp (VD: Nội Tiêu Hóa, Tai Mũi Họng, Da liễu, v.v.), bạn BẮT BUỘC PHẢI DỪNG HỎI NGAY LẬP TỨC.
     + Lập tức tạo `optimized_route` và hướng dẫn bệnh nhân đi khám. Không được cố gắng thu thập thêm triệu chứng như một bác sĩ.

     
3. ĐỐI CHIẾU AN TOÀN Y KHOA (PHẢI ĐỌC HỒ SƠ ĐẦU TIÊN):
   - LỆNH BẮT BUỘC: [HỒ SƠ BỆNH ÁN] chứa ĐẦY ĐỦ VÀ CHÍNH XÁC thông tin về bệnh nền và dị ứng của bệnh nhân. Bạn BẮT BUỘC coi đây là sự thật hiển nhiên.
   - KHÔNG ĐƯỢC PHÉP HỎI LẠI: Vì hồ sơ đã ghi rõ, bạn TUYỆT ĐỐI KHÔNG ĐƯỢC hỏi bệnh nhân bất kỳ câu nào liên quan đến bệnh nền, dị ứng hay tiểu sử bệnh lý. Bắt buộc bỏ qua bước xác minh bệnh nền.
   - LOẠI TRỪ LOGIC: Loại bỏ các chẩn đoán phi lý (VD: Đã 'cắt ruột thừa' thì không khám viêm ruột thừa).

4. TRUY VẾT & ĐIỀU HƯỚNG LÂM SÀNG (Routing to Doctor First):
   - Ưu Tiên Khám Lâm Sàng: Nhiệm vụ tối thượng của bạn là phân luồng bệnh nhân đến đúng PHÒNG KHÁM CHUYÊN KHOA (VD: Khám Nội Tiêu Hóa, Khám Hô hấp, Khám Da Liễu). LUÔN LUÔN xếp phòng khám bác sĩ làm Bước 1.
   - Cấm Vượt Quyền: TUYỆT ĐỐI KHÔNG chỉ định bệnh nhân đi làm xét nghiệm (Máu, Nước tiểu, X-Quang, Siêu âm, Nội soi) như một bước đi độc lập trước khi gặp bác sĩ.
   - Trợ lý cho Bác sĩ: Trong phần 'reasoning' (Lý do) của bước Khám lâm sàng, bạn HÃY đọc 'medical_rule' và ghi chú thêm: "Gợi ý cho Bác sĩ: Cân nhắc chỉ định thêm Siêu âm/Xét nghiệm máu...".

5. KỶ LUẬT DỮ LIỆU & CHỐNG ẢO GIÁC (Anti-Hallucination):
   - Ranh giới SQL: TUYỆT ĐỐI KHÔNG tự bịa ra tên khoa hoặc số phòng không có trong [DANH SÁCH DỊCH VỤ].
   - Vượt khả năng: Nếu triệu chứng thuộc chuyên khoa chưa có dữ liệu, mời ra Quầy Hướng dẫn.
   - Giới hạn Y khoa: TUYỆT ĐỐI KHÔNG chẩn đoán bệnh, không kê đơn thuốc, không ấn định chỉ định xét nghiệm. Bạn chỉ làm nhiệm vụ "Lễ tân điều phối chuyên khoa".

6. RÀNG BUỘC NGÔN NGỮ (LANGUAGE CONSTRAINT):
   - TOÀN BỘ suy luận, câu trả lời và lý do vạch lộ trình BẮT BUỘC PHẢI ĐƯỢC VIẾT BẰNG TIẾNG VIỆT 100%. 
   - Tuyệt đối không sử dụng tiếng Anh trong bất kỳ trường dữ liệu nào.
"""

structured_generator = ollama_generator.with_structured_output(ReceptionDecision)

# --- 3. CÁC HÀM TRUY XUẤT DỮ LIỆU ---
def fetch_text_from_mysql(chunk_ids):
    if not chunk_ids: return []
    conn = rag_pool.get_connection()
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
        results = cursor.fetchall()
        return results
    finally:
        cursor.close()
        conn.close()

# Hàm mới: Lấy thông tin dịch vụ và thời gian chờ Real-time
def fetch_live_services_from_mysql():
    conn = service_pool.get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT service_id, service_name, room, current_wait_time_mins, medical_rule, map_image_url FROM hospital_services")
        services = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    # Định dạng thành chuỗi văn bản để nhét vào Prompt
    services_text = ""
    map_urls = {}
    for s in services:
        services_text += f"- Mã: {s['service_id']} | Dịch vụ: {s['service_name']} | Phòng: {s['room']} | Chờ: {s['current_wait_time_mins']} phút | Quy tắc: {s['medical_rule']}\n"
        map_urls[s['service_id']] = s.get('map_image_url', '')
    return services_text, map_urls

def register_patient_to_queue(patient_id: str, service_id: str):
    """Đẩy bệnh nhân vào bảng patient_queue của dịch vụ"""
    if not patient_id:
        patient_id = "KHACH_MOI"
    conn = service_pool.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO patient_queue (patient_id, service_id, status) VALUES (%s, %s, %s)",
            (patient_id, service_id, 'WAITING')
        )
        conn.commit()
        print(f"\n[HỆ THỐNG] Đã check-in thành công bệnh nhân {patient_id} vào hàng đợi dịch vụ {service_id}")
    except Exception as e:
        print(f"[LỖI CHECK-IN] {e}")
    finally:
        cursor.close()
        conn.close()

# Hàm truy xuất hồ sơ bệnh án từ SQL dựa trên patient_id (nếu có)
def fetch_patient_record(patient_id: str) -> str:
    """Truy xuất hồ sơ bệnh án từ SQL"""
    if not patient_id:
        return "Bệnh nhân mới (Khách vãng lai) - Chưa có hồ sơ trên hệ thống."

    conn = patient_pool.get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM patient_records WHERE patient_id = %s", (patient_id,))
        record = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if record:
        return f"""
        - Tên: {record['full_name']} ({record['age']} tuổi, {record['gender']})
        - Bệnh nền: {record['chronic_conditions']}
        - Dị ứng: {record['allergies']}
        - Tiền sử y khoa: {record['past_history']}
        """
    return "Không tìm thấy mã bệnh nhân. Áp dụng quy trình như Khách vãng lai."

# _query_pending: key -> (threading.Event, list[str])  — cho lần gọi thứ 2 chờ kết quả
_query_pending: dict = {}
_pending_lock = threading.Lock()

# ══════════════════════════════════════════════════════════════
# --- FAST PATH: Rule-based router (không cần LLM) ---
# ══════════════════════════════════════════════════════════════

# Câu hỏi pre-coded khi bệnh nhân chỉ đưa ra 1 triệu chứng đơn lẻ, thiếu context
SYMPTOM_QUESTIONS: dict[str, str] = {
    "đau mắt":    "Dạ, để xác định đúng phòng khám, cô/chú cho biết: đau mắt trái hay mắt phải? Đau từ bao lâu? Có kèm mờ mắt, đỏ mắt hoặc chảy nước mắt không ạ?",
    "mờ mắt":     "Dạ, cô/chú bị mờ mắt trái hay phải? Mờ đột ngột hay từ từ? Từ bao lâu rồi ạ?",
    "đau đầu":    "Dạ, cô/chú cho biết: đau ở vùng nào (thái dương, trán, gáy, sau gáy)? Đau từ bao lâu? Có kèm sốt, buồn nôn, nôn không ạ?",
    "đau bụng":   "Dạ, cô/chú cho biết: đau ở vùng bụng nào (trên, dưới, trái, phải)? Đau liên tục hay từng cơn? Từ bao lâu ạ?",
    "đau lưng":   "Dạ, cô/chú cho biết: đau lưng trên hay lưng dưới? Một bên hay hai bên? Có lan xuống chân hay tê chân không ạ?",
    "đau ngực":   "Dạ, đau ngực cần đánh giá kỹ. Cô/chú đau ở bên nào? Đau từ bao lâu? Có khó thở, vã mồ hôi hoặc tê tay trái không ạ?",
    "đau vai":    "Dạ, cô/chú đau vai trái hay phải? Đau từ bao lâu? Có hạn chế cử động tay không ạ?",
    "đau cổ":     "Dạ, cô/chú đau cổ trước hay sau? Đau từ bao lâu? Có tê tay, cứng cổ buổi sáng không ạ?",
    "đau tay":    "Dạ, cô/chú đau tay trái hay phải? Đau ở đâu (cổ tay, khuỷu, cánh tay)? Có tê bì không ạ?",
    "đau chân":   "Dạ, cô/chú đau chân trái hay phải? Đau ở đâu (đùi, gối, bắp chân, bàn chân)? Từ bao lâu ạ?",
    "đau khớp":   "Dạ, cô/chú đau ở khớp nào? Khớp có sưng, nóng đỏ không? Đau từ bao lâu ạ?",
    "đau tai":    "Dạ, cô/chú đau tai trái hay phải? Có ù tai, chảy dịch hoặc nghe kém không? Từ bao lâu ạ?",
    "đau họng":   "Dạ, cô/chú đau họng từ bao lâu? Có sốt, ho hoặc khó nuốt không ạ?",
    "đau răng":   "Dạ, cô/chú đau răng nào (hàm trên/dưới, trái/phải)? Đau liên tục hay khi nhai? Có sưng lợi không ạ?",
    "sốt":        "Dạ, cô/chú sốt từ bao lâu? Nhiệt độ cao nhất bao nhiêu độ? Có kèm ho, đau họng, phát ban hoặc rét run không ạ?",
    "ho":         "Dạ, cô/chú ho khan hay có đờm? Ho từ bao lâu? Có kèm sốt, khó thở hoặc đau ngực không ạ?",
    "khó thở":    "Dạ, cô/chú khó thở từ bao lâu? Khó thở khi nằm hay cả khi ngồi? Có đau ngực hoặc tiền sử bệnh tim/phổi không ạ?",
    "chóng mặt":  "Dạ, cô/chú chóng mặt từ bao lâu? Chóng mặt khi đứng lên hay liên tục? Có buồn nôn, ù tai hoặc ngã không ạ?",
    "buồn nôn":   "Dạ, cô/chú buồn nôn từ bao lâu? Có nôn không? Kèm đau bụng hay sau khi ăn không ạ?",
    "nôn":        "Dạ, cô/chú nôn từ bao lâu? Nôn mấy lần? Có máu trong dịch nôn hoặc đau bụng không ạ?",
    "tiêu chảy":  "Dạ, cô/chú tiêu chảy từ bao lâu? Bao nhiêu lần/ngày? Có máu trong phân, sốt hoặc mất nước không ạ?",
    "táo bón":    "Dạ, cô/chú táo bón từ bao lâu? Có đau bụng, chướng bụng hoặc máu trong phân không ạ?",
    "phát ban":   "Dạ, ban xuất hiện ở vùng nào? Từ bao lâu? Có ngứa, sốt hoặc tiếp xúc với dị nguyên nào không ạ?",
    "ngứa":       "Dạ, cô/chú ngứa ở vùng nào? Từ bao lâu? Có nổi mẩn, phát ban hoặc tiếp xúc với hóa chất/thức ăn lạ không ạ?",
    "mất ngủ":    "Dạ, cô/chú mất ngủ từ bao lâu? Khó vào giấc hay hay thức giữa đêm? Có lo âu, căng thẳng hoặc đau không ạ?",
    "đi tiểu":    "Dạ, cô/chú gặp vấn đề gì về tiểu tiện (tiểu rắt, tiểu buốt, tiểu máu, tiểu nhiều)? Từ bao lâu ạ?",
    "tiểu buốt":  "Dạ, cô/chú tiểu buốt từ bao lâu? Có tiểu rắt, tiểu máu hoặc sốt không ạ?",
    "đau bẹn":    "Dạ, cô/chú đau ở bẹn trái hay phải? Có thấy khối phồng ở bẹn không? Đau từ bao lâu ạ?",
}

# Tín hiệu cho thấy đã đủ thông tin để route (không cần hỏi thêm)
SUFFICIENT_SIGNALS = [
    # Vị trí/bên cụ thể
    "trái", "phải", "trên", "dưới", "giữa", "trước", "sau",
    "bụng dưới", "bụng trên", "lưng dưới", "lưng trên",
    # Thời gian
    "ngày", "tuần", "tháng", "giờ", "phút",
    "hôm nay", "hôm qua", "sáng nay", "tối qua", "vừa",
    "lâu rồi", "từ lâu", "mấy ngày",
    # Tính chất đau
    "nhói", "âm ỉ", "bỏng", "tê", "sưng", "đỏ", "nóng",
    "dữ dội", "nặng", "nhẹ", "liên tục", "từng cơn",
    # Cấp cứu
    "ngã", "tai nạn", "va chạm", "không chịu được", "rất nặng",
    # Bệnh cụ thể
    "tiểu đường", "huyết áp", "tim mạch", "thận", "gan",
    "mổ", "phẫu thuật", "đã từng", "tiền sử",
]

def quick_route(raw_query: str) -> str | None:
    """
    Fast Path: Trả lời ngay không cần LLM.
    - None  → cần gọi LLM (đủ context hoặc query lạ)
    - str   → câu hỏi pre-coded (thiếu context)
    """
    # Không áp dụng Fast Path nếu đang trong giữa cuộc hội thoại (đã có HumanMessage trước đó)
    with _history_lock:
        human_msgs_count = sum(1 for m in chat_history if isinstance(m, HumanMessage))
    if human_msgs_count > 0:
        return None

    q = raw_query.lower().strip()

    # Nếu có đủ context signals → để LLM route (không hỏi thêm)
    if any(sig in q for sig in SUFFICIENT_SIGNALS):
        return None

    # Nếu khớp triệu chứng đơn lẻ → trả lời pre-coded
    for symptom, answer in SYMPTOM_QUESTIONS.items():
        if symptom in q:
            return answer

    # Không khớp gì → để LLM xử lý (câu hỏi ngoài phạm vi, v.v.)
    return None


# --- 4. LUỒNG XỬ LÝ CHÍNH ---
def _evict_expired_cache() -> None:
    """Dọn sạch các key đã hết TTL để tránh tích lũy vô hạn."""
    now = time.time()
    with _pending_lock:
        expired = [k for k, ts in _query_cache.items() if now - ts > _QUERY_CACHE_TTL]
        for k in expired:
            _query_cache.pop(k, None)
            _query_pending.pop(k, None)


def process_patient_query(raw_query: str, patient_record_text: str = "", patient_id: str = "") -> str:
    cache_key = re.sub(r'[^\w]', '', raw_query).strip().lower()
    now = time.time()

    # [THREAD-SAFE] Toàn bộ logic kiểm tra / đăng ký cache trong 1 khối lock duy nhất
    event = None
    result_holder = None
    should_skip = False

    _evict_expired_cache()  # dọn key cũ mỗi lần gọi

    with _pending_lock:
        if cache_key and cache_key in _query_cache:
            elapsed = now - _query_cache[cache_key]
            if elapsed < _QUERY_CACHE_TTL:
                pending = _query_pending.get(cache_key)
                if pending:
                    event, result_holder = pending  # lần gọi thứ 2 → chờ
                else:
                    should_skip = True              # đã xử lý xong → bỏ qua im lặng
        if not event and not should_skip:
            # Lần gọi đầu tiên — đăng ký event
            _query_cache[cache_key] = now
            event_new = threading.Event()
            result_holder_new: list = []
            _query_pending[cache_key] = (event_new, result_holder_new)

    if event and result_holder is not None:
        elapsed = now - _query_cache.get(cache_key, now)
        print(f"[XỬ LÝ TRÙNG LẶP] Đang chờ kết quả từ luồng 1 ({elapsed:.1f}s): '{raw_query[:50]}'")
        event.wait(timeout=355)
        return result_holder[0] if result_holder else ""
    if should_skip:
        return ""

    # Dùng event/holder đã đăng ký trong khối lock phía trên
    event = event_new
    result_holder = result_holder_new
    
    cleaned_query = raw_query.lower()
    # [1] BỘ ĐÁNH CHẶN CẤP CỨU TOÀN DIỆN (UNIVERSAL INTERCEPTOR)
    # Đặt trước Fast Path để đảm bảo các ca cấp cứu được ưu tiên tuyệt đối
    emergency_keywords = [
        "gãy", "chảy máu", "tai nạn", "bỏng", "ngất", "chó cắn", "vết thương hở", 
        "khó thở", "tức ngực", "đau ngực", "đau tim", "đột quỵ", "sốc", "nhồi máu"
    ]
    if any(keyword in cleaned_query for keyword in emergency_keywords):
        final_response = " **CẢNH BÁO KHẨN CẤP:** Dạ tình trạng của cô/chú rất nguy hiểm. Xin vui lòng BỎ QUA mọi thủ tục, di chuyển thẳng ra [QUẦY CẤP CỨU SỐ 1] ngay lập tức!"
        print(f"[EMERGENCY] Kích hoạt khẩn cấp cho: '{raw_query[:40]}'")
        log_exchange(raw_query, final_response)
        chat_history.append(HumanMessage(content=raw_query))
        chat_history.append(AIMessage(content=final_response))
        try:
            with _pending_lock:
                entry = _query_pending.pop(cache_key, None)
            if entry:
                ev, holder = entry
                holder.append(final_response)
                ev.set()
        except Exception:
            pass
        return final_response

    pending_whisper = None

    # 1.2. TỪ ĐIỂN QUY TẮC BỆNH NỀN RỦI RO CAO (Dễ dàng mở rộng)
    HIGH_RISK_RULES = [
        # --- Nhóm 1: Hô hấp ---
        {
            "conditions": ["hen", "suyễn", "copd", "phổi tắc nghẽn", "giãn phế quản"],
            "triggers": ["ho", "mệt", "cảm", "khó thở", "tức ngực"],
            "check_question": "Dạ, hệ thống thấy hồ sơ mình có tiền sử về hô hấp. Việc này có kèm theo cảm giác nặng ngực, khò khè hay khó thở ngay lúc này không ạ?",
            "danger_answers": ["có", "khó", "khò khè", "nặng", "ngợp", "mệt"]
        },
        # --- Nhóm 2: Tim mạch / Huyết áp ---
        {
            "conditions": ["tim", "huyết áp", "mạch vành", "nhồi máu", "suy tim", "rối loạn nhịp", "loạn nhịp"],
            "triggers": ["mệt", "chóng mặt", "đau vai", "đau lưng", "khó tiêu", "hồi hộp", "tim đập nhanh"],
            "check_question": "Dạ, hệ thống chú ý mình có tiền sử tim mạch/huyết áp. Cô/chú có đang cảm thấy đau thắt ngực, vã mồ hôi lạnh hay buồn nôn không ạ?",
            "danger_answers": ["có", "thắt", "vã", "mồ hôi", "lạnh", "buồn nôn"]
        },
        # --- Nhóm 3: Tiểu đường ---
        {
            "conditions": ["tiểu đường", "đái tháo đường", "đường huyết"],
            "triggers": ["mệt", "chóng mặt", "hoa mắt", "đói", "run", "vã mồ hôi"],
            "check_question": "Dạ, hệ thống thấy mình có bệnh nền tiểu đường. Hiện tại cô/chú có bị run rẩy tay chân, vã mồ hôi hay cảm thấy lả người đi không ạ?",
            "danger_answers": ["có", "run", "vã", "mồ hôi", "lả", "yếu"]
        },
        # --- Nhóm 4: Thai kỳ ---
        {
            "conditions": ["mang thai", "có thai", "thai kỳ", "sản phụ", "tuần thai", "tháng thai"],
            "triggers": ["đau bụng", "ra máu", "đau lưng", "chóng mặt", "phù", "đau đầu"],
            "check_question": "Dạ, hệ thống chú ý mình đang mang thai. Cô/chị có thấy xuất hiện cơn gò tử cung, ra máu âm đạo hay đau dữ dội không ạ?",
            "danger_answers": ["có", "máu", "gò", "dữ dội", "nhiều"]
        },
        # --- Nhóm 5: Thận / Suy thận ---
        {
            "conditions": ["thận", "suy thận", "sỏi thận", "viêm thận", "lọc máu", "chạy thận"],
            "triggers": ["đau lưng", "tiểu ít", "phù", "mệt", "buồn nôn", "khó thở"],
            "check_question": "Dạ, hệ thống thấy mình có tiền sử bệnh thận. Cô/chú có đang bị phù ở tay chân, tiểu rất ít hoặc không tiểu được, hay khó thở không ạ?",
            "danger_answers": ["có", "phù", "không tiểu", "tiểu ít", "khó thở", "tím"]
        },
        # --- Nhóm 6: Gan / Xơ gan ---
        {
            "conditions": ["gan", "xơ gan", "viêm gan", "men gan", "suy gan", "vàng da"],
            "triggers": ["đau bụng", "vàng da", "mệt", "buồn nôn", "phù bụng", "nôn máu"],
            "check_question": "Dạ, hệ thống chú ý mình có tiền sử về gan. Cô/chú có đang thấy da/mắt vàng hơn bình thường, bụng căng to hoặc có nôn ra máu không ạ?",
            "danger_answers": ["có", "vàng", "máu", "căng", "to", "nôn"]
        },
        # --- Nhóm 7: Động kinh / Co giật ---
        {
            "conditions": ["động kinh", "co giật", "epilepsy", "giật kinh"],
            "triggers": ["đau đầu", "mệt", "chóng mặt", "mất ngủ", "căng thẳng", "hoa mắt"],
            "check_question": "Dạ, hồ sơ ghi nhận mình có tiền sử động kinh. Gần đây cô/chú có bị co giật, mất ý thức thoáng qua hay cảm giác 'lạ lạ' khó tả trước cơn không ạ?",
            "danger_answers": ["có", "giật", "mất", "ngất", "lạ", "thoáng"]
        },
        # --- Nhóm 8: Ung thư / Đang hóa trị ---
        {
            "conditions": ["ung thư", "ung thư", "hóa trị", "xạ trị", "hóa xạ", "lymphoma", "leukemia"],
            "triggers": ["sốt", "mệt", "đau", "chảy máu", "bầm tím", "nhiễm trùng"],
            "check_question": "Dạ, hệ thống thấy mình đang trong quá trình điều trị ung thư. Cô/chú có đang bị sốt cao (trên 38°C), rét run, hoặc có vết thương chảy máu khó cầm không ạ?",
            "danger_answers": ["có", "sốt", "rét", "run", "chảy máu", "khó cầm"]
        },
        # --- Nhóm 9: Rối loạn đông máu / Dùng thuốc chống đông ---
        {
            "conditions": ["rối loạn đông máu", "chống đông", "warfarin", "heparin", "máu khó đông", "hemophilia"],
            "triggers": ["chảy máu", "bầm tím", "đau đầu", "đau bụng", "tiểu máu", "đi cầu ra máu"],
            "check_question": "Dạ, hồ sơ ghi nhận mình đang dùng thuốc chống đông/có rối loạn đông máu. Cô/chú có đang bị chảy máu bất thường ở đâu đó, hay đau đầu đột ngột dữ dội không ạ?",
            "danger_answers": ["có", "chảy máu", "máu", "đột ngột", "dữ dội", "không cầm"]
        },
        # --- Nhóm 10: Loãng xương / Tiền sử gãy xương ---
        {
            "conditions": ["loãng xương", "gãy xương", "losPorosis", "xương giòn", "thiếu canxi nặng"],
            "triggers": ["ngã", "va chạm", "đau xương", "đau lưng", "đau hông", "không đứng được"],
            "check_question": "Dạ, hồ sơ ghi nhận mình có tiền sử loãng xương. Cô/chú vừa bị ngã hoặc va chạm không ạ? Có đau nhói, không thể tự đứng dậy hoặc tay chân bị lệch hình không ạ?",
            "danger_answers": ["có", "ngã", "đau nhói", "không đứng", "lệch", "cong"]
        },
    ]

    active_rule = None
    with _history_lock:
        history_snapshot = list(chat_history)  # snapshot thread-safe
    if history_snapshot and isinstance(history_snapshot[-1], AIMessage):
        last_bot_msg = history_snapshot[-1].content
        for rule in HIGH_RISK_RULES:
            if rule["check_question"] in last_bot_msg:
                active_rule = rule
                break

    if active_rule:
        if any(word in cleaned_query for word in active_rule["danger_answers"]):
            final_response = " **CẢNH BÁO KHẨN CẤP:** Dấu hiệu biến chứng bệnh nền nguy hiểm! Xin vui lòng di chuyển thẳng ra [QUẦY CẤP CỨU SỐ 1] ngay lập tức!"
            log_exchange(raw_query, final_response)
            chat_history.append(HumanMessage(content=raw_query))
            chat_history.append(AIMessage(content=final_response))
            try:
                with _pending_lock:
                    entry = _query_pending.pop(cache_key, None)
                if entry:
                    ev, holder = entry
                    holder.append(final_response)
                    ev.set()
            except Exception:
                pass
            return final_response
        else:
            # [FAST PATH] Rủi ro bệnh nền đã loại trừ.
            # Tìm triệu chứng gốc từ lượt hỏi đầu tiên của bệnh nhân.
            with _history_lock:
                first_human_msg = next(
                    (m.content.lower() for m in chat_history if isinstance(m, HumanMessage)),
                    ""
                )
            # Tra SYMPTOM_QUESTIONS với triệu chứng gốc → tránh gọi LLM sinh câu hỏi dài
            symptom_followup = None
            for symptom, question in SYMPTOM_QUESTIONS.items():
                if symptom in first_human_msg:
                    symptom_followup = question
                    break

            if symptom_followup:
                # Có câu hỏi pre-coded → trả lời ngay, không cần LLM
                log_exchange(raw_query, symptom_followup)
                with _history_lock:
                    chat_history.append(HumanMessage(content=raw_query))
                    chat_history.append(AIMessage(content=symptom_followup))
                try:
                    with _pending_lock:
                        entry = _query_pending.pop(cache_key, None)
                    if entry:
                        ev, holder = entry
                        holder.append(symptom_followup)
                        ev.set()
                except Exception:
                    pass
                return symptom_followup
            else:
                # Không khớp SYMPTOM_QUESTIONS → để LLM hỏi thêm (kèm whisper hướng dẫn)
                pending_whisper = SystemMessage(
                    content="[HE THONG]: Rui ro benh nen da duoc loai tru. "
                            "Hay hoi tiep ve trieu chung ban dau (thoi gian, vi tri, muc do). "
                            "TUYET DOI CHUA DUOC vach lo trinh."
                )
    elif not active_rule:
        record_lower = patient_record_text.lower()
        _rule_matched = False
        
        with _history_lock:
            past_bot_msgs = [m.content for m in chat_history if isinstance(m, AIMessage)]
            
        for rule in HIGH_RISK_RULES:
            if any(rule["check_question"] in msg for msg in past_bot_msgs):
                continue
                
            has_condition = any(c in record_lower for c in rule["conditions"])
            has_trigger = any(t in cleaned_query for t in rule["triggers"])
            if has_condition and has_trigger:
                _rule_matched = True
                final_response = rule["check_question"]
                log_exchange(raw_query, final_response)
                with _history_lock:
                    chat_history.append(HumanMessage(content=raw_query))
                    chat_history.append(AIMessage(content=final_response))
                try:
                    with _pending_lock:
                        entry = _query_pending.pop(cache_key, None)
                    if entry:
                        ev, holder = entry
                        holder.append(final_response)
                        ev.set()
                except Exception:
                    pass
                return final_response

        # [LLM FALLBACK] Bệnh nhân có hồ sơ bệnh nền nhưng không khớp rule nào.
        # Inject whisper để LLM chủ động đọc hồ sơ và kiểm tra an toàn y khoa.
        _has_record = (
            patient_record_text
            and "khách vãng lai" not in record_lower
            and "không tìm thấy" not in record_lower
        )
        if not _rule_matched and _has_record:
            pending_whisper = SystemMessage(
                content=(
                    "[HE THONG - BAT BUOC DOC]: Benh nhan nay CO HO SO BENH AN voi tien su benh nen "
                    "chua duoc liet ke trong rule co dinh. "
                    "NHIEM VU: Doc ky phan [HO SO BENH AN], doi chieu toan bo benh nen va di ung "
                    "voi trieu chung hien tai. Neu phat hien to hop nguy hiem (VD: benh nen + trieu "
                    "chung co the la bien chung), HAY HOI KIEM TRA AN TOAN TRUOC khi vach lo trinh. "
                    "Neu khong co rui ro ro rang, tiep tuc hoi ve trieu chung binh thuong."
                )
            )

    # ── FAST PATH: Rule-based (không cần Qdrant + LLM) ──────────
    quick_answer = None
    if pending_whisper is None:
        quick_answer = quick_route(raw_query)
    if quick_answer is not None:
        print(f"[FAST PATH] '{raw_query[:40]}' → pre-coded answer")
        log_exchange(raw_query, quick_answer)
        chat_history.append(HumanMessage(content=raw_query))
        chat_history.append(AIMessage(content=quick_answer))
        # Mở khóa tiến trình nếu có luồng thứ 2 đang chờ
        try:
            with _pending_lock:
                entry = _query_pending.pop(cache_key, None)
            if entry:
                ev, holder = entry
                holder.append(quick_answer)
                ev.set()
        except Exception:
            pass
        return quick_answer
    # ─────────────────────────────────────────────────────────────

    setup_qdrant()
    global qdrant_client
        
    # Lấy tài liệu Text từ Qdrant
    query_vector = embed_model.encode(raw_query).tolist()
    search_results = qdrant_client.query_points(collection_name=COLLECTION_NAME, query=query_vector, limit=5).points
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
    # [GUARD] Giới hạn context để tránh tràn token
    if len(filtered_context) > 3000:
        filtered_context = filtered_context[:3000] + "\n...(đã cắt bớt để tiết kiệm token)"
    
    # Lấy dữ liệu Real-time từ SQL
    live_services, map_urls = fetch_live_services_from_mysql()
    # [GUARD] Giới hạn live_services để tránh tràn token
    if len(live_services) > 2000:
        live_services = live_services[:2000] + "\n...(đã cắt bớt)"
    
    messages = [
        SystemMessage(content=GENERATE_PROMPT.format(
            context=filtered_context,
            live_services=live_services,
            patient_record=patient_record_text
        )),
    ]
    # [GUARD] Chỉ giữ lại 4 tin nhắn gần nhất (2 lượt) để tránh loop tự tham chiếu
    with _history_lock:
        recent_history = list(chat_history[-4:])  # snapshot thread-safe
    messages.extend(recent_history)
    
    messages.append(HumanMessage(content=raw_query))


    if pending_whisper:
        messages.append(pending_whisper)
    
    route_text = ""  # [GUARD] khai báo trước try để luôn tồn tại dù có exception
    final_response = "Dạ, hệ thống đang bận. Cô/chú vui lòng qua Quầy số 1 ạ."  # default fallback

    try:
        decision: ReceptionDecision = structured_generator.invoke(messages)

        ai_text_lower = decision.ai_response.lower()

        # [ROLE GUARD] Phát hiện AI nhập vai sai (nói như bác sĩ hoặc bệnh nhân)
        WRONG_ROLE_SIGNALS = [
            "xin chào bác sĩ",       # chào bác sĩ → nhập vai sai
            "bệnh nhân của tôi",      # nói "bệnh nhân của tôi" → vai bác sĩ
            "tôi có triệu chứng",     # nói "tôi có triệu chứng" → vai bệnh nhân
            "bạn cho tôi biết",       # hỏi lại → vai bệnh nhân
            "hướng dẫn bạn đi theo", # văn phong sai vai
        ]
        if any(sig in ai_text_lower for sig in WRONG_ROLE_SIGNALS):
            log_error(f"[ROLE GUARD] Nhập vai sai: '{decision.ai_response[:80]}'")
            decision.ai_response = (
                "Dạ, để hỗ trợ tốt hơn, cô/chú vui lòng cho biết "
                "triệu chứng đau ở vị trí nào và bắt đầu từ bao giờ ạ?"
            )
            decision.is_ready_for_route = False
            decision.optimized_route = []
            ai_text_lower = decision.ai_response.lower()

        question_signals = [
            "?", "không ạ", "hỏi thêm", "cho biết", "mô tả", "kể thêm",
            "như thế nào", "cần thêm thông tin", "vui lòng cung cấp", "chi tiết hơn"
        ]
        # Nếu phát hiện AI đang cố moi thông tin → Xóa sạch lộ trình
        if any(signal in ai_text_lower for signal in question_signals):
            decision.is_ready_for_route = False
            decision.optimized_route = []

        final_response = decision.ai_response

        # Xây dựng phần lộ trình — CHỈ hiển thị màn hình, KHÔNG phát âm thanh
        if decision.optimized_route:
            # Xóa câu hỏi "xin phép" khỏi văn bản phát âm
            if "?" in final_response:
                final_response = final_response.split("?")[0] + "."
            route_text = "\n\n **LỘ TRÌNH KHÁM TỐI ƯU:**"
            for step in decision.optimized_route:
                route_text += f"\n{step.step_order}. **{step.service_name}** ({step.room})"
                route_text += f"\n   ↓ *Lý do:* {step.reasoning}"
                map_url = map_urls.get(step.service_id)
                if map_url:
                    route_text += f"\n  *Bản đồ:* {map_url}"
            
            if decision.is_ready_for_route and len(decision.optimized_route) > 0:
                first_step = sorted(decision.optimized_route, key=lambda x: x.step_order)[0]
                register_patient_to_queue(patient_id, first_step.service_id)

    except Exception as e:
        log_error(f"Loi xu ly cau truc: {e}")


    tts_response = final_response
    route_block = route_text  # luôn được khai báo trước try block
    display_response = final_response + route_block

    log_exchange(raw_query, display_response)
    with _history_lock:
        chat_history.append(HumanMessage(content=raw_query))
        chat_history.append(AIMessage(content=tts_response))

    # Giải phóng call thứ 2 đang chờ — luôn chạy dù có exception
    try:
        with _pending_lock:
            entry = _query_pending.pop(cache_key, None)
        if entry:
            ev, holder = entry
            holder.append(tts_response)
            ev.set()
    except Exception:
        pass

    return tts_response

def reset_brain_memory():
    """Hàm dùng để xóa sạch trí nhớ LLM khi có bệnh nhân mới"""
    with _history_lock:
        chat_history.clear()
    print(" [HỆ THỐNG]: Đã quét sạch bộ nhớ ngắn hạn của AI!")
    
if __name__ == "__main__":
    print("\n=== HỆ THỐNG ĐIỀU PHỐI BỆNH NHÂN SẴN SÀNG ===")
    last_input_time = time.time()
    timeout_duration = 60 * 60
    
    current_patient_id = input("Mô phỏng Quét mã bệnh nhân (Nhập BN-001, BN-002, BN-003, BN-004, BN-005,... hoặc nhấn Enter nếu là Khách mới): ").strip()
    patient_record_text = fetch_patient_record(current_patient_id)
    
    print("\n[ĐÃ TẢI HỒ SƠ BỆNH ÁN]")
    print(patient_record_text)
    
    while True:
        try:
            current_time = time.time()
            
            # Kiểm tra timeout 5 phút
            if current_time - last_input_time > timeout_duration:
                chat_history.clear()
                print(f"\n Cuộc trò chuyện đã hết hạn ({timeout_duration // 60} phút không hoạt động). Đã làm mới lịch sử hội thoại.")
                last_input_time = current_time  # Reset timer
            
            user_input = input("Người bệnh hỏi: ")
            last_input_time = time.time()  # Cập nhật thời gian nhập
            
            
            if user_input.lower() in ['exit', 'quit']:
                break
            
            # Reset cuộc trò chuyện nếu có lệnh refresh hoặc update
            if user_input.lower() in ['refresh', 'update']:
                chat_history.clear()
                print("Đã làm mới lịch sử hội thoại. Mọi ngữ cảnh trước đó đã bị xóa.")
                continue
            
            if user_input.lower().startswith('bn-'):
                current_patient_id = user_input.strip().upper()
                patient_record_text = fetch_patient_record(current_patient_id)
                chat_history.clear() # Reset lịch sử hội thoại khi chuyển sang bệnh nhân mới
                
                print("\n" + "*"*50)
                print("[ĐÃ TẢI HỒ SƠ BỆNH ÁN MỚI]")
                print(patient_record_text)
                print("*"*50 + "\n")
                
                print(f"Dạ, hệ thống đã nhận hồ sơ của {current_patient_id}. Cô chú cần khám gì ạ?")
                continue
            
            if user_input.strip(): 
                process_patient_query(user_input, patient_record_text, current_patient_id)
        except KeyboardInterrupt: 
            break
        