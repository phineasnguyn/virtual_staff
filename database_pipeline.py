import os
import uuid
import pandas as pd
from PIL import Image
import pytesseract
import mysql.connector
from datetime import datetime
from langchain_community.document_loaders import PyMuPDFLoader, Docx2txtLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Cấu hình OCR
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# --- CẤU HÌNH MYSQL ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'hospital_rag_db'
}

def init_mysql_db():
    """Tạo database + bảng documents và documentChunks"""

    # 1. Kết nối KHÔNG chọn database trước
    conn = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )
    cursor = conn.cursor()

    # 2. Tạo database nếu chưa tồn tại
    cursor.execute("CREATE DATABASE IF NOT EXISTS hospital_rag_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")

    # 3. Sử dụng database
    cursor.execute("USE hospital_rag_db")

    # 4. Tạo bảng documents
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        docID VARCHAR(50) PRIMARY KEY,
        filename VARCHAR(255) NOT NULL,
        filepath VARCHAR(255) NOT NULL,
        uploadTime DATETIME,
        totalPage INT
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    """)

    # 5. Tạo bảng documentChunks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documentChunks (
        chunkID VARCHAR(50) PRIMARY KEY,
        docID VARCHAR(50) NOT NULL,
        chunkIndex INT,
        chunkText TEXT,
        pageNumber VARCHAR(50),
        FOREIGN KEY (docID) REFERENCES documents(docID) ON DELETE CASCADE
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    """)

    conn.commit()
    return conn, cursor

def process_and_ingest_documents(data_folder: str):
    conn, cursor = init_mysql_db()
    
    # chunk_overlap=150: Đảm bảo 150 ký tự cuối của chunk 1 sẽ được lặp lại ở đầu chunk 2
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
        
        # 1. Khởi tạo Document ID và lấy thời gian hiện tại
        docID = str(uuid.uuid5(uuid.NAMESPACE_DNS, filename))
        uploadTime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        raw_pages = []
        ext = os.path.splitext(filename)[-1].lower()

        # 2. Trích xuất text tùy theo định dạng
        try:
            if ext == '.pdf':
                loader = PyMuPDFLoader(filepath)
                pages = loader.load()
                raw_pages = [{"text": p.page_content, "page": p.metadata.get("page", 0) + 1} for p in pages]
            elif ext == '.docx':
                raw_pages = [{"text": Docx2txtLoader(filepath).load()[0].page_content, "page": 1}]
            elif ext == '.txt':
                raw_pages = [{"text": TextLoader(filepath, encoding='utf-8').load()[0].page_content, "page": 1}]
            elif ext in ['.xlsx', '.xls','.csv']:
                if ext == '.csv':
                    excel_data = pd.read_csv(filepath)
                else:
                    excel_data = pd.read_excel(filepath, sheet_name=None)
                for sheet_name, df in excel_data.items():
                    text_content = df.dropna(how='all').dropna(axis=1, how='all').to_string(index=False)
                    raw_pages.append({"text": f"Dữ liệu Sheet '{sheet_name}':\n{text_content}", "page": sheet_name})
            elif ext in ['.png', '.jpg', '.jpeg']:
                img = Image.open(filepath)
                raw_pages = [{"text": pytesseract.image_to_string(img, lang='vie'), "page": 1}]
        except Exception as e:
            print(f"Lỗi đọc file {filename}: {e}")
            continue

        if not raw_pages: continue

        totalPage = len(raw_pages)

        # 3. NẠP DỮ LIỆU VÀO BẢNG documents
        cursor.execute("""
            INSERT IGNORE INTO documents (docID, filename, filepath, uploadTime, totalPage)
            VALUES (%s, %s, %s, %s, %s)
        """, (docID, filename, filepath, uploadTime, totalPage))

        # 4. CẮT CHUNK VÀ NẠP VÀO BẢNG documentChunks
        chunkIndex = 1
        for page_info in raw_pages:
            chunks = text_splitter.split_text(page_info["text"])
            
            for chunkText in chunks:
                if len(chunkText.strip()) < 30: continue
                
                chunkID = str(uuid.uuid4())
                pageNumber = str(page_info["page"])
                
                cursor.execute("""
                    INSERT IGNORE INTO documentChunks (chunkID, docID, chunkIndex, chunkText, pageNumber)
                    VALUES (%s, %s, %s, %s, %s)
                """, (chunkID, docID, chunkIndex, chunkText, pageNumber))
                
                chunkIndex += 1

        conn.commit()
        print(f"    + Đã cắt thành {chunkIndex - 1} chunks và lưu vào MySQL.")

    cursor.close()
    conn.close()
    print("\n=== HOÀN TẤT NẠP DỮ LIỆU VÀO MYSQL ===")

if __name__ == "__main__":
    
    process_and_ingest_documents("hospital_data")