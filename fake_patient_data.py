from db_pipeline_modules.db_utils import init_patients_db, get_db_connection

def seed_patient_records():
    # 1. Khởi tạo Database và Bảng từ db_utils
    db_config = init_patients_db()

    # 2. Kết nối an toàn qua Context Manager để nạp dữ liệu
    with get_db_connection(db_config) as (conn, cursor):
        # TẬP DỮ LIỆU 10 HỒ SƠ "BẪY" DÙNG ĐỂ TEST LOGIC AI
        fake_patients = [
            # 1. Ca Tim mạch cơ bản
            ("BN-001", "Trần Văn Ánh", 65, "Nam", "Tăng huyết áp, Đái tháo đường tuýp 2", "Dị ứng thuốc kháng sinh Penicillin", "Từng bị nhồi máu cơ tim năm 2023"),
            
            # 2. Ca Dị ứng thực phẩm cấp tính
            ("BN-002", "Nguyễn Thị Bình", 28, "Nữ", "Không có bệnh nền", "Dị ứng hải sản gây nổi mề đay, khó thở", "Chưa từng phẫu thuật"),
            
            # 3. Ca đã phẫu thuật tiêu hóa
            ("BN-003", "Lê Hoàng Cường", 45, "Nam", "Viêm loét dạ dày mạn tính", "Không phát hiện dị ứng", "Đã phẫu thuật cắt ruột thừa năm 2015, Cắt túi mật năm 2020"),
            
            # 4. BẪY CHỤP MRI: Bệnh nhân có kim loại trong người
            ("BN-004", "Phạm Văn Dũng", 55, "Nam", "Thoái hóa cột sống", "Không", "Đã phẫu thuật kết hợp xương đùi (có nẹp vít kim loại) năm 2022"),
            
            # 5. BẪY CHỤP CT/X-QUANG: Phụ nữ mang thai
            ("BN-005", "Hoàng Thu Trà", 30, "Nữ", "Mang thai tuần 24 (Tháng thứ 6)", "Dị ứng phấn hoa", "Khỏe mạnh"),
            
            # 6. BẪY DỊ ỨNG THUỐC CẢN QUANG (Cấm tiêm thuốc khi nội soi/chụp chiếu)
            ("BN-006", "Vũ Quốc Hưng", 50, "Nam", "Gout mạn tính", "Sốc phản vệ với Thuốc cản quang có I-ốt", "Sỏi thận"),
            
            # 7. BẪY HÔ HẤP (Hen suyễn)
            ("BN-007", "Đinh Bích Ngọc", 35, "Nữ", "Hen phế quản (Suyễn) nặng", "Dị ứng lông chó mèo", "Thường xuyên nhập viện vì cơn hen cấp"),
            
            # 8. BẪY NHÃN KHOA (Tiểu đường biến chứng)
            ("BN-008", "Ngô Khắc Việt", 60, "Nam", "Đái tháo đường tuýp 1 hơn 10 năm", "Không", "Đã mổ đục thủy tinh thể mắt trái"),
            
            # 9. BẪY NGOẠI KHOA (Đang dùng thuốc chống đông máu - cấm nhổ răng/phẫu thuật bừa bãi)
            ("BN-009", "Lý Mai Lan", 70, "Nữ", "Rung nhĩ, Đang uống thuốc chống đông máu Aspirin hàng ngày", "Không", "Thay van tim nhân tạo năm 2018"),
            
            # 10. Bệnh nhân hoàn toàn khỏe mạnh
            ("BN-010", "Bùi Tấn Phát", 22, "Nam", "Không", "Không", "Sinh viên, thể trạng tốt, chưa từng nằm viện"),
            
            # --- BỔ SUNG 50 HỒ SƠ BỆNH ÁN ĐA DẠNG ---
            # Nhóm hô hấp
            ("BN-011", "Trịnh Kim Oanh", 45, "Nữ", "Viêm phế quản mạn tính", "Phấn hoa", "Từng nhập viện vì đợt cấp viêm phế quản"),
            ("BN-012", "Hồ Quang Hiếu", 38, "Nam", "Hen suyễn nhẹ", "Không", "Hay sử dụng bình xịt giãn phế quản"),
            ("BN-013", "Phan Thị Mai", 60, "Nữ", "COPD (Phổi tắc nghẽn mạn tính)", "Kháng sinh nhóm Sulfa", "Hút thuốc lá 20 năm đã bỏ"),
            ("BN-014", "Đoàn Văn Hậu", 25, "Nam", "Viêm xoang dị ứng", "Lông chó mèo, Bụi nhà", "Thường xuyên nghẹt mũi khi đổi mùa"),
            ("BN-015", "Tạ Đình Phong", 50, "Nam", "Lao phổi đã điều trị khỏi", "Không", "Điều trị lao năm 2018"),

            # Nhóm tim mạch, huyết áp
            ("BN-016", "Nguyễn Thu Hương", 68, "Nữ", "Suy tim độ 2, Tăng huyết áp", "Không", "Thay van 2 lá năm 2015"),
            ("BN-017", "Lý Thanh Bình", 55, "Nam", "Rối loạn nhịp tim (Ngoại tâm thu)", "Caffein", "Thỉnh thoảng có cơn hồi hộp, đánh trống ngực"),
            ("BN-018", "Đặng Thị Hoa", 72, "Nữ", "Bệnh mạch vành, Tăng huyết áp", "Aspirin (gây hen)", "Đặt 2 stent mạch vành năm 2021"),
            ("BN-019", "Vương Quốc Bảo", 40, "Nam", "Cao huyết áp vô căn", "Không", "Phát hiện bệnh năm 35 tuổi"),
            ("BN-020", "Trương Mỹ Lan", 80, "Nữ", "Hở van động mạch chủ nhẹ, Lão hóa", "Không", "Có triệu chứng chóng mặt tư thế"),

            # Nhóm tiêu hóa, gan mật
            ("BN-021", "Bùi Việt Hoàng", 34, "Nam", "Viêm loét dạ dày tá tràng, Nhiễm HP", "Không", "Từng điều trị xuất huyết tiêu hóa năm 2022"),
            ("BN-022", "Lê Thị Thảo", 42, "Nữ", "Trào ngược dạ dày thực quản (GERD)", "Sữa bò (Bất dung nạp Lactose)", "Thường xuyên ợ chua, nóng rát ngực"),
            ("BN-023", "Nguyễn Văn Toàn", 58, "Nam", "Xơ gan độ F2 (do rượu)", "Không", "Đang cai rượu"),
            ("BN-024", "Phạm Bích Thủy", 30, "Nữ", "Hội chứng ruột kích thích (IBS)", "Hải sản sống", "Hay bị đau bụng quặn, tiêu chảy khi căng thẳng"),
            ("BN-025", "Hoàng Đăng Khoa", 65, "Nam", "Sỏi mật, Viêm túi mật mạn", "Thuốc giảm đau NSAID", "Từng có cơn đau quặn mật phải nhập viện"),

            # Nhóm nội tiết, chuyển hóa
            ("BN-026", "Đinh Hữu Trí", 52, "Nam", "Đái tháo đường tuýp 2, Rối loạn mỡ máu", "Không", "Đang tiêm Insulin hỗn hợp 2 lần/ngày"),
            ("BN-027", "Vũ Cẩm Ly", 48, "Nữ", "Suy giáp (Đang dùng Levothyroxine)", "Hải sản", "Phẫu thuật cắt tuyến giáp bán phần năm 2019"),
            ("BN-028", "Trần Bá Đạo", 36, "Nam", "Gout mạn tính, Béo phì độ 1", "Hải sản, Rượu bia (làm khởi phát cơn Gout)", "Đang dùng Allopurinol hàng ngày"),
            ("BN-029", "Nguyễn Kiều Oanh", 28, "Nữ", "Cường giáp (Basedow)", "Không", "Đang điều trị nội khoa, nhịp tim hay nhanh"),
            ("BN-030", "Lê Văn Tám", 75, "Nam", "Đái tháo đường biến chứng thần kinh ngoại biên", "Không", "Tê bì hai bàn chân, thị lực giảm"),

            # Nhóm thận, tiết niệu
            ("BN-031", "Phạm Thu Hà", 46, "Nữ", "Sỏi thận 2 bên, Viêm đường tiết niệu tái phát", "Kháng sinh nhóm Ciprofloxacin", "Từng tán sỏi ngoài cơ thể năm 2020"),
            ("BN-032", "Trần Trọng Kim", 62, "Nam", "Suy thận mạn độ 3", "Không", "Theo dõi định kỳ hàng tháng"),
            ("BN-033", "Nguyễn Thái Học", 70, "Nam", "Phì đại tuyến tiền liệt", "Không", "Tiểu đêm nhiều lần, tia tiểu yếu"),
            ("BN-034", "Lý Thu Thủy", 32, "Nữ", "Viêm bàng quang cấp tái diễn", "Không", "Hay bị tiểu buốt, tiểu rắt"),
            ("BN-035", "Võ Hồng Nam", 50, "Nam", "Nang thận đơn thuần", "Không", "Tình cờ phát hiện qua siêu âm, không triệu chứng"),

            # Nhóm cơ xương khớp, thần kinh
            ("BN-036", "Đặng Thùy Trâm", 65, "Nữ", "Loãng xương, Thoái hóa khớp gối 2 bên", "Thuốc cản quang I-ốt", "Từng gãy xương quay tay trái năm 2021"),
            ("BN-037", "Nguyễn Hải Đăng", 40, "Nam", "Thoát vị đĩa đệm L4-L5", "Không", "Đau thần kinh tọa chân trái"),
            ("BN-038", "Lê Quý Đôn", 55, "Nam", "Đau nửa đầu Migraine", "Sô cô la, Rượu vang đỏ", "Có những cơn đau đầu dữ dội kèm buồn nôn"),
            ("BN-039", "Hoàng Hữu Phước", 35, "Nam", "Viêm cột sống dính khớp", "NSAID", "Cứng khớp buổi sáng, hạn chế vận động"),
            ("BN-040", "Phạm Mai Anh", 29, "Nữ", "Động kinh cơn vắng ý thức", "Không", "Đang dùng thuốc chống động kinh, kiểm soát tốt"),

            # Nhóm ung thư, huyết học
            ("BN-041", "Nguyễn Văn Hùng", 58, "Nam", "K Phổi giai đoạn 3 (Đang hóa trị)", "Không", "Rụng tóc, thể trạng suy kiệt"),
            ("BN-042", "Trần Thị Bé", 45, "Nữ", "K Vú (Đã đoạn nhũ và xạ trị)", "Không", "Mổ năm 2022, hiện đang theo dõi định kỳ"),
            ("BN-043", "Lê Đại Hành", 12, "Nam", "Thalassemia (Mang gen bệnh)", "Không", "Thiếu máu nhẹ, hay mệt mỏi"),
            ("BN-044", "Lý Băng Băng", 60, "Nữ", "Rối loạn đông máu (Giảm tiểu cầu)", "Aspirin", "Hay có mảng bầm tím dưới da tự nhiên"),
            ("BN-045", "Vũ Trọng Phụng", 70, "Nam", "K Đại tràng (Đã phẫu thuật)", "Không", "Đang mang hậu môn nhân tạo"),

            # Nhóm trẻ em, thai phụ, sản phụ khoa
            ("BN-046", "Bé Bào Ngư", 5, "Nữ", "Viêm tai giữa tái phát", "Sữa bò", "Hay sốt, quấy khóc"),
            ("BN-047", "Hoàng Tú Anh", 25, "Nữ", "Mang thai tuần 32, Tiểu đường thai kỳ", "Không", "Đang ăn kiêng kiểm soát đường huyết"),
            ("BN-048", "Lý Nhã Kỳ", 33, "Nữ", "U xơ tử cung đa nhân", "Không", "Hay rong kinh, cường kinh"),
            ("BN-049", "Đặng Siêu", 8, "Nam", "Tự kỷ nhẹ", "Không", "Rối loạn phát triển ngôn ngữ"),
            ("BN-050", "Phạm Băng Băng", 27, "Nữ", "Mang thai tuần 12, Nghén nặng", "Không", "Nôn nhiều, sụt cân"),

            # Nhóm người cao tuổi, đa bệnh lý (Geriatrics)
            ("BN-051", "Cụ Đồ Chiểu", 85, "Nam", "Sa sút trí tuệ (Alzheimer), Cao huyết áp, Phì đại tiền liệt tuyến", "Không", "Trí nhớ kém, cần người nhà đi kèm"),
            ("BN-052", "Cụ Bà Tám", 88, "Nữ", "Suy tim, Loãng xương nặng, Suy giảm thính lực", "Không", "Đi lại khó khăn, phải dùng xe lăn"),
            ("BN-053", "Nguyễn Ngọc Ngạn", 78, "Nam", "COPD, Tiểu đường, Viêm khớp dạng thấp", "Penicillin", "Di chuyển bằng gậy, hay khó thở"),

            # Nhóm các bệnh lý khác
            ("BN-054", "Lê Lợi", 42, "Nam", "Viêm da cơ địa (Chàm)", "Cao su, Phấn hoa", "Thường xuyên ngứa, khô da"),
            ("BN-055", "Hồ Xuân Hương", 30, "Nữ", "Lupus ban đỏ hệ thống (SLE)", "Ánh sáng mặt trời", "Đang dùng Corticoid liều duy trì"),
            ("BN-056", "Trần Hưng Đạo", 50, "Nam", "Bệnh trĩ nội độ 3", "Không", "Thỉnh thoảng đi cầu ra máu tươi"),
            ("BN-057", "Nguyễn Du", 65, "Nam", "Đục thủy tinh thể mắt phải", "Không", "Nhìn mờ, lóa sáng"),
            ("BN-058", "Bà Huyện Thanh Quan", 55, "Nữ", "Rối loạn lo âu lan tỏa, Mất ngủ mạn tính", "Không", "Hay lo lắng, hồi hộp"),
            ("BN-059", "Phùng Hưng", 38, "Nam", "Béo phì độ 2, Ngưng thở khi ngủ", "Không", "Ngủ ngáy to, hay buồn ngủ ban ngày"),
            ("BN-060", "Thạch Sanh", 20, "Nam", "Khỏe mạnh", "Không", "Thanh niên cường tráng, chưa từng ốm đau nặng")
        ]

        insert_query = """
        INSERT INTO patient_records 
        (patient_id, full_name, age, gender, chronic_conditions, allergies, past_history)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            chronic_conditions=VALUES(chronic_conditions), 
            allergies=VALUES(allergies), 
            past_history=VALUES(past_history);
        """
        
        cursor.executemany(insert_query, fake_patients)
        # conn.commit() đã được gọi bên trong block with của Context Manager db_utils
        print(f"=== Đã nạp thành công {cursor.rowcount} hồ sơ bệnh án ===")
        
        # In ra danh sách để QA dễ test
        print("\n[DANH SÁCH MÃ BỆNH NHÂN ĐỂ MÔ PHỎNG QUÉT THẺ]:")
        for bn in fake_patients:
            print(f"- {bn[0]}: {bn[1]} ({bn[2]} tuổi) -> {bn[4]} | Dị ứng: {bn[5]}")

if __name__ == "__main__":
    seed_patient_records()