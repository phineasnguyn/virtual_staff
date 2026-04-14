import os
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

ollama_rewriter = Ollama(model="qwen2.5:3b", temperature=0.1)
ollama_generator = ChatOllama(model="qwen2.5:3b", temperature=0.2)

# Khai báo biến lịch sử hội thoại
chat_history = []

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
        description="CÂU TRẢ LỜI: Giao tiếp tự nhiên, thấu cảm. Tự động thay đổi văn phong dựa theo internal_assessment (Hỏi thăm nhẹ nhàng, hoặc Cấp báo khẩn cấp, hoặc Đưa ra lộ trình)."
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
   - QUY TẮC HỎI TRIỆU CHỨNG (THIẾU DỮ KIỆN): Nếu bệnh nhân khai bệnh, bạn BẮT BUỘC phải hỏi để thu thập đủ 3 biến số sau:
     (1) Triệu chứng chính (VD: Đau, ho, chóng mặt, sốt).
     (2) Đặc điểm/Vị trí/Kèm theo (VD: đau rốn, ho có đờm, kèm buồn nôn).
     (3) Thời gian HOẶC Hoàn cảnh (VD: đau từ hôm qua, sau khi ăn, thay đổi tư thế).
     + LƯU Ý: Tuyệt đối không hỏi "vị trí" của các triệu chứng toàn thân (Ho, Sốt, Chóng mặt).
   - Bệnh cũ tái phát: Nếu triệu chứng trùng với hồ sơ bệnh án, hãy hỏi thêm 1-2 câu để rõ vị trí và thời gian đau trước khi vạch lộ trình.
   - CẦU DAO DỪNG HỎI (ĐỦ DỮ KIỆN): 
     + Cấm chốt sớm nếu thiếu bất kỳ biến số nào. Trừ khi bệnh nhân cũng không rõ (VD: "Tôi chỉ biết là đau bụng thôi, chứ không rõ vị trí nào"). Trong trường hợp này, bạn có thể chốt tạm thời nhưng phải ghi rõ "Vị trí đau chưa rõ ràng, cần bác sĩ khám kỹ hơn".
     + CHỈ KHI NÀO bệnh nhân cung cấp ĐỦ CẢ 3 Biến số (Thời gian, Đặc điểm, Vị trí) -> BẮT BUỘC DỪNG HỎI. Lập tức vạch lộ trình!

     
3. ĐỐI CHIẾU AN TOÀN Y KHOA (PHẢI ĐỌC HỒ SƠ ĐẦU TIÊN):
   - LỆNH BẮT BUỘC: NẾU có [HỒ SƠ BỆNH ÁN], bạn PHẢI phân tích phần 'Bệnh nền' và 'Dị ứng' TRƯỚC KHI phản hồi.
   - CẤM HỎI THỪA: NẾU hồ sơ ĐÃ GHI rõ bệnh nền/dị ứng, TUYỆT ĐỐI KHÔNG hỏi lại "Bạn có bị dị ứng không?".
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
    conn=db_pool.get_connection()
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
    cursor.close()
    conn.close()
    return results

# Hàm mới: Lấy thông tin dịch vụ và thời gian chờ Real-time
def fetch_live_services_from_mysql():
    conn=db_pool.get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT service_name, room, current_wait_time_mins, medical_rule FROM hospital_services")
    services = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # Định dạng thành chuỗi văn bản để nhét vào Prompt
    services_text = ""
    for s in services:
        services_text += f"- Dịch vụ: {s['service_name']} | Phòng: {s['room']} | Chờ: {s['current_wait_time_mins']} phút | Quy tắc: {s['medical_rule']}\n"
    return services_text

# Hàm truy xuất hồ sơ bệnh án từ SQL dựa trên patient_id (nếu có)
def fetch_patient_record(patient_id: str) -> str:
    """Truy xuất hồ sơ bệnh án từ SQL"""
    if not patient_id:
        return "Bệnh nhân mới (Khách vãng lai) - Chưa có hồ sơ trên hệ thống."
        
    conn = db_pool.get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM patient_records WHERE patient_id = %s", (patient_id,))
    record = cursor.fetchone()
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

# --- 4. LUỒNG XỬ LÝ CHÍNH ---
def process_patient_query(raw_query: str, patient_record_text: str = "") -> str:
    print(f"\n NGƯỜI BỆNH: {raw_query}")
    
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
    
    # Lấy dữ liệu Real-time từ SQL
    live_services = fetch_live_services_from_mysql()
    
    messages = [
        SystemMessage(content=GENERATE_PROMPT.format(context=filtered_context, live_services=live_services, patient_record=patient_record_text),),
    ]
    #Nối thêm lịch sử hội thoại để LLM có ngữ cảnh đầy đủ hơn khi đưa ra quyết định
    messages.extend(chat_history)
    
    messages.append(HumanMessage(content=raw_query))

    cleaned_query = raw_query.lower()
    # [1] BỘ ĐÁNH CHẶN CẤP CỨU TOÀN DIỆN (UNIVERSAL INTERCEPTOR)

    # 1.1. LỚP 1: TỪ KHÓA TỬ THẦN (Cấp cứu ngay lập tức, bất kể ai)
    emergency_keywords = [
        "gãy", "chảy máu", "tai nạn", "bỏng", "ngất", "chó cắn", "vết thương hở", 
        "khó thở", "tức ngực", "đau ngực", "đau tim", "đột quỵ", "sốc", "nhồi máu"
    ]
    if any(keyword in cleaned_query for keyword in emergency_keywords):
        final_response = " **CẢNH BÁO KHẨN CẤP:** Dạ tình trạng của cô/chú rất nguy hiểm. Xin vui lòng BỎ QUA mọi thủ tục, di chuyển thẳng ra [QUẦY CẤP CỨU SỐ 1] ngay lập tức!"
        print("\n" + "="*60 + f"\n LỄ TÂN ẢO: {final_response}\n" + "="*60 + "\n")
        chat_history.append(HumanMessage(content=raw_query))
        chat_history.append(AIMessage(content=final_response))
        return final_response

    # 1.2. TỪ ĐIỂN QUY TẮC BỆNH NỀN RỦI RO CAO (Dễ dàng mở rộng)
    HIGH_RISK_RULES = [
        {
            "conditions": ["hen", "suyễn", "copd", "phổi tắc nghẽn"],
            "triggers": ["ho", "mệt", "cảm"],
            "check_question": "Dạ, hệ thống thấy hồ sơ mình có tiền sử về hô hấp. Việc này có kèm theo cảm giác nặng ngực, khò khè hay khó thở ngay lúc này không ạ?",
            "danger_answers": ["có", "khó", "khò khè", "nặng", "ngợp", "mệt"]
        },
        {
            "conditions": ["tim", "huyết áp", "mạch vành", "nhồi máu"],
            "triggers": ["mệt", "chóng mặt", "đau vai", "đau lưng", "khó tiêu"],
            "check_question": "Dạ, hệ thống chú ý mình có tiền sử tim mạch/huyết áp. Cô/chú có đang cảm thấy đau thắt ngực, vã mồ hôi lạnh hay buồn nôn không ạ?",
            "danger_answers": ["có", "thắt", "vã", "mồ hôi", "lạnh", "buồn nôn"]
        },
        {
            "conditions": ["tiểu đường", "đái tháo đường"],
            "triggers": ["mệt", "chóng mặt", "hoa mắt", "đói"],
            "check_question": "Dạ, hệ thống thấy mình có bệnh nền tiểu đường. Hiện tại cô/chú có bị run rẩy tay chân, vã mồ hôi hay cảm thấy lả người đi không ạ?",
            "danger_answers": ["có", "run", "vã", "mồ hôi", "lả", "yếu"]
        },
        {
            "conditions": ["mang thai", "có thai", "thai kỳ", "sản phụ"],
            "triggers": ["đau bụng", "ra máu", "đau lưng", "chóng mặt"],
            "check_question": "Dạ, hệ thống chú ý mình đang mang thai. Cô/chị có thấy xuất hiện cơn gò tử cung, ra máu âm đạo hay đau dữ dội không ạ?",
            "danger_answers": ["có", "máu", "gò", "dữ dội", "nhiều"]
        }
    ]

    # 2.3. LỚP 2: XỬ LÝ LOGIC HỎI/ĐÁP BỆNH NỀN
    
    # Bước A: Kiểm tra xem Lễ tân có đang đợi khách trả lời câu hỏi xác nhận rủi ro không?
    active_rule = None
    if len(chat_history) > 0 and isinstance(chat_history[-1], AIMessage):
        last_bot_msg = chat_history[-1].content
        for rule in HIGH_RISK_RULES:
            if rule["check_question"] in last_bot_msg:
                active_rule = rule
                break

    # Bước B: Khách đang trả lời câu hỏi kiểm tra chéo
    if active_rule:
        if any(word in cleaned_query for word in active_rule["danger_answers"]):
            final_response = " **CẢNH BÁO KHẨN CẤP:** Dấu hiệu biến chứng bệnh nền nguy hiểm! Xin vui lòng di chuyển thẳng ra [QUẦY CẤP CỨU SỐ 1] ngay lập tức!"
            print("\n" + "="*60 + f"\n LỄ TÂN ẢO: {final_response}\n" + "="*60 + "\n")
            chat_history.append(HumanMessage(content=raw_query))
            chat_history.append(AIMessage(content=final_response))
            return final_response
        else:
            # Khách nói "Không/Bình thường" -> Bỏ qua, để AI Qwen 3B tiếp quản
            # TRẠNG THÁI AN TOÀN: Khách nói "Không/Bình thường"
            hidden_whisper = " [LỆNH HỆ THỐNG ẨN: Rủi ro bệnh nền đã được loại trừ. Bạn BẮT BUỘC phải quay lại hỏi tiếp về TRIỆU CHỨNG BAN ĐẦU (thời gian, mức độ) theo đúng Quy tắc 3 Biến số. TUYỆT ĐỐI CHƯA ĐƯỢC VẠCH LỘ TRÌNH NGAY!]"
            
            # Gắn lời nhắc này vào sau câu trả lời "Không" của khách để ép AI phải đọc
            raw_query = raw_query + hidden_whisper

    # Bước C: Khách mới khai bệnh -> Quét xem có dính bẫy bệnh nền không?
    elif not active_rule:
        record_lower = patient_record_text.lower()
        for rule in HIGH_RISK_RULES:
            has_condition = any(c in record_lower for c in rule["conditions"])
            has_trigger = any(t in cleaned_query for t in rule["triggers"])
            
            if has_condition and has_trigger:
                final_response = rule["check_question"]
                print("\n" + "="*60 + f"\n LỄ TÂN ẢO: {final_response}\n" + "="*60 + "\n")
                chat_history.append(HumanMessage(content=raw_query))
                chat_history.append(AIMessage(content=final_response))
                return final_response # Cắt ngang, không gọi LLM
    
    try:
        decision: ReceptionDecision = structured_generator.invoke(messages)
        
        ai_text_lower = decision.ai_response.lower()
        
        question_signals = [
        "?", "không ạ", "hỏi thêm", "cho biết", "mô tả", "kể thêm",
        "như thế nào", "cần thêm thông tin", "vui lòng cung cấp", "chi tiết hơn"
    ]
        
        # Nếu phát hiện AI đang cố moi thông tin -> Xóa sạch lộ trình
        if any(signal in ai_text_lower for signal in question_signals):
            decision.is_ready_for_route = False
            decision.optimized_route = []

        final_response = decision.ai_response
        
        # In lộ trình nếu lọt qua bộ lọc
        if len(decision.optimized_route) > 0:
            # Nếu có lộ trình, ta chủ động xóa bỏ các câu hỏi "xin phép" ở cuối response để tránh nhầm lẫn
            if "?" in final_response:
                final_response = final_response.split("?")[0] + "." 

            final_response += "\n\n **LỘ TRÌNH KHÁM TỐI ƯU:**"
            for step in decision.optimized_route:
                final_response += f"\n{step.step_order}. **{step.service_name}** ({step.room})"
                final_response += f"\n   ↳ *Lý do:* {step.reasoning}"
                
    except Exception as e:
        print(f"Lỗi khi xử lý cấu trúc: {e}")
        final_response = "Dạ, hệ thống đang bận. Cô/chú vui lòng qua Quầy số 1 ạ."

    print("\n" + "="*60)
    print(f" LỄ TÂN ẢO: {final_response}")
    print("="*60 + "\n")

    chat_history.append(HumanMessage(content=raw_query))
    chat_history.append(AIMessage(content=final_response))
    return final_response

def reset_brain_memory():
    """Hàm dùng để xóa sạch trí nhớ LLM khi có bệnh nhân mới"""
    global chat_history
    chat_history.clear()
    print(" [HỆ THỐNG]: Đã quét sạch bộ nhớ ngắn hạn của AI!")
    
if __name__ == "__main__":
    print("\n=== HỆ THỐNG ĐIỀU PHỐI BỆNH NHÂN SẴN SÀNG ===")
    last_input_time = time.time()
    timeout_duration = 60 * 60
    
    current_patient_id = input("Mô phỏng Quét mã bệnh nhân (Nhập BN-001, BN-002, BN-003, BN-004, BN-005, BN-006, BN-007, BN-008, BN-009, BN-010 hoặc nhấn Enter nếu là Khách mới): ").strip()
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
                process_patient_query(user_input, patient_record_text)
        except KeyboardInterrupt: 
            break
        