# Thay đổi phiên bản

## 0.6.4

- Sửa lỗi thiếu dấu tiếng Việt ở menu và hội thoại Ori: nhận diện font `sakkalMajalla` bị bỏ sót trước đó.
- Lần theo `MessageBoxLanguageStyles` → `TextStyleCollection` → `BitmapFont` để báo và ưu tiên font của bảng English.
- Bổ sung glyph SDF vào chỗ trống atlas; giữ chữ gốc, kerning, kích thước atlas và font biểu tượng. Dùng font dự phòng Windows cho ký tự ngoài Latin khi có nguồn phù hợp.
- Thêm cửa sổ kiểm tra/sửa font, chuẩn hóa Unicode và cài/khôi phục bản vá font với backup riêng. Kiểm tra game đang chạy trước khi ghi file.
- Bảo vệ tên nhân vật, địa danh, vật phẩm và khu vực; hỗ trợ ngữ cảnh game, thuật ngữ, kiểm tra và dịch lại câu đã chọn.
- Đọc đúng trường English của Ori `TranslatedMessageProvider`, giữ nguyên các ngôn ngữ khác và metadata; bỏ qua dữ liệu âm thanh và thông báo thư viện khi quét.
- Thêm kiểm thử adapter Ori, tên riêng, font và giao diện. 137 kiểm thử tự động đạt; bản EXE Windows đã qua kiểm tra khởi động.
- Người dùng đã xác nhận bản Việt hóa và dấu tiếng Việt hiển thị được trong Ori trên bản game đã thử.

Font trong TextMeshPro, container Godot/Unreal và engine riêng vẫn cần adapter riêng. Không kèm font Windows, asset hoặc bản vá của game trong mã nguồn và bản phát hành.
