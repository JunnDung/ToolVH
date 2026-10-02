# Lộ trình tương thích

Mục tiêu là mở rộng theo định dạng đã kiểm chứng, không cam kết mọi game. Nhận diện engine, đọc text, ghi dữ liệu và game nạp bản vá là bốn kết quả khác nhau.

| Công việc | 0.7.5 | Điều kiện để mở rộng tiếp |
|---|---|---|
| Kiểm tra trước dịch | Thử writer/catalog với câu nguồn và tiếng Việt dài hơn; SHA-256; báo mục chưa chọn/file chưa trích xuất | Lần theo tài nguyên runtime thực sự được game nạp và kiểm tra layout/font trong game |
| TextMeshPro | Static SDF một atlas có type tree | Fixture và game cho dynamic/fallback/multi-atlas, shader khác và atlas external |
| Unreal PAK | LOCRES không nén, v1–7 không mã hóa/có chữ ký | Versioned fixtures cho nén, v8+, mount/patch priority và kiểm thử game |
| Godot binary | Translation RSRC Godot 4 v5/v6 trong/ngoài PCK | RSCC compression, OptimizedTranslation, scene binary, plural và PCK embedded |
| RPG Maker | MV/MZ database và text command JSON | Game thực tế, speaker/event context và biến plugin; định dạng VX/Ace riêng |
| Ren’Py | RPY thoại nhiều dòng, thuộc tính, extend, menu có điều kiện và monologue theo khối | Raw/backtick strings, monologue none, screen UI, archive RPA, RPYC và kiểm tra compile/load với engine |
| IoStore/UASSET | Chưa hỗ trợ | Fixtures theo phiên bản UE, package store và dependency graph, công cụ đóng gói tương ứng |
| Engine riêng | Adapter theo format/game đã kiểm chứng | Schema, nguồn English, phương thức ghi/override, fonts và bản game mẫu |
| Game cập nhật | Giữ bản dịch khớp duy nhất; chặn SHA khác | Đối chiếu game build/Steam manifest, migration UI và patch journal khi mất điện |
| Dịch không mất phí API | Google Dịch web có cache/project và chia đoạn; Ollama local; không tự chuyển sang API trả phí | Chất lượng model local, endpoint web bị giới hạn; không cam kết miễn phí vô hạn |
| Chất lượng dịch | Ngữ cảnh gần, thoại Ren’Py cùng label, glossary, tên người nói khai báo rõ và token | Plural/gender/ICU riêng theo engine, đo layout, QA thủ công theo màn hình |

Tiêu chí mỗi adapter: chỉ sửa vị trí được chọn; giữ key/metadata/tài nguyên khác; reopen đúng; cài/khôi phục đúng byte; dữ liệu sai/mã hóa không được ghi; sau đó kiểm tra menu, hội thoại, font và lưu game trên bản thương mại cụ thể. Các fixture hiện tại là dữ liệu tổng hợp tự tạo, không chứa asset thương mại.
