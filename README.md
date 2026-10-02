# ToolVH

Ứng dụng GUI trên Windows giúp quét text tiếng Anh trong thư mục game, dịch sang tiếng Việt, duyệt bản dịch và cài bản vá có sao lưu. Phiên bản hiện tại: **0.7.0**. Mã nguồn được cấp phép theo [Apache-2.0](LICENSE).

ToolVH hỗ trợ nhiều định dạng, nhưng **chưa thể Việt hóa mọi game**. Khả năng quét, cài bản dịch và sửa font phụ thuộc cấu trúc dữ liệu của từng game; cần kiểm tra kết quả trong game trước khi chia sẻ bản vá.

## Tính năng chính

- Quét dữ liệu, ưu tiên text tiếng Anh và đưa các mục chưa xác định rõ ngôn ngữ vào nhóm cần duyệt.
- Dịch bằng Gemini, Groq, OpenRouter free, API tương thích OpenAI, Ollama hoặc Google Dịch web thử nghiệm.
- Cung cấp ngữ cảnh game, văn phong và bảng thuật ngữ; bảo vệ tên riêng, biến và thẻ định dạng.
- Chỉnh sửa bản dịch, dịch lại các câu đã chọn, tự lưu theo lô và xuất/nhập CSV.
- Kiểm tra khả năng đọc/ghi và catalog trước khi dịch; xác minh SHA-256 trước khi tạo/cài bản vá.
- Sao lưu, cài và khôi phục bản dịch; chuyển sang game khác mà vẫn giữ bản vá và backup của game cũ.
- Kiểm tra ký tự còn thiếu, chuẩn hóa Unicode và sửa một số loại font với backup riêng.

## Phạm vi hỗ trợ

| Engine / dữ liệu | Phạm vi hiện tại |
|---|---|
| File text | JSON, CSV/TSV, XML, INI, TXT và phụ đề SRT theo cấu trúc bộ đọc hỗ trợ. |
| Unity | TextAsset, Localization StringTable có type tree và adapter `TranslatedMessageProvider` của Ori and the Will of the Wisps. Hỗ trợ cập nhật Addressables binary catalog v2 và JSON catalog cục bộ trong phạm vi writer hiện có. |
| Godot | PCK rời v1–v3 không mã hóa; CSV/JSON, gettext PO/MO UTF-8, trường text của TSCN, Translation TRES dạng text và Godot 4 Translation RSRC v5/v6 little-endian một resource. |
| Unreal Engine | LOCRES rời v0–v3 hoặc LOCRES không nén trong PAK v1–v7 không mã hóa, không có chữ ký. Giữ namespace, key và hash nguồn. |
| RPG Maker MV/MZ | JSON database trong `data/` khi nhận diện được core engine; tên, mô tả, thuật ngữ và lệnh sự kiện hiển thị thoại/lựa chọn. Không sửa script, plugin command hoặc trường note. |
| Ren’Py | Source/template RPY: thoại và menu một dòng, cặp old/new của template English. Không thực thi Python hoặc sửa logic game. |

**Các giới hạn đáng chú ý:**

- Unity thiếu type tree hoặc schema chưa nhận diện; Addressables remote/cache, catalog đóng trong bundle và cấu trúc dependency chưa hỗ trợ có thể bị chặn.
- Godot PCK mã hóa/sparse/v4 hoặc nhúng trong EXE; RSCC, OptimizedTranslation, scene binary và RSRC ngoài schema đã hỗ trợ. PO/MO chưa hỗ trợ đầy đủ plural; PO fuzzy/obsolete được bỏ qua. File nguồn có `.import`/`.remap` có thể bị bỏ qua vì game đọc tài nguyên đã nhập.
- Unreal PAK v8+, gói nén/mã hóa/có chữ ký, IoStore (`.utoc`, `.ucas`) và text trong UASSET chưa hỗ trợ cài bản dịch.
- Ren’Py RPA/RPYC, chuỗi nhiều dòng và cú pháp ngoài phạm vi bộ đọc chưa hỗ trợ.

Tên engine được nhận diện không có nghĩa toàn bộ text trong game đã được tìm thấy. Các mục thiếu thông tin locale cần được xác nhận là tiếng Anh trước khi dịch.

BOMBANANA!, Ori and the Will of the Wisps và R.E.P.O. đã có kết quả sử dụng thực tế theo xác nhận của người dùng, trên các bản game đã thử. Các adapter Godot, Unreal, RPG Maker và Ren’Py được kiểm thử bằng dữ liệu tổng hợp; chưa xác nhận trên game thương mại tương ứng.

## Cài đặt và chạy

### Bản đóng gói Windows

Nếu có bản Windows tại [Releases](https://github.com/JunnDung/ToolVH/releases), tải ZIP, giải nén toàn bộ và mở `ToolVH/ToolVH.exe`. Giữ EXE cùng thư mục `_internal`; bản đóng gói không cần cài Python.

### Chạy từ mã nguồn

Môi trường kiểm thử: Windows 10/11 x64 và Python 3.12. Mở PowerShell tại thư mục mã nguồn rồi chạy:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m toolvh gui
```

Sau khi cài phụ thuộc, có thể mở bằng `Start-ToolVH.cmd`.

## Cách Việt hóa game

1. Chọn thư mục game và bấm **Quét dữ liệu**. Bật **Quét sâu bundle / PCK** nếu cần đọc dữ liệu đóng gói.
2. Duyệt câu nguồn, chọn các mục tiếng Anh cần dịch và lưu project ở thư mục làm việc riêng.
3. Trong **Cấu hình**, chọn dịch vụ, nhập URL/model/key phù hợp rồi **Kiểm tra kết nối**. Bổ sung ngữ cảnh, tên riêng và thuật ngữ của game.
4. Dùng **Kiểm tra khả năng cài** trong **Báo cáo / Cài đặt**, rồi **Dịch thử 10 câu** trước khi dịch nhiều. Kiểm tra khả năng cài cũng chạy tự động trước khi dịch.
5. Duyệt bản dịch, chạy **Kiểm tra bản dịch**, sửa các câu có lỗi và kiểm tra font nếu cần.
6. Lưu project, đóng game rồi bấm **Cài vào game**, hoặc **Xuất bản vá…** để lưu bản vá riêng. Mở game kiểm tra font, bố cục và ngữ cảnh.

Nếu bản vá thay bảng tiếng Anh, giữ lựa chọn **English** trong game. Kiểm tra khả năng cài không ghi vào game hoặc gọi API; kết quả đạt chỉ xác nhận các vị trí đã chọn có thể đọc/ghi bằng adapter, chưa bảo đảm game sẽ nạp bản vá hoặc hiển thị đúng.

Giữ project và thư mục bản vá chứa `backup/`. **Khôi phục** trả các file đã vá về bản gốc, vẫn giữ bản dịch trong project. Nếu đã cài bản vá font, khôi phục font từ bản mới nhất trước khi khôi phục bản dịch.

Để Việt hóa game khác, chọn thư mục mới rồi quét; không cần khôi phục game cũ. Khi quét lại chính game đang có bản dịch đã cài, cần khôi phục trước để không lấy tiếng Việt làm câu nguồn. Tool chặn cài khi dữ liệu game khác phiên bản lúc quét; bản dịch chỉ được ghép lại khi nguồn, ngữ cảnh và vị trí phù hợp, không tự ghép mục mơ hồ. CSV nhập phải khớp ID và câu nguồn.

## Dịch vụ dịch

| Dịch vụ | Cấu hình |
|---|---|
| Google AI Studio / Gemini | Tạo key tại [AI Studio](https://aistudio.google.com/api-keys), tải danh sách model, chọn model rồi kiểm tra kết nối. |
| Groq | Key tại [Groq Console](https://console.groq.com/keys); dùng endpoint preset của tool. |
| OpenRouter free | Key tại [OpenRouter](https://openrouter.ai/settings/keys); preset chỉ chấp nhận model `:free` hoặc `openrouter/free`. |
| API tương thích OpenAI | Nhập base URL, model và key theo nhà cung cấp. |
| Ollama local | Cài Ollama, tải model và chạy dịch vụ; URL mặc định `http://localhost:11434`, không cần key cho dịch vụ local. |
| Google Dịch web | Không cần key/model; tính năng thử nghiệm, endpoint có thể bị giới hạn hoặc thay đổi. |

Hạn mức và chi phí phụ thuộc nhà cung cấp và tài khoản; tool không bảo đảm API miễn phí hoặc tự bật billing. Ollama chạy trên máy không cần mua API, nhưng tốc độ và chất lượng phụ thuộc model, RAM và GPU.

API nhận text được chọn để dịch. Key được giữ trong phiên hoặc mã hóa bằng Windows DPAPI nếu chọn lưu. Không đưa key, cấu hình cá nhân, project hay dữ liệu trích xuất từ game vào Git.

Google Dịch web áp dụng bảo vệ tên và glossary cục bộ, nhưng không dùng ngữ cảnh/văn phong project như model AI. Với mọi dịch vụ, cần duyệt bản dịch trước khi cài.

## Ngữ cảnh và tên riêng

Trong **Cấu hình**, giữ bật **Giữ nguyên tên nhân vật, địa danh, vật phẩm và kỹ năng**, mô tả game trong **Ngữ cảnh game**, thêm tên còn thiếu ở **Giữ thêm tên** (mỗi dòng một tên). Dùng **Xem tên nhận diện** để kiểm tra danh sách được bảo vệ; tool không tự nhận diện đầy đủ mọi tên riêng.

**Thuật ngữ** dùng dạng `nguồn = đích` và có ưu tiên cao hơn việc giữ tên. Chỉ đặt bản dịch cho tên riêng khi chủ động muốn Việt hóa tên đó. Các bản dịch cũ không tự thay đổi khi sửa cấu hình; chọn câu cần sửa rồi dùng **Dịch lại các câu đã chọn**. Tool sao lưu project trước khi dịch lại và giữ câu cũ nếu dịch thất bại.

Kiểm tra bản dịch phát hiện lỗi tên, biến và định dạng; không thay thế việc đánh giá nghĩa, giọng thoại hoặc bố cục trong game.

## Kiểm tra và sửa font

Mở **Báo cáo / Cài đặt → Kiểm tra / sửa font… → Quét font**. Chọn font hỗ trợ sửa, chọn TTF/OTF đủ ký tự hoặc để trống để lấy font Windows, rồi **Xuất bản vá font…** hoặc **Tạo và cài font**. Đóng game trước khi cài; giữ backup font riêng. Có thể dùng **Chuẩn hóa Unicode**, quét font lại và cài lại bản dịch khi cần.

Phạm vi sửa hiện tại gồm TTF/OTF rời, Unity dynamic Font có dữ liệu font nhúng, font bitmap Ori đã nhận diện và TMP static SDF một atlas có type tree phù hợp. TMP dynamic/multi-atlas/MSDF, atlas tham chiếu ngoài file và font trong PCK/PAK/IoStore chưa có phương án sửa chung. Font nguồn thiếu glyph, atlas thiếu chỗ hoặc schema không hỗ trợ sẽ bị chặn.

Không bảo đảm sửa mọi lỗi font: encoding, layout, shader và fallback cần chẩn đoán riêng. Kiểm tra giấy phép font trước khi chia sẻ bản vá; không đưa font Windows hoặc asset game vào mã nguồn.

## Phát triển

Chạy kiểm thử từ môi trường đã cài phụ thuộc:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m scripts.gui_smoke
.\.venv\Scripts\python.exe -m scripts.gui_api_smoke
.\.venv\Scripts\python.exe -m scripts.gui_switch_game_smoke
.\.venv\Scripts\python.exe -m scripts.gui_terminology_smoke
.\.venv\Scripts\python.exe -m scripts.gui_fonts_smoke
.\.venv\Scripts\python.exe -m scripts.gui_preflight_smoke
```

Kiểm thử dùng dữ liệu tổng hợp và mock API; không cần game thương mại hoặc API key. Kiểm thử GUI chạy offscreen; kiểm thử DPAPI cần môi trường Windows.

Build bản Windows sau khi tạo `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\Build.ps1
```

Script đọc phiên bản từ `toolvh/__init__.py`, tạo thư mục chạy tại `dist/<phiên bản>/ToolVH`, ZIP và file SHA-256. Giữ toàn bộ thư mục chạy cùng `_internal`. Dùng `-NoArchive` nếu chỉ cần thư mục chạy. Không commit `.venv`, `build` hoặc `dist`.

Xem [CHANGELOG](CHANGELOG.md) để biết thay đổi, [ROADMAP](ROADMAP.md) cho lộ trình, [CONTRIBUTING](CONTRIBUTING.md) để đóng góp và [THIRD_PARTY](THIRD_PARTY.md) cho thông tin phụ thuộc. Không đưa asset, text trích xuất hoặc bản vá game thương mại vào repo.
