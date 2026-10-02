# ToolVH

Tool GUI trên Windows để quét text tiếng Anh trong thư mục game, dịch sang tiếng Việt, duyệt bản dịch và tạo/cài bản vá có backup. Phiên bản **0.7.0**. Mã nguồn theo [Apache-2.0](LICENSE).

## Khả năng

- Đọc JSON, CSV/TSV, XML, INI, TXT và phụ đề SRT.
- Godot: đọc/ghi PCK rời không mã hóa v1–v3; đọc CSV/JSON, gettext PO/MO, TSCN và Translation TRES dạng text bên trong hoặc ngoài PCK.
- Unreal Engine: đọc/ghi LOCRES rời v0–v3 hoặc LOCRES không nén trong PAK v1–v7 không mã hóa/không có chữ ký, giữ nguyên namespace, key và hash nguồn; không đổi text của locale khác.
- Đọc Unity TextAsset và bảng Localization StringTable có type tree; ưu tiên nguồn tiếng Anh, bỏ metadata kỹ thuật và đánh dấu mục chưa chắc chắn để duyệt.
- Dịch qua Gemini, Groq, OpenRouter free, API tương thích OpenAI, Ollama hoặc Google Dịch web thử nghiệm.
- Glossary, hướng dẫn văn phong, bảo vệ biến/thẻ định dạng, tự lưu từng lô, xuất/nhập CSV.
- Xác minh SHA-256, tạo backup, cài và khôi phục. Unity Addressables binary catalog v2 và JSON catalog cục bộ được cập nhật CRC/kích thước cùng bundle.
- Chuyển sang game khác để quét ngay, giữ bản Việt hóa và backup của game cũ.
- Dịch theo ngữ cảnh, giữ tên riêng và kiểm tra bản dịch trước khi cài.
- Kiểm tra font, chuẩn hóa Unicode, sửa font bitmap Ori và TMP static SDF một atlas có type tree, có backup riêng.
- Kiểm tra thử đọc/ghi và catalog trước khi dịch; không gọi API nếu dữ liệu nguồn đã đổi hoặc writer không hỗ trợ.
- RPG Maker MV/MZ: adapter JSON database và lệnh sự kiện hiển thị. Ren’Py: source/template RPY một dòng, không thực thi Python.
- Godot 4: Translation RSRC v5/v6 little-endian một resource, không script/external resource; hỗ trợ trong PCK đã đọc được.

Không hỗ trợ tự động mọi engine hoặc mọi bản game. Container thiếu type tree, catalog remote/cache hoặc catalog đóng trong bundle chưa hỗ trợ sẽ cần adapter riêng. Bộ quét và model dịch không bảo đảm mọi câu đúng ngữ cảnh; cần duyệt câu nguồn, bản dịch, font và bố cục trong game.

## Ori and the Will of the Wisps

Adapter Moon nhận diện `TranslatedMessageProvider` bằng MonoScript, assembly và fingerprint schema đã kiểm tra. Đọc đúng trường English trong mỗi message; giữ 20 ngôn ngữ khác, GUID và metadata. Wwise GeneratedSoundBanks, third-party notices, name database và benchmark không được lấy làm text giao diện.

Quét lại bằng 0.6.4 để chọn tự động các trường English. Cấu trúc khác tiếp tục báo thiếu type tree; không đoán bằng byte ASCII. Bản 0.6.4 đã được người dùng xác nhận Việt hóa và hiển thị dấu tiếng Việt hoạt động trong Ori. Bộ kiểm thử xác minh ghi/reopen asset, giữ nguyên object ngoài font và dữ liệu ngôn ngữ khác; kết quả thực tế này áp dụng cho bản game đã thử, không đại diện cho mọi bản phát hành.

## Godot và Unreal Engine

| Engine / định dạng | Quét và cài bản dịch |
|---|---|
| Godot PCK rời v1/v2/v3, không mã hóa | Bật **Quét sâu bundle / PCK**. Locator ghi cả tên member và vị trí text. Cài lại PCK với offset, kích thước, MD5 mới; giữ nguyên asset khác. |
| Godot TSCN | Chỉ lấy `text`, `placeholder_text`, `tooltip_text`; không sửa tên node, đường dẫn, script. Thiếu locale thì đưa vào Cần duyệt. |
| Godot Translation TRES / .translation dạng text | Dịch giá trị trong `messages`, giữ key và locale gốc. |
| Gettext PO/MO UTF-8 | Dịch message đơn; giữ msgid, context, header. Bỏ qua plural, fuzzy, obsolete; MO giữ byte order. |
| Unreal LOCRES rời v0/v1/v2/v3 | Tự đọc khi quét; ưu tiên đường dẫn locale `en`/`en-US`. Giữ hash nguồn để engine không bỏ bản dịch. Chuỗi dùng chung được tách theo key khi chỉ sửa một mục. |

Chọn thư mục game → quét → duyệt nguồn tiếng Anh → dịch thử → đóng game → **Cài vào game**. Tool tạo backup trước khi ghi PCK/LOCRES; **Khôi phục** trả file về đúng byte gốc. Giữ English trong game khi vá bảng English. Mọi provider dịch hiện có dùng được cho các adapter mới.

**Chưa hỗ trợ:** PCK mã hóa/sparse/v4 hoặc nhúng trong EXE; Godot RSCC/OptimizedTranslation, RSRC schema khác và scene binary; Unreal PAK v8+ hoặc LOCRES nén, PAK mã hóa/có chữ ký, IoStore (`.utoc`, `.ucas`) và StringTable/FText trong UASSET. Không tự đổi đuôi hoặc vá byte thô ở các định dạng này. CSV/PO có `.import`/`.remap` được bỏ qua vì engine đọc tài nguyên đã nhập, không đọc file nguồn; báo cáo ghi rõ file chưa hỗ trợ. Tên engine là nhận diện định dạng, không bảo đảm toàn bộ game đã được hỗ trợ.

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

Google Dịch web bảo vệ tên riêng và áp dụng glossary cục bộ; không dùng văn phong và ngữ cảnh project như model AI, nên cần duyệt bản nháp.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m scripts.gui_smoke
.\.venv\Scripts\python.exe -m scripts.gui_api_smoke
.\.venv\Scripts\python.exe -m scripts.gui_switch_game_smoke
.\.venv\Scripts\python.exe -m scripts.gui_terminology_smoke
.\.venv\Scripts\python.exe -m scripts.gui_fonts_smoke
.\.venv\Scripts\python.exe -m scripts.gui_preflight_smoke
```

Kiểm thử dùng dữ liệu tổng hợp và mock API; không cần game thương mại hoặc API key. DPAPI cần tài khoản Windows có quyền mã hóa. GUI được kiểm tra offscreen và xóa dữ liệu tạm sau khi chạy.

## Build EXE

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\Build.ps1
```

Kết quả ở `dist/0.7.0/ToolVH`; giữ toàn bộ thư mục cùng `_internal`. Script tự đọc phiên bản từ `toolvh/__init__.py`, tạo `ToolVH-0.7.0-windows-x64.zip` và file SHA-256 để upload lên GitHub Releases. Dùng `-NoArchive` nếu chỉ muốn build thư mục chạy. Build dùng `packaging/ToolVH.spec`, loại ICU lấy nhầm từ PATH để Qt dùng ICU Windows. Thư mục dist và runtime không được commit vào mã nguồn.

## Đăng GitHub Release

1. Build bằng các lệnh trên. Người tải bản ZIP không cần cài Python.
2. Mở [New release](https://github.com/JunnDung/ToolVH/releases/new), tạo tag khớp phiên bản (ví dụ `v0.7.0`) và chọn commit mã nguồn đã build.
3. Đặt tiêu đề `ToolVH 0.7.0`, ghi thay đổi và giới hạn hỗ trợ.
4. Đính kèm `dist/0.7.0/ToolVH-0.7.0-windows-x64.zip` và `.zip.sha256`, rồi **Publish release**.
5. Người dùng giải nén toàn bộ ZIP, mở `ToolVH/ToolVH.exe`. Không tách EXE khỏi `_internal`.

File **Source code (zip)** do GitHub tự tạo chỉ chứa mã nguồn. Không commit `.venv`, `build`, `dist` vào repo; upload bản chạy ở phần Assets của Release.

## Cấu trúc

- `toolvh/scanner.py`, `formats.py`, `unity.py`: nhận diện, đọc/ghi text theo locator.
- `toolvh/godot.py`, `unreal.py`: PCK, tài nguyên Godot/gettext và LOCRES.
- `toolvh/addressables.py`: đọc catalog và tính/cập nhật CRC payload UnityFS.
- `toolvh/translation.py`: provider, chia lô, glossary, kiểm tra biến.
- `toolvh/model.py`, `patching.py`: project, CSV, staging, backup và cài/khôi phục.
- `toolvh/gui.py`, `settings.py`, `diagnostics.py`: giao diện, cấu hình, báo cáo.
- `toolvh/moon.py`, `terminology.py`: adapter Ori, ngữ cảnh và tên riêng.
- `toolvh/fonts.py`, `bitmap_fonts.py`, `bitmap_bindings.py`, `processes.py`: chẩn đoán/sửa font, tra liên kết English và kiểm tra game đang chạy.
- `tests/`: kiểm thử và bộ tạo dữ liệu tổng hợp tự viết, không chứa asset game.

Xem [CHANGELOG.md](CHANGELOG.md) cho thay đổi phiên bản, [CONTRIBUTING.md](CONTRIBUTING.md) để đóng góp và [THIRD_PARTY.md](THIRD_PARTY.md) cho phụ thuộc. Không đưa asset, text trích xuất hoặc bản vá game thương mại vào repo.

### Dịch theo ngữ cảnh và giữ tên riêng (0.6.4)

Trong Cấu hình, bật **Giữ nguyên tên** (mặc định), thêm tên ở **Giữ thêm tên** (mỗi dòng một tên) và mô tả game trong **Ngữ cảnh game**. Tool bảo vệ tên bằng token trước khi gửi cho mọi provider, bao gồm Google Dịch. **Thuật ngữ** dạng `nguồn = đích` có ưu tiên cao hơn việc giữ tên; dùng khi chủ động muốn Việt hóa một thuật ngữ.

Profile Ori tự giữ các tên như Howl, Horn Beetle, Willow Stone, Wellspring Glades và Spirit Shard. Các game khác chỉ tự nhận diện trường tên có ngữ cảnh rõ ràng; không đoán tên từ chữ viết hoa. Bấm **Xem tên nhận diện** để kiểm tra và bổ sung tên còn thiếu. Một số tên có thể chưa được nhận diện; chất lượng diễn đạt còn phụ thuộc model và cần duyệt trong game.

Bản dịch cũ không tự đổi. Bấm **Kiểm tra bản dịch**, duyệt bộ lọc Có lỗi, bỏ chọn các câu khác và chọn câu cần sửa, rồi dùng **Dịch lại các câu đã chọn** trong Cấu hình. Tool sao lưu project trước khi dịch lại, giữ câu cũ khi dịch thất bại và kiểm tra tên/biến trước khi xuất hoặc cài bản vá. Kiểm tra này phát hiện vi phạm tên/định dạng, không thay thế đánh giá nghĩa hoặc bố cục trong game.

### Kiểm tra và sửa font (0.6.4)

Mở **Báo cáo / Cài đặt → Kiểm tra / sửa font… → Quét font**. Chẩn đoán kiểm tra bộ ký tự tiếng Việt và ký tự trong bản dịch được chọn. Tick font hỗ trợ sửa, chọn TTF/OTF có đủ glyph hoặc để trống để lấy font từ Windows, rồi **Xuất bản vá font…** hoặc **Tạo và cài font**. Đóng game trước khi cài. Font patch có SHA-256 và backup riêng, giữ bản dịch đang cài; **Khôi phục font** theo thứ tự từ mới nhất trước khi khôi phục bản dịch. Project cũ vẫn mở được.

Ori WotW: nhận diện BitmapFont bằng MonoScript/assembly/fingerprint, bổ sung glyph tiếng Việt SDF cho candara, roboto, nyala, sakkalMajalla vào vùng atlas chưa dùng. Chữ gốc, kerning, kích thước atlas và font biểu tượng phím được giữ nguyên. Font nguồn được cân cap-height; style bổ sung có thể khác font gốc và cần kiểm tra trong game. Atlas thiếu chỗ, schema khác hoặc font nguồn thiếu glyph sẽ dừng trước khi ghi game. Bản vá font áp dụng lên trạng thái game hiện tại; không cần dịch lại text.

Hỗ trợ thêm thay TTF/OTF rời và Unity dynamic Font có font data nhúng nếu font mới chứa cả glyph gốc lẫn tiếng Việt. Bitmap/atlas tĩnh khác, TMP dynamic/multi-atlas/thiếu type tree, font trong PCK/PAK/IoStore của Godot/Unreal và engine riêng chưa có phương án sửa chung. Không tuyên bố sửa mọi lỗi font: lỗi encoding, layout, shader, dấu kết hợp và fallback cần chẩn đoán riêng. Không phân phối font Windows hay asset game trong mã nguồn/release. Khi chia sẻ bản vá font tự tạo, kiểm tra giấy phép font đã chọn.

Tool kiểm tra tiến trình có EXE nằm trong thư mục game trước khi cài/khôi phục trên Windows. Nếu game đang chạy, chưa ghi file. Với dấu Unicode kết hợp, dùng **Chuẩn hóa Unicode** (có backup project), quét font lại và cài lại bản dịch đã chuẩn hóa khi cần.

Bản 0.6.4 lần theo MessageBoxLanguageStyles → TextStyleCollection → BitmapFont để báo font được gán cho English. Ori dùng sakkalMajalla cho menu, hội thoại và thông báo; kiểm tra chỉ dựa vào tên font đã bỏ sót font này ở bản cũ. Nếu đã cài bản vá font cũ và còn lỗi, quét font lại rồi tạo/cài bản vá bổ sung; không cần khôi phục hoặc dịch lại text. Glyph được thêm theo mã Unicode đã sắp xếp để khớp hàm tra ký tự của game.

Với font bitmap Ori mặc định, ký tự ngoài Latin còn thiếu được lấy từ font dự phòng Windows khi có (TTC dùng face đầu tiên). Chỉ glyph cần thiết được đưa vào atlas; không đóng gói file font hệ thống trong release. Nếu không có nguồn glyph phù hợp, tool báo lỗi trước khi cài.

### Cài bản dịch với JSON Addressables (0.6.5)

Hỗ trợ catalog JSON cục bộ không có dependency, như bản R.E.P.O. đã kiểm tra. Khi xuất/cài, tool xác minh CRC và kích thước bundle nguồn, cập nhật options của bundle đã dịch và giữ các bảng địa chỉ, key, dependency, hash và options khác. Catalog remote, đóng trong bundle hoặc bundle dùng UnityWebRequest/cache vẫn bị chặn.

Nếu gặp thông báo catalog chưa hỗ trợ ở bản cũ, mở project đã lưu bằng bản mới và xuất/cài lại; không cần dịch lại. Giữ thư mục bản vá chứa `backup/` để khôi phục. Việc kiểm tra dữ liệu sau khi ghi không thay thế kiểm tra font, bố cục và hiển thị thực tế trong game.

### Khả năng cài và adapter mới (0.7.0)

Sau khi chọn các câu nguồn, dùng **Báo cáo / Cài đặt → Kiểm tra khả năng cài**. Tool thử cùng writer được dùng để xuất bản vá, kiểm tra SHA-256 và catalog, không ghi game hoặc gọi API. Bước này cũng chạy tự động trước dịch bằng GUI/CLI. Đạt kiểm tra nghĩa là các vị trí đã chọn có thể đọc/ghi theo adapter; không bảo đảm đã tìm hết text, font đủ glyph hay game sẽ nạp bản vá. Game đang có bản vá cần khôi phục trước khi chuẩn bị bản dịch mới cho chính game đó; chuyển game khác vẫn được.

CLI: `.\.venv\Scripts\python.exe -m toolvh check game.toolvh.json`.

| Adapter mới | Phạm vi và giới hạn |
|---|---|
| TMP static SDF | MonoScript TMPro.TMP_FontAsset của Unity.TextMeshPro.dll; một Texture2D Alpha8/RGBA32 cùng container; có type tree, bảng glyph/character và padding hợp lệ. Bổ sung glyph vào vùng trống, giữ metrics/kerning và glyph gốc. Dynamic/multi-atlas/MSDF, tham chiếu atlas ngoài file và schema khác bị chặn. Chọn font nguồn đủ glyph; style cần kiểm tra trong game. |
| Unreal PAK | v1–v7, index không mã hóa; chỉ sửa LOCRES không nén/không mã hóa, giữ payload member khác và cập nhật header/index/SHA1. Không giải nén asset, không sửa UASSET. Gói có sidecar .sig bị chặn trước quét/xuất/cài. v8+, IoStore, PAK engine riêng cần adapter khác. |
| Godot RSRC | Godot 4 format v5/v6, Translation một resource, không external resource/script class/import-metadata offset. Giữ locale, key, UID và property khác; kiểm tra reopen. RSCC, OptimizedTranslation, plural, scene binary và PCK nhúng EXE chưa hỗ trợ. |
| RPG Maker MV/MZ | Cần nhận diện rpg_core.js/rmmz_core.js; chỉ JSON trong data/: tên/mô tả database, System terms, Map displayName, event 401/405 và choices 102. Bỏ note, ID, đường dẫn, script/plugin command. Nguồn không có locale để ở Cần duyệt; xác nhận English trước khi chọn. |
| Ren’Py | RPY source hoặc template: câu thoại và menu một dòng, old/new của template English. Giữ câu old, speaker, script và cấu trúc. Bỏ Python/init/screen/style/transform, ngôn ngữ khác, chuỗi nhiều dòng/cú pháp ngoài phạm vi; RPA/RPYC chưa hỗ trợ. Cần kiểm tra game nạp lại script đã sửa. |

Quét lại sau khi game cập nhật chỉ giữ bản dịch có nguồn/ngữ cảnh/locale giống nhau và vị trí khớp hoặc khớp duy nhất trong cùng file. Mục trùng hoặc nguồn đã đổi không được tự ghép. Không quét lại dữ liệu đang được vá để coi tiếng Việt là nguồn English.

Adapter mới đã kiểm thử bằng dữ liệu tổng hợp, cài/khôi phục trên thư mục thử nghiệm; chưa xác nhận trên game thương mại tương ứng. R.E.P.O., Ori và BOMBANANA! có kết quả thực tế theo xác nhận của người dùng. Không tuyên bố hỗ trợ mọi game hoặc mọi phiên bản engine.

Nguồn định dạng: [Godot binary resources](https://github.com/godotengine/godot/blob/4.5/core/io/resource_format_binary.cpp), [Unreal FPakInfo](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/PakFile/FPakInfo), [Ren’Py translation](https://www.renpy.org/doc/html/translation.html), [Unity font engine](https://github.com/Unity-Technologies/UnityCsReference/blob/master/Modules/TextCoreFontEngine/Managed/FontEngine.bindings.cs). Bộ đọc/ghi được viết riêng, không kèm code engine, asset game hoặc font Windows.

Các bước còn lại được theo dõi trong [ROADMAP.md](ROADMAP.md).
