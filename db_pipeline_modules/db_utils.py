import mysql.connector
from contextlib import contextmanager

# --- CẤU HÌNH MYSQL ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
}

DB_NAME = 'hospital_rag_db'

def init_mysql_db():
    """Tạo database + bảng documents và documentChunks. Trả về thông tin pool để tái sử dụng."""
    
    # 1. Kết nối KHÔNG chọn database trước
    conn = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )
    cursor = conn.cursor()

    # 2. Tạo database nếu chưa tồn tại
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cursor.execute(f"USE {DB_NAME}")

    # 3. Tạo bảng documents
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        docID VARCHAR(50) PRIMARY KEY,
        filename VARCHAR(255) NOT NULL,
        filepath VARCHAR(255) NOT NULL,
        uploadTime DATETIME,
        totalPage INT
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    """)

    # 4. Tạo bảng documentChunks
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
    cursor.close()
    conn.close()
    
    # Cấu hình pool cho toàn bộ ứng dụng
    pool_config = DB_CONFIG.copy()
    pool_config['database'] = DB_NAME
    
    # Trả về config để nơi khác có thể dùng
    return pool_config

def init_services_db():
    """Tạo database và bảng hospital_services. Trả về cấu hình cho pool."""
    conn = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )
    cursor = conn.cursor()
    db_name = 'hospital_services_db'
    
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cursor.execute(f"USE {db_name}")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hospital_services (
        service_id VARCHAR(20) PRIMARY KEY,
        service_name VARCHAR(255) NOT NULL,
        department VARCHAR(100),
        room VARCHAR(100),
        est_duration_mins INT,
        current_wait_time_mins INT,
        machine_processing_time INT DEFAULT 0,
        medical_rule TEXT
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    """)
    conn.commit()
    cursor.close()
    conn.close()
    
    pool_config = DB_CONFIG.copy()
    pool_config['database'] = db_name
    return pool_config

def init_patients_db():
    """Tạo database và bảng patient_records. Trả về cấu hình cho pool."""
    conn = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )
    cursor = conn.cursor()
    db_name = 'patient_records_db'
    
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cursor.execute(f"USE {db_name}")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patient_records (
        patient_id VARCHAR(20) PRIMARY KEY,
        full_name VARCHAR(100),
        age INT,
        gender VARCHAR(10),
        chronic_conditions TEXT,
        allergies TEXT,
        past_history TEXT
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    """)
    conn.commit()
    cursor.close()
    conn.close()
    
    pool_config = DB_CONFIG.copy()
    pool_config['database'] = db_name
    return pool_config

@contextmanager
def get_db_connection(config=None):
    """Context manager để lấy connection và đảm bảo đóng an toàn.
    Sử dụng: with get_db_connection() as (conn, cursor): ...
    """
    if config is None:
        config = DB_CONFIG.copy()
        config['database'] = DB_NAME
        
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)
    try:
        yield conn, cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()
