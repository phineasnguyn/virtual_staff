import os
import random
import time
import mysql.connector
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder
from langchain_community.llms import Ollama
from langchain_ollama import ChatOllama # Đã sửa import chuẩn
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Literal, List

# --- 1. CẤU HÌNH HỆ THỐNG ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'hospital_rag_db'
}
COLLECTION_NAME = "hospital_vector_index"
RERANK_THRESHOLD = -2.0

print("=== ĐANG KHỞI ĐỘNG HỆ THỐNG LỄ TÂN ẢO ĐIỀU HƯỚNG ===")
embed_model = SentenceTransformer('all-MiniLM-L6-v2')
rerank_model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
qdrant_client = QdrantClient(path="./local_qdrant_db")

ollama_rewriter = Ollama(model="qwen3", temperature=0.1)
ollama_generator = ChatOllama(model="qwen3", temperature=0.2)

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
        description="True NẾU internal_assessment cho thấy đã đủ cơ sở an toàn để vạch lộ trình cận lâm sàng( NGHĨA LÀ KHI internal_assessment là 'ĐỦ RÕ RÀNG', không phải 'TÌNH HUỐNG KHẨN CẤP' và KHÔNG CÒN CÂU HỎI NÀO ĐƯỢC ĐƯA RA CHO BỆNH NHÂN'). False NẾU cần có câu hỏi thêm hoặc nghi ngờ cần có câu hỏi thêm hoặc là ca cấp cứu."
    )
    ai_response: str = Field(
        description="CÂU TRẢ LỜI: Giao tiếp tự nhiên, thấu cảm. Tự động thay đổi văn phong dựa theo internal_assessment (Hỏi thăm nhẹ nhàng, hoặc Cấp báo khẩn cấp, hoặc Đưa ra lộ trình)."
    )
    optimized_route: List[RouteStep] = Field(
        description="Danh sách lộ trình di chuyển. Bắt buộc để trống nếu is_ready_for_route = False."
    )

GENERATE_PROMPT = """
Bạn là Lễ tân Ảo thông minh tại sảnh bệnh viện. Nhiệm vụ của bạn là lắng nghe, phân loại và điều hướng bệnh nhân linh hoạt nhất có thể.

[TÀI LIỆU QUY TRÌNH HÀNH CHÍNH]:
{context}

[DANH SÁCH DỊCH VỤ & THỜI GIAN]:
{live_services}

NGUYÊN TẮC ỨNG XỬ LINH HOẠT:
1. ĐÁNH GIÁ MỨC ĐỘ (Internal Assessment): Trước khi trả lời, hãy tự phân tích câu nói của bệnh nhân. 
   - Nếu chung chung (VD: "Tôi mệt", "Tôi đau bụng"): Hãy đặt 1-2 câu hỏi mở tự nhiên để gợi ý họ kể thêm.
   - Nếu là TÌNH HUỐNG KHẨN CẤP (VD: Chảy máu, khó thở, ngất xỉu, tai nạn): BỎ QUA mọi quy trình lộ trình. Lập tức hướng dẫn họ đi thẳng ra [Quầy Cấp Cứu Số 1] với tông giọng khẩn trương.
   - Nếu thông tin ĐỦ RÕ RÀNG để biết cần khám khoa nào (VD: "Đau bụng trên, ợ chua", hoặc "Đau rát họng kéo dài"): Lúc này mới kích hoạt vạch lộ trình cận lâm sàng cơ bản.
2. TRUY VẾT CẬN LÂM SÀNG BẮT BUỘC (QUAN TRỌNG):
   - Khi bạn chọn một Khoa Khám Lâm Sàng (VD: Tim mạch, Nội tiết), bạn BẮT BUỘC phải đọc kỹ 'medical_rule' của khoa đó. 
   - Nếu rule yêu cầu phải làm xét nghiệm trước (VD: Tim mạch yêu cầu ECG, Nội tiết yêu cầu Máu), bạn PHẢI tự động bốc các xét nghiệm cận lâm sàng đó từ [DANH SÁCH DỊCH VỤ] và xếp lên các Bước 1, Bước 2 sao chi tối ưu thời gian nhất (TRƯỚC khi gặp bác sĩ).
3. PHONG CÁCH GIAO TIẾP: Không dùng văn mẫu. Hãy linh hoạt phản hồi dựa theo cảm xúc và tình trạng của bệnh nhân. Giữ thái độ: Ân cần, Chuyên nghiệp, Nhanh gọn.
4. TUYỆT ĐỐI KHÔNG chẩn đoán bệnh thay bác sĩ.
5. Không được bịa các dịch vụ ngoài danh sách
"""

structured_generator = ollama_generator.with_structured_output(ReceptionDecision)

# --- 3. CÁC HÀM TRUY XUẤT DỮ LIỆU ---
def fetch_text_from_mysql(chunk_ids):
    if not chunk_ids: return []
    conn = mysql.connector.connect(**DB_CONFIG)
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

def fetch_live_services_from_mysql():
    """Hàm mới: Lấy thông tin dịch vụ và thời gian chờ Real-time"""
    conn = mysql.connector.connect(**DB_CONFIG)
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

# --- 4. LUỒNG XỬ LÝ CHÍNH ---
def process_patient_query(raw_query: str) -> str:
    print(f"\n NGƯỜI BỆNH: {raw_query}")
    
    history_text = "\n".join([f"{'Người bệnh' if isinstance(m, HumanMessage) else 'Lễ tân'}: {m.content}" for m in chat_history[-4:]])
    
    #promt này sẽ giúp Qwen3 hiểu được ngữ cảnh của cuộc hội thoại trước đó để viết lại câu truy vấn chính xác hơn, đặc biệt khi người bệnh trả lời mập mờ hoặc có dấu hiệu cấp cứu.
    rewrite_prompt_with_history = PromptTemplate(
        input_variables=["history", "raw_query"],
        template="""Dựa vào đoạn hội thoại trước đó, hãy viết lại câu nói mới nhất của người bệnh thành câu truy vấn đầy đủ ý nghĩa y khoa.
        TUYỆT ĐỐI CHỈ IN RA TỪ KHÓA. KHÔNG giải thích, KHÔNG phân tích, KHÔNG xuống dòng.
        [Lịch sử hội thoại]:
        {history}
        [Câu mới nhất]: {raw_query}
        [Câu truy vấn chuẩn (chỉ ghi từ khóa)]:"""
    )
    rewritten_query = ollama_rewriter.invoke(rewrite_prompt_with_history.format(history=history_text, raw_query=raw_query)).strip()
    print(f" [Lễ tân hiểu ý]: {rewritten_query}")
    
    # Lấy tài liệu Text từ Qdrant
    query_vector = embed_model.encode(rewritten_query).tolist()
    search_results = qdrant_client.query_points(collection_name=COLLECTION_NAME, query=query_vector, limit=5).points
    chunk_ids = [hit.id for hit in search_results] if search_results else []
    mysql_docs = fetch_text_from_mysql(chunk_ids)
    
    filtered_context = ""
    if mysql_docs:
        pairs = [[rewritten_query, doc['chunkText']] for doc in mysql_docs]
        scores = rerank_model.predict(pairs)
        scored_docs = sorted(zip(mysql_docs, scores), key=lambda x: x[1], reverse=True)
        for doc, score in scored_docs:
            if score >= RERANK_THRESHOLD:
                filtered_context += f"- [Nguồn: {doc['filename']} - Trang {doc['pageNumber']}]: {doc['chunkText']}\n"
    
    # Lấy dữ liệu Real-time từ SQL
    live_services = fetch_live_services_from_mysql()
    
    messages = [
        SystemMessage(content=GENERATE_PROMPT.format(context=filtered_context, live_services=live_services)),
    ]
    #Nối thêm lịch sử hội thoại để LLM có ngữ cảnh đầy đủ hơn khi đưa ra quyết định
    messages.extend(chat_history)
    
    messages.append(HumanMessage(content=raw_query))
    
    try:
        decision: ReceptionDecision = structured_generator.invoke(messages)
        final_response = decision.ai_response
        
        # In lộ trình nếu AI quyết định vạch đường
        if decision.is_ready_for_route and decision.optimized_route:
            final_response += "\n\n **LỘ TRÌNH KHÁM TỐI ƯU DÀNH CHO CÔ/CHÚ:**"
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
    chat_history.append(SystemMessage(content=final_response))
    return final_response
if __name__ == "__main__":
    print("\n=== HỆ THỐNG ĐIỀU PHỐI BỆNH NHÂN SẴN SÀNG ===")
    last_input_time = time.time()
    timeout_duration = 60 * 60
    
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
            
            if user_input.strip(): 
                process_patient_query(user_input)
        except KeyboardInterrupt: 
            break