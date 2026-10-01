# Đóng góp cho ToolVH

Thiết lập môi trường và chạy kiểm thử theo README. Pull request nên mô tả lỗi, hành vi sau sửa và cách kiểm tra.

- Không commit API key, cấu hình cá nhân, log, đường dẫn người dùng hoặc project dịch game thật.
- Không đưa asset, bundle, catalog, bản vá hay text trích xuất từ game thương mại vào repo. Dùng dữ liệu tổng hợp tự tạo như `tests/synthetic_addressables.py`.
- Adapter mới cần kiểm tra đọc → sửa → ghi → đọc lại, giữ ID/biến/thẻ và xác minh checksum nếu định dạng có kiểm tra.
- Thay đổi cài/khôi phục phải giữ backup, xác minh file trước khi ghi và kiểm thử hoàn tác khi lỗi.
- Kiểm thử API dùng mock hoặc câu mẫu tổng hợp; không gọi dịch vụ trả phí trong bộ kiểm thử.
- Đóng góp mã nguồn theo giấy phép Apache-2.0 của dự án.
