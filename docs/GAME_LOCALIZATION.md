# Tìm text game và dịch đúng ngữ cảnh

Đối chiếu tài liệu engine và kiểm tra cấu trúc thư mục 8 game đang cài ngày 04/10/2026. Đây là hướng dẫn nhận diện tài nguyên, không phải xác nhận đã dịch/cài thành công các game này. Không đưa asset hoặc text game thương mại vào repo.

## Tìm ở đâu

| Cấu trúc | Nơi cần kiểm tra | ToolVH hiện xử lý được gì |
|---|---|---|
| Unity thông thường | `*_Data/resources.assets`, `sharedassets*.assets`, `StreamingAssets` | TextAsset, StringTable đã xác nhận locale, một số MonoBehaviour có type tree và adapter riêng |
| Unity Addressables | `StreamingAssets/aa`, catalog và bundle có bảng English | Đọc bảng được hỗ trợ; khi ghi cần cập nhật bundle/catalog cùng nhau |
| Unity packed player | `*_Data/data.unity3d` | Đọc từng asset qua stream trong UnityFS được hỗ trợ; không nhận mọi chuỗi code là text |
| Unreal | `Content/Localization`, `.locres` trong `Content/Paks/*.pak`; `.utoc/.ucas` | LOCRES rời và PAK được hỗ trợ; IoStore/FText trong asset còn thiếu adapter |
| Godot | `.pck`, `.translation`, `.po/.mo`, `.tscn/.tres`, CSV nguồn | Các adapter hiện có; import/remap và tài nguyên biên dịch phải xử lý đúng đích runtime |
| Ren’Py | `game/*.rpy`, `game/tl/<language>`, `.rpa/.rpyc` | Script RPY hỗ trợ lời thoại/lựa chọn và giữ tên người nói; RPA/RPYC chưa đọc/ghi |
| RPG Maker MV/MZ | `www/data` hoặc `data`: `Map*.json`, `CommonEvents.json`, `Actors.json`, `Items.json`, `System.json` | Các trường hiển thị và lệnh thoại/lựa chọn; nguồn chưa xác nhận English cần duyệt |
| XNA/MonoGame | `.xnb`; thư mục có thể là `Content/Strings`, `Content/Characters/Dialogue` | Báo tài nguyên XNB cần adapter theo kiểu dữ liệu; chưa trích xuất/ghi XNB |
| Source/container VPK | `.vpk`, directory và chunk cùng bộ; cần tìm bảng ngôn ngữ bên trong | Báo VPK cần bộ đọc; chưa giải nén/ghi VPK |
| Engine riêng | `localization`, `strings`, `dialogue`, `languages`, bảng JSON/CSV/XML và container riêng | Đọc định dạng đã hỗ trợ, xác nhận locale bằng schema; không tự ghi binary chưa có adapter |

Chỉ tên file hoặc phần mở rộng không đủ chứng minh engine hoặc ngôn ngữ. Một game có thể dùng nhiều kiểu dữ liệu cùng lúc. Bảng text chưa dùng trong runtime, tài nguyên tải từ server, chữ trong ảnh/video và chuỗi trong mã chương trình cần cách xử lý khác.

## Ví dụ kiểm tra thư mục thực tế

- **PEAK:** có `PEAK_Data/data.unity3d`, cần đọc packed player thay vì chỉ file text rời.
- **REPO:** có Unity assets và JSON; cần kiểm tra bảng ngôn ngữ và Addressables trong bundle, không dịch catalog như lời thoại.
- **Children of Morta:** có Unity assets, các bảng trong bundle; font phải xử lý theo adapter đã kiểm tra. Không ghép glyph thử nghiệm.
- **Stardew Valley:** có `.xnb`, gồm `Content/Characters/Dialogue` và `Content/Strings`. Có XNB không có nghĩa file đó chứa text; phải đọc ContentTypeReader và phân biệt các locale.
- **Darkest Dungeon:** có `localization/*.string_table.xml` với `<language id="english">` và các nhánh ngôn ngữ khác; đồng thời có `english.loc2`. Sửa XML nguồn chưa đủ: cần biên dịch LOC2 bằng công cụ đúng của game để runtime sử dụng. ToolVH mới xác nhận đọc nhánh English, chưa cung cấp writer LOC2.
- **Don’t Starve Together:** có `data/databundles/scripts.zip`; cần adapter Lua và cơ chế mod/đóng gói đúng, không dịch toàn bộ string literal trong code.
- **Left 4 Dead 2:** có nhiều VPK, cần directory và chunk cùng bộ. ToolVH hiện báo giới hạn, không đếm chuỗi ngẫu nhiên trong container là text đã tìm được.
- **Summer Memories:** có thư mục `www` và JSON; xác minh `rpg_core.js`/`rmmz_core.js` trước khi dùng adapter RPG Maker, không kết luận engine chỉ từ `.pak`.

## Quy tắc dịch

- Nhập thể loại, vai trò nhân vật, quan hệ, cách xưng hô và vùng giọng ở **Ngữ cảnh game / Văn phong**. Không đủ thông tin thì dùng cách xưng hô ít giả định, không tự bịa giới tính hoặc quan hệ.
- Tên nhân vật/địa danh được giữ theo nguồn và danh sách bảo vệ. Thuật ngữ do người dùng chỉ định có ưu tiên cao hơn. Không coi mọi từ viết hoa là tên riêng; `Level`, `Credits`, `Volume` phải chọn nghĩa theo chức năng.
- Câu JSON dạng record được bổ sung người nói khi có trường xác nhận, câu trước/sau trong cùng mảng/trường/scene/locale. Nội dung lân cận chỉ để hiểu câu đang dịch, không được dịch thêm.
- Giữ độ thô tục của nguồn, không thay bằng `***`, không làm nhẹ hoặc thêm chửi vào câu trung tính. `Fuck off!` có thể là **Cút mẹ đi!**; `It's fucking cold.` có thể là **Lạnh vãi.**; `Fuck!` khi bực tức có thể là **Địt mẹ! / Đụ má!** tùy vùng giọng. Đây là ví dụ theo ngữ cảnh, không phải bảng thay thế từ máy móc.
- Nghĩa hành vi tình dục của `fuck` khác lời cảm thán hoặc từ nhấn mạnh. Giữ tiếng lóng, mỉa mai và giọng nhân vật nhưng không tự tăng mức độ.
- Biến, thẻ, token và tên bảo vệ được kiểm tra cục bộ trước lưu. Kiểm tra này không chứng minh câu dịch đúng về văn học/ngữ nghĩa.
- **Google Dịch web không nhận prompt văn phong/ngữ cảnh.** Các quy tắc chỉ dẫn trên áp dụng cho đường dịch LLM (Ollama/Gemini/API tương thích). Google vẫn giữ cơ chế bảo vệ token/tên ở ToolVH, nhưng cần duyệt lại lời thoại/xưng hô/chửi tục. Nhà cung cấp LLM cũng có thể từ chối hoặc dịch sai.
- Bản dịch cũ không tự bị ghi đè sau cập nhật. Chọn dịch lại/thử lại các câu cần sửa; luôn thử trong game, kiểm tra font, bố cục và bản vá trước khi chia sẻ.

## Tài liệu tham khảo

- [Unity String Tables](https://docs.unity3d.com/Packages/com.unity.localization@1.5/manual/StringTables.html): locale, ID, metadata và Smart Strings.
- [Unreal Localization Overview](https://dev.epicgames.com/documentation/en-us/unreal-engine/localization-overview-for-unreal-engine): FText, quy trình thu thập/biên dịch tài nguyên ngôn ngữ.
- [Godot internationalizing games](https://docs.godotengine.org/en/stable/tutorials/i18n/internationalizing_games.html): CSV, gettext, plural và thay đổi locale.
- [Ren’Py Translation](https://www.renpy.org/doc/html/translation.html): lời thoại, string translation và template theo ngôn ngữ.
- [RPG Maker MZ API](https://developer.rpgmakerweb.com/rpg-maker-mz/): runtime và cấu trúc API engine; đường dẫn các game ở trên được kiểm tra trên thư mục local.
