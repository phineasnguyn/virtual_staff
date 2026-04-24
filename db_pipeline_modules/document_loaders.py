import os
import pandas as pd
from PIL import Image
import pytesseract
from langchain_community.document_loaders import PyMuPDFLoader, Docx2txtLoader, TextLoader

# Cấu hình OCR
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def extract_text_from_file(filepath: str) -> list[dict]:
    """
    Trích xuất text từ các định dạng file khác nhau.
    Trả về danh sách các dict chứa text và page number: [{"text": "...", "page": 1}, ...]
    Cô lập Exception handling để không làm chết toàn bộ tiến trình.
    """
    raw_pages = []
    ext = os.path.splitext(filepath)[-1].lower()
    
    try:
        if ext == '.pdf':
            loader = PyMuPDFLoader(filepath)
            pages = loader.load()
            raw_pages = [{"text": p.page_content, "page": p.metadata.get("page", 0) + 1} for p in pages]
        
        elif ext == '.docx':
            raw_pages = [{"text": Docx2txtLoader(filepath).load()[0].page_content, "page": 1}]
        
        elif ext == '.txt':
            raw_pages = [{"text": TextLoader(filepath, encoding='utf-8').load()[0].page_content, "page": 1}]
        
        elif ext == '.csv':
            # Sửa lỗi: CSV chỉ có 1 bảng, không thể lặp qua sheet
            df = pd.read_csv(filepath)
            text_content = df.dropna(how='all').dropna(axis=1, how='all').to_string(index=False)
            raw_pages = [{"text": f"Dữ liệu CSV:\n{text_content}", "page": 1}]
            
        elif ext in ['.xlsx', '.xls']:
            excel_data = pd.read_excel(filepath, sheet_name=None)
            for sheet_name, df in excel_data.items():
                text_content = df.dropna(how='all').dropna(axis=1, how='all').to_string(index=False)
                raw_pages.append({"text": f"Dữ liệu Sheet '{sheet_name}':\n{text_content}", "page": sheet_name})
                
        elif ext in ['.png', '.jpg', '.jpeg']:
            img = Image.open(filepath)
            raw_pages = [{"text": pytesseract.image_to_string(img, lang='vie'), "page": 1}]
            
    except Exception as e:
        print(f"Lỗi trích xuất file {filepath}: {e}")
        
    return raw_pages
