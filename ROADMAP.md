# Lộ trình tương thích

Mục tiêu là mở rộng theo định dạng đã kiểm chứng, không cam kết mọi game. Nhận diện engine, đọc text, ghi dữ liệu và game nạp bản vá là bốn kết quả khác nhau.

| Công việc | 0.7.0 | Điều kiện để mở rộng tiếp |
|---|---|---|
| Kiểm tra trước dịch | Có thử writer/catalog, SHA-256, không gọi API khi bị chặn | Báo cáo mức bao phủ theo tài nguyên runtime và thử dịch dài hơn nguồn |
| TextMeshPro | Static SDF một atlas có type tree | Fixture và game cho dynamic/fallback/multi-atlas, shader khác và atlas external |
| Unreal PAK | LOCRES không nén, v1–7 không mã hóa/có chữ ký | Versioned fixtures cho nén, v8+, mount/patch priority và kiểm thử game |
| Godot binary | Translation RSRC Godot 4 v5/v6 trong/ngoài PCK | RSCC compression, OptimizedTranslation, scene binary, plural và PCK embedded |
| RPG Maker | MV/MZ database và text command JSON | Game thực tế, speaker/event context và biến plugin; định dạng VX/Ace riêng |
| Ren’Py | Source/template RPY một dòng | Parser nhiều dòng, archive RPA, RPYC và kiểm tra compile/load với engine |
| IoStore/UASSET | Chưa hỗ trợ | Fixtures theo phiên bản UE, package store và dependency graph, công cụ đóng gói tương ứng |
| Engine riêng | Adapter theo format/game đã kiểm chứng | Schema, nguồn English, phương thức ghi/override, fonts và bản game mẫu |
| Game cập nhật | Giữ bản dịch khớp duy nhất; chặn SHA khác | Đối chiếu game build/Steam manifest, migration UI và patch journal khi mất điện |
| Chất lượng dịch | Ngữ cảnh gần, glossary, tên riêng, token | Plural/gender/ICU riêng theo engine, đo layout, QA thủ công theo màn hình |

Tiêu chí mỗi adapter: chỉ sửa vị trí được chọn; giữ key/metadata/tài nguyên khác; reopen đúng; cài/khôi phục đúng byte; dữ liệu sai/mã hóa không được ghi; sau đó kiểm tra menu, hội thoại, font và lưu game trên bản thương mại cụ thể. Các fixture hiện tại là dữ liệu tổng hợp tự tạo, không chứa asset thương mại.
