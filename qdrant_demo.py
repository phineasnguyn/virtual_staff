from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

# 1. Khởi tạo model embedding và Client
embed_model = SentenceTransformer('all-MiniLM-L6-v2')
client = QdrantClient(":memory:")

# 2. Tạo Collection
client.create_collection(
    collection_name="knowledge_base",
    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
)

# 3. Dữ liệu giả lập
documents = [
    # Chủ đề: Công nghệ & AI
    "Qdrant là vector database viết bằng Rust, tối ưu cho việc tìm kiếm vector.",
    "Reranking giúp cải thiện độ chính xác của chatbot bằng cách chấm điểm lại các kết quả.",
    "Việc sử dụng LLM để trích xuất thông tin cần kết hợp với thư viện như Pydantic để đảm bảo output có cấu trúc chuẩn JSON.",
    "Vector search hoạt động dựa trên việc tính toán khoảng cách Cosine hoặc Euclidean giữa các điểm trong không gian đa chiều.",
    
    # Chủ đề: Y tế & Digital Twin
    "Hệ thống Digital Twin có thể mô phỏng trạng thái sức khỏe của bệnh nhân tại nhà để tự động liên hệ người thân khi có sự cố khẩn cấp.",
    "Quy trình phân luồng bệnh nhân (Triage) tự động giúp điều hướng người bệnh đến đúng chuyên khoa, giảm tải cho bệnh viện.",
    "Trợ lý AI y tế cần được cung cấp thông tin bảo hiểm để tư vấn chính xác chi phí khám chữa bệnh cho bệnh nhân.",
    
    # Chủ đề: Game & Giải trí
    "Để tối ưu tỷ lệ đập thẻ thành công, người chơi thường sử dụng chiến thuật mồi thẻ với các cầu thủ chỉ số thấp trước khi nâng cấp thẻ chính.",
    "Chỉ số phôi càng cao thì tỷ lệ nâng cấp thẻ thành công ở các mức cộng cao (+5, +8) càng được đảm bảo.",
    
    # Chủ đề: Kiến thức chung (Nhiễu)
    "Hôm nay thời tiết tại Hà Nội rất đẹp, thích hợp để đi dạo phố.",
    "Bún chả là một món ăn đặc sản truyền thống quen thuộc của người dân thủ đô.",
    "Thuật toán sắp xếp QuickSort có độ phức tạp trung bình là O(n log n)."
]

# 4. Upsert dữ liệu vào Qdrant
points = [
    PointStruct(
        id=idx,
        vector=embed_model.encode(doc).tolist(),
        payload={"text": doc}
    ) for idx, doc in enumerate(documents)
]
client.upsert(collection_name="knowledge_base", points=points)

from sentence_transformers import CrossEncoder

# Khởi tạo model Reranker (Cross-Encoder)
rerank_model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

test_queries = [
    "Làm sao để tăng tỷ lệ nâng cấp cầu thủ?",
    "Ứng dụng AI trong việc điều hướng bệnh nhân?",
    "Cách ép kiểu dữ liệu đầu ra của LLM cho chuẩn?",
]

print("="*50)
# Chạy vòng lặp để test từng câu hỏi
for query in test_queries:
    print(f"\n CÂU HỎI: '{query}'")
    
    # --- RETRIEVAL (Giai đoạn 1) ---
    query_vector = embed_model.encode(query).tolist()
    search_results = client.query_points(
        collection_name="knowledge_base",
        query=query_vector,
        limit=5  # Lấy top 5 kết quả thô
    ).points
    
    retrieved_docs = [hit.payload["text"] for hit in search_results]
    
    # --- RERANKING (Giai đoạn 2) ---
    pairs = [[query, doc] for doc in retrieved_docs]
    scores = rerank_model.predict(pairs)
    
    # Ghép điểm và sắp xếp
    reranked_results = sorted(zip(retrieved_docs, scores), key=lambda x: x[1], reverse=True)
    
    # In ra Top 1 sau khi Rerank
    best_doc, best_score = reranked_results[0]
    print(f" KẾT QUẢ CHỌN LỌC (Score: {best_score:.4f}):\n   -> {best_doc}")
    
print("\n" + "="*50)