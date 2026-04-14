import os
import uuid
import pandas as pd
from PIL import Image
import pytesseract
from langchain_community.document_loaders import PyMuPDFLoader, Docx2txtLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Cấu hình đường dẫn Tesseract OCR cho Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def extract_text_from_file(file_path: str):
    """
    Router đa năng: Tự động chọn công cụ trích xuất chữ dựa vào đuôi file.
    Trả về một list chứa các dict: [{"text": "nội dung", "page_num": 1}, ...]
    """
    ext = os.path.splitext(file_path)[-1].lower()
    extracted_data = []

    try:
        if ext == '.pdf':
            loader = PyMuPDFLoader(file_path)
            for page in loader.load():
                extracted_data.append({
                    "text": page.page_content, 
                    "page_num": page.metadata.get("page", 0) + 1
                })
                
        elif ext == '.txt':
            loader = TextLoader(file_path, encoding='utf-8')
            extracted_data.append({
                "text": loader.load()[0].page_content, 
                "page_num": 1
            })
            
        elif ext == '.docx':
            loader = Docx2txtLoader(file_path)
            extracted_data.append({
                "text": loader.load()[0].page_content, 
                "page_num": 1
            })
            
        elif ext in ['.xlsx', '.xls', '.csv']:
            if ext == '.csv':
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path, sheet_name=None)
            
            for sheet_name, df in excel_data.items():
                df = df.dropna(how='all').dropna(axis=1, how='all')
                text_content = df.to_string(index=False)
                extracted_data.append({
                    "text": f"Dữ liệu từ Sheet '{sheet_name}':\n{text_content}", 
                    "page_num": sheet_name
                })
                
        elif ext in ['.png', '.jpg', '.jpeg']:
            img = Image.open(file_path)
            text_content = pytesseract.image_to_string(img, lang='vie')
            extracted_data.append({
                "text": text_content, 
                "page_num": 1
            })
            
        else:
            print(f"Bỏ qua định dạng không hỗ trợ: {ext}")
            
    except Exception as e:
        print(f"Lỗi khi đọc file {file_path}: {e}")
        
    return extracted_data

def process_raw_documents(data_folder: str):
    """
    Quét thư mục, đọc đa định dạng, cắt chunk và chuẩn bị dữ liệu cho SQL & Qdrant.
    """
    processed_data = []
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " ", ""] 
    )

    print(f"Đang quét thư mục: {data_folder}...")
    
    for filename in os.listdir(data_folder):
        file_path = os.path.join(data_folder, filename)
        
        if os.path.isdir(file_path):
            continue
            
        print(f" -> Đang trích xuất: {filename}")
        
        # 1. Trích xuất text thô
        raw_pages = extract_text_from_file(file_path)
        
        # 2. Cắt Chunk và gán ID
        for page_info in raw_pages:
            raw_text = page_info["text"]
            page_identifier = page_info["page_num"]
            
            chunks = text_splitter.split_text(raw_text)
            
            for chunk_text in chunks:
                if len(chunk_text.strip()) < 30: 
                    continue 

                chunk_id = str(uuid.uuid4())
                sql_doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{filename}_{page_identifier}")) 
                
                processed_data.append({
                    "qdrant_point": {
                        "id": chunk_id,
                        "text": chunk_text,
                        "sql_ref_id": sql_doc_id 
                    },
                    "sql_metadata": {
                        "sql_ref_id": sql_doc_id,
                        "source_file": filename,
                        "location_in_file": str(page_identifier),
                        "department_tag": "Chưa phân loại"
                    }
                })

    return processed_data

if __name__ == "__main__":
    DATA_DIR = "hospital_data"
    
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        print(f"Đã tạo thư mục '{DATA_DIR}'. Vui lòng ném file (PDF, DOCX, TXT, XLSX, JPG) vào đây và chạy lại!")
    else:
        results = process_raw_documents(DATA_DIR)
        
        print("\n=== HOÀN TẤT XỬ LÝ ===")
        print(f"Tổng số chunks tạo ra: {len(results)}")
        
        if results:
            print("\n[MẪU DỮ LIỆU ĐÃ BÓC TÁCH]")
            print("Qdrant Data:", results[0]["qdrant_point"])
            print("SQL Data:", results[0]["sql_metadata"])