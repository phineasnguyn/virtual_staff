from sentence_transformers import SentenceTransformer
from qdrant_client.models import PointStruct

from db_pipeline_modules.db_utils import get_db_connection
from db_pipeline_modules.vector_utils import get_qdrant_client, get_all_qdrant_chunk_ids, COLLECTION_NAME

def sync_mysql_to_qdrant():
    print("1. Đang khởi tạo Model Embedding và Qdrant...")
    # Model biến text thành vector (384 chiều)
    embed_model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Lấy Qdrant client (đã bao gồm tự tạo Collection nếu chưa có)
    qdrant_client = get_qdrant_client()

    print("2. Đang kiểm tra các chunk đã có trong Qdrant...")
    existing_qdrant_ids = get_all_qdrant_chunk_ids()
    print(f" -> Qdrant hiện đang có {len(existing_qdrant_ids)} vectors.")

    print("3. Đang kết nối MySQL để lấy dữ liệu Text...")
    
    # Kết nối MySQL an toàn qua context manager
    with get_db_connection() as (conn, cursor):
        # Lấy thêm docID để nhúng vào payload, phục vụ cho việc xóa sau này
        cursor.execute("SELECT chunkID, docID, chunkText FROM documentChunks")
        rows = cursor.fetchall()
        
        if not rows:
            print("Không tìm thấy dữ liệu trong MySQL. Vui lòng chạy file database_pipeline.py trước.")
            return

        print(f" -> Tìm thấy {len(rows)} chunks trong MySQL.")
        
        # CHỈ LỌC NHỮNG CHUNK CHƯA CÓ TRONG QDRANT (Incremental Sync)
        chunks_to_insert = [row for row in rows if row['chunkID'] not in existing_qdrant_ids]
        
        if not chunks_to_insert:
            print(" -> Toàn bộ dữ liệu đã được đồng bộ. Không có chunk nào mới cần mã hóa.")
            print("\n=== HOÀN TẤT ĐỒNG BỘ VECTOR THÀNH CÔNG ===")
            return
            
        print(f" -> Có {len(chunks_to_insert)} chunks MỚI. Bắt đầu mã hóa thành Vector...")
        
        # 4. Bơm dữ liệu vào Qdrant theo Batch (Gói nhỏ) để tránh tràn RAM
        points = []
        BATCH_SIZE = 100
        
        for idx, row in enumerate(chunks_to_insert):
            chunkID = row['chunkID']
            docID = row['docID']
            chunkText = row['chunkText']
            
            # Biến đoạn text thành ma trận số
            vector_data = embed_model.encode(chunkText).tolist()
            
            point = PointStruct(
                id=chunkID,
                vector=vector_data,
                # Thêm doc_id vào payload để sau này xóa dễ dàng
                payload={"sql_chunk_id": chunkID, "doc_id": docID}
            )
            points.append(point)
            
            # Đẩy từng lô 100 điểm lên Qdrant
            if len(points) >= BATCH_SIZE:
                qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
                print(f"    + Đã đồng bộ {idx + 1}/{len(chunks_to_insert)} vectors mới...")
                points = [] # Xóa bộ nhớ tạm
                
        # Đẩy nốt số điểm còn lẻ chưa đủ 100
        if points:
            qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
            print(f"    + Đã đồng bộ {len(chunks_to_insert)}/{len(chunks_to_insert)} vectors mới...")

    print("\n=== HOÀN TẤT ĐỒNG BỘ VECTOR THÀNH CÔNG ===")

if __name__ == "__main__":
    sync_mysql_to_qdrant()