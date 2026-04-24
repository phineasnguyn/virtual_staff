import os
import uuid
from datetime import datetime
from langchain_text_splitters import RecursiveCharacterTextSplitter

from db_pipeline_modules.db_utils import init_mysql_db, get_db_connection
from db_pipeline_modules.document_loaders import extract_text_from_file
from db_pipeline_modules.vector_utils import delete_vectors_by_doc_id

def process_and_ingest_documents(data_folder: str):
    # Khởi tạo DB nếu chưa có
    config = init_mysql_db()
    
    # Cấu hình Text Splitter
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=150, 
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    print(f"Đang quét thư mục: {data_folder}...")
    
    for filename in os.listdir(data_folder):
        filepath = os.path.join(data_folder, filename)
        if os.path.isdir(filepath): continue
            
        print(f" -> Đang xử lý: {filename}")
        
        # 1. Trích xuất văn bản từ file (Module ngoài)
        raw_pages = extract_text_from_file(filepath)
        if not raw_pages:
            print(f"    (Bỏ qua file {filename} vì không trích xuất được text hoặc rỗng)")
            continue
            
        # 2. Khởi tạo Document ID và lấy thời gian
        docID = str(uuid.uuid5(uuid.NAMESPACE_DNS, filename))
        uploadTime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        totalPage = len(raw_pages)
        
        # 3. Kết nối DB qua Context Manager (đảm bảo đóng an toàn)
        with get_db_connection(config) as (conn, cursor):
            
            # GHI ĐÈ: Xóa document cũ (nếu có) trước khi insert
            # Bảng documentChunks sẽ tự động bị xóa theo nhờ ON DELETE CASCADE
            cursor.execute("DELETE FROM documents WHERE docID = %s", (docID,))
            
            # Xóa các vector tương ứng bên Qdrant (Tránh Ghost Vectors)
            delete_vectors_by_doc_id(docID)
            
            # NẠP DỮ LIỆU VÀO BẢNG documents
            cursor.execute("""
                INSERT INTO documents (docID, filename, filepath, uploadTime, totalPage)
                VALUES (%s, %s, %s, %s, %s)
            """, (docID, filename, filepath, uploadTime, totalPage))

            # CẮT CHUNK VÀ NẠP VÀO BẢNG documentChunks
            chunkIndex = 1
            for page_info in raw_pages:
                chunks = text_splitter.split_text(page_info["text"])
                
                for chunkText in chunks:
                    if len(chunkText.strip()) < 30: continue
                    
                    chunkID = str(uuid.uuid4())
                    pageNumber = str(page_info["page"])
                    
                    cursor.execute("""
                        INSERT INTO documentChunks (chunkID, docID, chunkIndex, chunkText, pageNumber)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (chunkID, docID, chunkIndex, chunkText, pageNumber))
                    
                    chunkIndex += 1
                    
        print(f"    + Đã cắt thành {chunkIndex - 1} chunks và lưu vào MySQL (Ghi đè nếu có).")

    print("\n=== HOÀN TẤT NẠP DỮ LIỆU VÀO MYSQL ===")

if __name__ == "__main__":
    process_and_ingest_documents("hospital_data")