from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, Filter, FieldCondition, MatchValue

COLLECTION_NAME = "hospital_vector_index"
QDRANT_PATH = "./local_qdrant_db"

_qdrant_client = None

def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(path=QDRANT_PATH)
        
        # Tạo Collection nếu chưa tồn tại
        if not _qdrant_client.collection_exists(COLLECTION_NAME):
            _qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
            print(f" -> Đã tạo collection mới trong Qdrant: {COLLECTION_NAME}")
    return _qdrant_client

def delete_vectors_by_doc_id(doc_id: str):
    """
    Xóa tất cả các vector thuộc về một tài liệu (docID) khỏi Qdrant.
    Được gọi khi người dùng upload lại file cùng tên để tránh lưu rác (Ghost Vectors).
    """
    client = get_qdrant_client()
    try:
        # Xóa theo payload condition (lọc theo doc_id)
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="doc_id",
                        match=MatchValue(value=doc_id)
                    )
                ]
            )
        )
        print(f"    + [Qdrant] Đã dọn dẹp các vector cũ của docID: {doc_id}")
    except Exception as e:
        print(f"    + [Qdrant] Lỗi khi dọn dẹp vector: {e}")

def get_all_qdrant_chunk_ids() -> set:
    """
    Lấy danh sách tất cả các ID (sql_chunk_id) hiện có trong Qdrant.
    Dùng để so sánh và chỉ nạp (ingest) những chunk CHƯA CÓ.
    Do Qdrant bản local chưa hỗ trợ Scroll / Pagination dễ dàng lấy id, 
    ta sử dụng count hoặc scroll (nếu có thể).
    """
    client = get_qdrant_client()
    try:
        # Scroll để lấy toàn bộ điểm (lưu ý: dataset siêu lớn thì nên tối ưu đoạn này)
        records, next_page_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=10000,
            with_payload=False,
            with_vectors=False
        )
        existing_ids = set([record.id for record in records])
        
        # Nếu dataset quá lớn (hơn 10k), cần lặp scroll
        while next_page_offset is not None:
            records, next_page_offset = client.scroll(
                collection_name=COLLECTION_NAME,
                limit=10000,
                offset=next_page_offset,
                with_payload=False,
                with_vectors=False
            )
            existing_ids.update([record.id for record in records])
            
        return existing_ids
    except Exception as e:
        print(f"Lỗi khi quét ID từ Qdrant: {e}")
        return set()
