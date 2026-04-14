import mysql.connector
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

# --- CẤU HÌNH ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'hospital_rag_db'
}
COLLECTION_NAME = "hospital_vector_index"

def sync_mysql_to_qdrant():
    print("1. Đang khởi tạo Model Embedding và Qdrant...")
    # Model biến text thành vector (384 chiều)
    embed_model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Khởi tạo Qdrant lưu trữ offline trên ổ cứng (thư mục local_qdrant_db)
    qdrant_client = QdrantClient(path="./local_qdrant_db")
    
    # Tạo Collection nếu chưa tồn tại
    if not qdrant_client.collection_exists(COLLECTION_NAME):
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        print(f" -> Đã tạo collection mới: {COLLECTION_NAME}")

    print("2. Đang kết nối MySQL để lấy dữ liệu Text...")
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Chỉ lấy chunkID và chunkText. Không cần lấy các thông tin khác.
    cursor.execute("SELECT chunkID, chunkText FROM documentChunks")
    rows = cursor.fetchall()
    
    if not rows:
        print("Không tìm thấy dữ liệu trong MySQL. Vui lòng chạy file database_pipeline.py trước.")
        return

    print(f" -> Tìm thấy {len(rows)} chunks. Bắt đầu mã hóa thành Vector...")
    
    # 3. Bơm dữ liệu vào Qdrant theo Batch (Gói nhỏ) để tránh tràn RAM
    points = []
    BATCH_SIZE = 100
    
    for idx, (chunkID, chunkText) in enumerate(rows):
        # Biến đoạn text thành ma trận số
        vector_data = embed_model.encode(chunkText).tolist()
        
        point = PointStruct(
            id=chunkID,
            vector=vector_data,
            # Payload cực kỳ nhẹ, chỉ chứa đúng chìa khóa để trỏ về MySQL
            payload={"sql_chunk_id": chunkID}
        )
        points.append(point)
        
        # Đẩy từng lô 100 điểm lên Qdrant
        if len(points) >= BATCH_SIZE:
            qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
            print(f"    + Đã đồng bộ {idx + 1}/{len(rows)} vectors...")
            points = [] # Xóa bộ nhớ tạm
            
    # Đẩy nốt số điểm còn lẻ chưa đủ 100
    if points:
        qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"    + Đã đồng bộ {len(rows)}/{len(rows)} vectors...")

    cursor.close()
    conn.close()
    print("\n=== HOÀN TẤT ĐỒNG BỘ VECTOR THÀNH CÔNG ===")

if __name__ == "__main__":
    sync_mysql_to_qdrant()