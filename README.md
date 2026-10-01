# ToolVH

Tool GUI trên Windows để quét text tiếng Anh trong thư mục game, dịch sang tiếng Việt, duyệt bản dịch và tạo/cài bản vá có backup. Phiên bản **0.6.0**. Mã nguồn theo [Apache-2.0](LICENSE).

## Khả năng

- Đọc JSON, CSV/TSV, XML, INI, TXT và phụ đề SRT.
- Godot: đọc/ghi PCK rời không mã hóa v1–v3; đọc CSV/JSON, gettext PO/MO, TSCN và Translation TRES dạng text bên trong hoặc ngoài PCK.
- Unreal Engine: đọc/ghi LOCRES rời v0–v3, giữ nguyên namespace, key và hash nguồn; không đổi text của locale khác.
- Đọc Unity TextAsset và bảng Localization StringTable có type tree; ưu tiên nguồn tiếng Anh, bỏ metadata kỹ thuật và đánh dấu mục chưa chắc chắn để duyệt.
- Dịch qua Gemini, Groq, OpenRouter free, API tương thích OpenAI, Ollama hoặc Google Dịch web thử nghiệm.
- Glossary, hướng dẫn văn phong, bảo vệ biến/thẻ định dạng, tự lưu từng lô, xuất/nhập CSV.
- Xác minh SHA-256, tạo backup, cài và khôi phục. Unity Addressables binary catalog v2 local được cập nhật CRC cùng bundle.
- Chuyển sang game khác để quét ngay, giữ bản Việt hóa và backup của game cũ.

Không hỗ trợ tự động mọi engine hoặc mọi bản game. Container thiếu type tree, catalog JSON/remote/cache chưa hỗ trợ sẽ cần adapter riêng. Bộ quét và model dịch không bảo đảm mọi câu đúng ngữ cảnh; cần duyệt câu nguồn, bản dịch, font và bố cục trong game.

## Godot và Unreal Engine

| Engine / định dạng | Quét và cài bản dịch |
|---|---|
| Godot PCK rời v1/v2/v3, không mã hóa | Bật **Quét sâu bundle / PCK**. Locator ghi cả tên member và vị trí text. Cài lại PCK với offset, kích thước, MD5 mới; giữ nguyên asset khác. |
| Godot TSCN | Chỉ lấy `text`, `placeholder_text`, `tooltip_text`; không sửa tên node, đường dẫn, script. Thiếu locale thì đưa vào Cần duyệt. |
| Godot Translation TRES / .translation dạng text | Dịch giá trị trong `messages`, giữ key và locale gốc. |
| Gettext PO/MO UTF-8 | Dịch message đơn; giữ msgid, context, header. Bỏ qua plural, fuzzy, obsolete; MO giữ byte order. |
| Unreal LOCRES rời v0/v1/v2/v3 | Tự đọc khi quét; ưu tiên đường dẫn locale `en`/`en-US`. Giữ hash nguồn để engine không bỏ bản dịch. Chuỗi dùng chung được tách theo key khi chỉ sửa một mục. |

Chọn thư mục game → quét → duyệt nguồn tiếng Anh → dịch thử → đóng game → **Cài vào game**. Tool tạo backup trước khi ghi PCK/LOCRES; **Khôi phục** trả file về đúng byte gốc. Giữ English trong game khi vá bảng English. Mọi provider dịch hiện có dùng được cho các adapter mới.

**Chưa hỗ trợ:** PCK mã hóa/sparse/v4 hoặc nhúng trong EXE; Godot RSRC/RSCC/OptimizedTranslation và scene binary; Unreal PAK/IoStore (`.utoc`, `.ucas`) và StringTable/FText trong UASSET. Không tự đổi đuôi hoặc vá byte thô ở các định dạng này. CSV/PO có `.import`/`.remap` được bỏ qua vì engine đọc tài nguyên đã nhập, không đọc file nguồn; báo cáo ghi rõ file chưa hỗ trợ. Tên engine là nhận diện định dạng, không bảo đảm toàn bộ game đã được hỗ trợ.

Bộ kiểm thử có dữ liệu tổng hợp cho các phiên bản PCK/LOCRES, chuỗi dùng chung, Unicode, gettext, cài/khôi phục, file sai offset/MD5 và gói mã hóa. Chưa xác nhận trên game Godot/Unreal thương mại; font và việc game nạp đúng file phải kiểm tra thực tế.

Tham khảo định dạng: [Godot PCK reader](https://github.com/godotengine/godot/blob/4.5/core/io/file_access_pack.cpp), [Godot gettext](https://docs.godotengine.org/en/stable/tutorials/i18n/localization_using_gettext.html), [UnrealLocres format implementation](https://github.com/akintos/UnrealLocres/blob/master/LocresLib/LocresFile.cs). Adapter được viết riêng, không kèm mã thư viện hoặc asset game.

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

Kết quả ở `dist/0.6.0/ToolVH`; giữ toàn bộ thư mục cùng `_internal`. Build dùng `packaging/ToolVH.spec`, loại ICU lấy nhầm từ PATH để Qt dùng ICU Windows. Thư mục dist và runtime không được commit vào mã nguồn.

## Cấu trúc

- `toolvh/scanner.py`, `formats.py`, `unity.py`: nhận diện, đọc/ghi text theo locator.
- `toolvh/godot.py`, `unreal.py`: PCK, tài nguyên Godot/gettext và LOCRES.
- `toolvh/addressables.py`: đọc catalog và tính/cập nhật CRC payload UnityFS.
- `toolvh/translation.py`: provider, chia lô, glossary, kiểm tra biến.
- `toolvh/model.py`, `patching.py`: project, CSV, staging, backup và cài/khôi phục.
- `toolvh/gui.py`, `settings.py`, `diagnostics.py`: giao diện, cấu hình, báo cáo.
- `tests/`: kiểm thử và bộ tạo dữ liệu tổng hợp tự viết, không chứa asset game.

Xem [CONTRIBUTING.md](CONTRIBUTING.md) để đóng góp và [THIRD_PARTY.md](THIRD_PARTY.md) cho phụ thuộc. Không đưa asset, text trích xuất hoặc bản vá game thương mại vào repo.
