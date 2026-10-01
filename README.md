# ToolVH

Tool GUI trên Windows để quét text tiếng Anh trong thư mục game, dịch sang tiếng Việt, duyệt bản dịch và tạo/cài bản vá có backup. Phiên bản **0.5.5**. Mã nguồn theo [Apache-2.0](LICENSE).

## Khả năng

- Đọc JSON, CSV/TSV, XML, INI, TXT và phụ đề SRT.
- Đọc Unity TextAsset và bảng Localization StringTable có type tree; ưu tiên nguồn tiếng Anh, bỏ metadata kỹ thuật và đánh dấu mục chưa chắc chắn để duyệt.
- Dịch qua Gemini, Groq, OpenRouter free, API tương thích OpenAI, Ollama hoặc Google Dịch web thử nghiệm.
- Glossary, hướng dẫn văn phong, bảo vệ biến/thẻ định dạng, tự lưu từng lô, xuất/nhập CSV.
- Xác minh SHA-256, tạo backup, cài và khôi phục. Unity Addressables binary catalog v2 local được cập nhật CRC cùng bundle.
- Chuyển sang game khác để quét ngay, giữ bản Việt hóa và backup của game cũ.

Không hỗ trợ tự động mọi engine hoặc mọi bản game. Container thiếu type tree, catalog JSON/remote/cache chưa hỗ trợ sẽ cần adapter riêng. Bộ quét và model dịch không bảo đảm mọi câu đúng ngữ cảnh; cần duyệt câu nguồn, bản dịch, font và bố cục trong game.

## Cài từ mã nguồn

Windows 10/11 x64, Python 3.12 được dùng để kiểm thử.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m toolvh gui
```

Sau khi cài phụ thuộc, có thể chạy `Start-ToolVH.cmd`.

## Quy trình

1. Chọn thư mục game và Quét dữ liệu; bật quét sâu bundle nếu cần.
2. Duyệt các mục tiếng Anh và mục Cần duyệt. Lưu project ở thư mục làm việc riêng.
3. Chọn dịch vụ, cấu hình model/key rồi Kiểm tra kết nối. Dịch thử 10 câu trước khi dịch nhiều.
4. Sửa thuật ngữ/văn phong, lưu project, đóng game rồi Cài vào game.
5. Giữ thư mục backup được ghi trong project. Khôi phục trả các file đã vá về bản gốc, không xóa bản dịch trong project.

Để chuyển game: Chọn game → chọn thư mục mới → Quét dữ liệu. Khôi phục chỉ cần khi quét lại chính game đã cài bản dịch từ project đang mở. Nếu có thay đổi chưa lưu, tool cho chọn lưu trước khi chuyển.

Khi bản dịch thay bảng tiếng Anh, chọn English trong game. CSV nhập phải khớp ID và câu nguồn. Bản vá sẽ bị chặn nếu file game khác phiên bản lúc quét.

## Dịch vụ và cấu hình

| Dịch vụ | Cấu hình |
|---|---|
| Gemini | Tạo key ở [AI Studio](https://aistudio.google.com/api-keys), tải model và kiểm tra kết nối |
| Groq | Key ở [Groq Console](https://console.groq.com/keys), endpoint preset cố định |
| OpenRouter free | Key ở [OpenRouter](https://openrouter.ai/settings/keys); preset chỉ chấp nhận model `:free` hoặc `openrouter/free` |
| API tương thích OpenAI | URL/model/key do người dùng cấu hình theo nhà cung cấp |
| Ollama | Cài Ollama và tải model; URL mặc định `http://localhost:11434`, không cần key local |
| Google Dịch web | Không key/model; endpoint thử nghiệm có thể bị giới hạn hoặc thay đổi |

API nhận text được chọn để dịch. Key giữ trong phiên, hoặc mã hóa bằng Windows DPAPI nếu chọn lưu. Không commit key/cấu hình/project cá nhân. Tool không tự bật billing, mua credits hoặc xác minh gói miễn phí của tài khoản; hạn mức phụ thuộc dịch vụ.

Ollama dùng tối đa 5 câu/lô, schema JSON, ID ngắn ánh xạ lại project, tắt thinking, context 8192, temperature 0, tối đa 4096 token đầu ra và chờ ít nhất 300 giây. Phản hồi thiếu/trùng ID hoặc bị cắt không được lưu. Model nhỏ vẫn cần duyệt văn phong/tên riêng.

Google Dịch web không dùng glossary, văn phong và ngữ cảnh project; phù hợp bản nháp cần duyệt.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m scripts.gui_smoke
.\.venv\Scripts\python.exe -m scripts.gui_api_smoke
.\.venv\Scripts\python.exe -m scripts.gui_switch_game_smoke
```

Kiểm thử dùng dữ liệu tổng hợp và mock API; không cần game thương mại hoặc API key. DPAPI cần tài khoản Windows có quyền mã hóa. GUI được kiểm tra offscreen và xóa dữ liệu tạm sau khi chạy.

## Build EXE

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\Build.ps1
```

Kết quả ở `dist/0.5.5/ToolVH`; giữ toàn bộ thư mục cùng `_internal`. Build dùng `packaging/ToolVH.spec`, loại ICU lấy nhầm từ PATH để Qt dùng ICU Windows. Thư mục dist và runtime không được commit vào mã nguồn.

## Cấu trúc

- `toolvh/scanner.py`, `formats.py`, `unity.py`: nhận diện, đọc/ghi text theo locator.
- `toolvh/addressables.py`: đọc catalog và tính/cập nhật CRC payload UnityFS.
- `toolvh/translation.py`: provider, chia lô, glossary, kiểm tra biến.
- `toolvh/model.py`, `patching.py`: project, CSV, staging, backup và cài/khôi phục.
- `toolvh/gui.py`, `settings.py`, `diagnostics.py`: giao diện, cấu hình, báo cáo.
- `tests/`: kiểm thử và bộ tạo dữ liệu tổng hợp tự viết, không chứa asset game.

Xem [CONTRIBUTING.md](CONTRIBUTING.md) để đóng góp và [THIRD_PARTY.md](THIRD_PARTY.md) cho phụ thuộc. Không đưa asset, text trích xuất hoặc bản vá game thương mại vào repo.
