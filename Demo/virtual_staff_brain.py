import os
import random
import mysql.connector
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder
from langchain_community.llms import Ollama
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from typing import Literal
from pydantic import BaseModel, Field

# --- 1. CẤU HÌNH HỆ THỐNG ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'hospital_rag_db'
}
COLLECTION_NAME = "hospital_vector_index"
RERANK_THRESHOLD = -2.0

print("=== ĐANG KHỞI ĐỘNG HỆ THỐNG LỄ TÂN ẢO (LOCAL) ===")
embed_model = SentenceTransformer('all-MiniLM-L6-v2')
rerank_model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
qdrant_client = QdrantClient(path="./local_qdrant_db")

# Dùng Qwen3 cho cả việc dịch ý và sinh hội thoại
ollama_rewriter = Ollama(model="qwen3", temperature=0.1)
ollama_generator = ChatOllama(model="qwen3", temperature=0.2)

# --- 2. ĐỊNH NGHĨA LẠI PROMPT CHO LỄ TÂN ---
REWRITE_PROMPT = PromptTemplate(
    input_variables=["raw_query"],
    template="""Bạn là một Lễ tân bệnh viện. Hãy viết lại câu hỏi của người bệnh thành một câu truy vấn ngắn gọn để tìm kiếm trong sổ tay quy trình hành chính. 
    Chỉ giữ lại các từ khóa về: thủ tục, bảo hiểm, giá tiền, phòng ban, hoặc mô tả triệu chứng. Không giải thích.
    Câu của người bệnh: {raw_query}
    Câu truy vấn chuẩn:"""
)

#Pydantic để ép Qwen3 trả về JSON rõ ràng
class ReceptionDecision(BaseModel):
    ai_response: str = Field(
        description="Câu giao tiếp của lễ tân. Lịch sự, thấu cảm. NẾU quyết định cấp số, chỉ thông báo hướng di chuyển. NẾU triệu chứng phức tạp hoặc nguy hiểm (như khó thở), hãy mời ra Quầy số 1. KHÔNG ĐƯỢC VỪA ĐẶT CÂU HỎI XÁC NHẬN VỪA CẤP SỐ."
    )
    is_ready_for_ticket: bool = Field(
        description="Chỉ đặt True khi bạn CHẮC CHẮN 100% khoa cần khám VÀ câu ai_response không có bất kỳ câu hỏi nào. NẾU trong ai_response bạn còn hỏi lại người bệnh hoặc mời ra Quầy 1, BẮT BUỘC đặt False."
    )
    department_name: str = Field(
        description="Tên khoa khám bệnh (vd: Nội khoa, Ngoại khoa, Tai Mũi Họng...). NẾU is_ready_for_ticket = False thì để chuỗi rỗng."
    )

GENERATE_PROMPT = """
Bạn là Lễ tân Ảo tại sảnh chờ của bệnh viện. Nhiệm vụ của bạn là hướng dẫn thủ tục, chỉ đường, báo giá dịch vụ và phân luồng khoa khám để giảm tải cho nhân viên y tế.

Dưới đây là TÀI LIỆU QUY TRÌNH HÀNH CHÍNH trích xuất từ hệ thống:
{context}

NGUYÊN TẮC CỐT LÕI:
1. TÍNH NHẤT QUÁN: Nếu bạn quyết định cấp số khám (is_ready_for_ticket=True), câu trả lời của bạn chỉ được phép hướng dẫn di chuyển, TUYỆT ĐỐI KHÔNG hỏi thêm. Nếu bạn cần hỏi thêm, TUYỆT ĐỐI KHÔNG cấp số (is_ready_for_ticket=False).
2. XỬ LÝ TRIỆU CHỨNG LẠ/NGUY HIỂM: Nếu người bệnh có các triệu chứng mâu thuẫn, hoặc có dấu hiệu nguy cấp (như KHÓ THỞ, chảy máu nhiều), KHÔNG ĐƯỢC TỰ Ý CẤP SỐ. Hãy nói: "Dạ, với các triệu chứng phức tạp này, cô/chú vui lòng qua trực tiếp Quầy Hướng dẫn số 1 (Khu vực Cấp cứu) để được nhân viên y tế kiểm tra ngay lập tức ạ."
3. CHỈ hướng dẫn thủ tục, số phòng, và quy định dựa trên tài liệu trên. TUYỆT ĐỐI KHÔNG chẩn đoán bệnh hay khuyên dùng thuốc.
4. Luôn xưng hô lịch sự, thân thiện (Dạ, thưa, cô/chú/anh/chị).
"""
structured_generator = ollama_generator.with_structured_output(ReceptionDecision)

# --- 3. TÍNH NĂNG MỞ RỘNG: LẤY SỐ TỰ ĐỘNG ---
def generate_queue_number(department: str) -> str:
    prefix=department[:2].upper() if department else "A"
    number = random.randint(100, 999)
    return f"{prefix}-{number}"

# --- 4. CÁC HÀM XỬ LÝ LÕI ---
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

def process_patient_query(raw_query: str) -> str:
    print(f"\n NGƯỜI BỆNH: {raw_query}")
    
    # [TÍNH NĂNG MỚI]: Bắt ý định Lấy số/Đăng ký khám nhanh bằng Keyword đơn giản
    # Trong thực tế, bạn có thể dùng một bước phân loại Intent (Intent Classification) nhỏ trước khi chạy RAG

    rewritten_query = ollama_rewriter.invoke(REWRITE_PROMPT.format(raw_query=raw_query)).strip()
    print(f" [Lễ tân hiểu ý]: {rewritten_query}")
    
    
    #Qdrant Retrieval
    query_vector = embed_model.encode(rewritten_query).tolist()
    search_results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME, query=query_vector, limit=5
    ).points
    
    chunk_ids = [hit.id for hit in search_results] if search_results else []
    mysql_docs = fetch_text_from_mysql(chunk_ids)
    
    #Reranking
    filtered_context = ""
    if mysql_docs:
        pairs = [[rewritten_query, doc['chunkText']] for doc in mysql_docs]
        scores = rerank_model.predict(pairs)
        scored_docs = sorted(zip(mysql_docs, scores), key=lambda x: x[1], reverse=True)
        
        valid_docs = [doc for doc, score in scored_docs if score >= RERANK_THRESHOLD]
        for doc in valid_docs:
            filtered_context += f"- [Nguồn: {doc['filename']} - Trang {doc['pageNumber']}]: {doc['chunkText']}\n\n"
    
    if not filtered_context.strip():
        filtered_context = "[HỆ THỐNG KHÔNG CÓ THÔNG TIN. HÃY MỜI NGƯỜI BỆNH RA QUẦY SỐ 1]"
        
    messages = [
        SystemMessage(content=GENERATE_PROMPT.format(context=filtered_context)),
        HumanMessage(content=raw_query)
    ]
    # Gọi LLM để sinh phản hồi có cấu trúc (câu trả lời + có cần cấp số hay không + tên khoa nếu có)
    try:
        decision: ReceptionDecision = structured_generator.invoke(messages)
        
        final_response = decision.ai_response
        
        if decision.is_ready_for_ticket and decision.department_name:
            stt = generate_queue_number(decision.department_name)
            final_response += f"\n\n **Hệ thống đã cấp số thứ tự cho cô/chú: [{stt}]. Vui lòng di chuyển đến khu vực chờ Khoa {decision.department_name}, cô/chú vui lòng nhìn lên màn hình ạ.**"
            
    except Exception as e:
        print(f" LỖI KHI GỌI AI: {e}")
        final_response = "Dạ, hiện tại cháu chưa tra cứu được thông tin này. Cô/chú vui lòng qua Quầy Hướng dẫn số 1 để được nhân viên trực tiếp hỗ trợ ạ."
    
    print("\n" + "="*50)
    print(f" LỄ TÂN ẢO: {final_response}")
    print("="*50 + "\n")
    return final_response

if __name__ == "__main__":
    print("\n=== LỄ TÂN ẢO SẴN SÀNG ===")
    while True:
        try:
            user_input = input("Người bệnh hỏi: ")
            if user_input.lower() in ['exit', 'quit']:
                print("Đang tắt hệ thống Lễ tân ảo. Hẹn gặp lại!")
                break
            if user_input.strip(): process_patient_query(user_input)
        except KeyboardInterrupt: break