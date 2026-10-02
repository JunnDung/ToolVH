# Thay đổi phiên bản

## 0.7.0

- Kiểm tra thử đọc/ghi, nguồn SHA-256 và catalog trước khi dịch (GUI/CLI); thêm nút Kiểm tra khả năng cài và CLI check.
- TMP static SDF một atlas: chẩn đoán glyph, bổ sung ký tự, giữ glyph/kerning/pixel gốc và kiểm tra reopen; từ chối schema/font chưa hỗ trợ.
- Unreal PAK v1–7: đọc/ghi LOCRES không nén trong index không mã hóa; giữ payload khác, cập nhật header/index/SHA1; chặn sidecar chữ ký cả lúc cài.
- Godot 4 Translation RSRC v5/v6: nguồn/locale, key và UID; hỗ trợ trong PCK; không đoán OptimizedTranslation/RSCC/scene.
- Adapter RPG Maker MV/MZ và Ren’Py RPY source/template, giữ script, metadata, command và tên riêng.
- Bảo vệ biến Ren’Py có conversion và escape code RPG Maker.
- Quét lại giữ bản dịch theo nguồn/ngữ cảnh/locale khớp duy nhất khi vị trí thay đổi; mục trùng hoặc đổi nguồn cần duyệt lại.
- 156 kiểm thử tự động đạt; thêm kiểm tra GUI preflight chặn API khi nguồn đổi. Adapter mới cần kiểm tra trên game thương mại.

## 0.6.5

- Sửa lỗi chặn xuất/cài bản dịch R.E.P.O. do catalog Addressables dạng JSON cục bộ.
- Cập nhật đúng CRC và kích thước bundle đã dịch; giữ options khác và các record không liên quan.
- Kiểm tra nguồn trước khi xuất, kiểm tra catalog trước khi cài, hỗ trợ cài lặp và khôi phục nguyên trạng. Tiếp tục chặn remote/cache và catalog chưa hỗ trợ.
- Thêm kiểm thử JSON catalog và cài/khôi phục; 140 kiểm thử tự động đạt. Đã xuất và cài 603 câu từ project R.E.P.O.; người dùng đã xác nhận game hoạt động tốt.

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
