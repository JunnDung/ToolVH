# Thay đổi phiên bản

## 0.7.9

- Giải nén Oodle bằng oozextract 0.5.5 MIT trong WASM/Wasmtime: không host imports, giới hạn 64 MB/block, 256 MB bộ nhớ và fuel; chặn dữ liệu bị cắt/sai kích thước. Đóng gói sẵn decoder, giữ nguồn wrapper/Cargo.lock/license và script build lại.
- Shady Job: đọc được 530 vị trí English từ LOCRES en/en-001, thử ghi nguồn và tiếng Việt dài hơn vào PAK; giữ payload còn lại. Chưa xác nhận đủ text trong IoStore hay nạp bản vá runtime.
- Quét không có mục được chọn sẽ hiện Tất cả ứng viên và hướng dẫn xem báo cáo; giữ Đã chọn khi có text xác nhận.

## 0.7.8

- Thêm đọc/ghi LOCRES trong PAK v10–v12 full directory index không mã hóa/có chữ ký; không nén, Zlib và Gzip. Kiểm tra SHA1 từng index/payload; giữ payload khác và cập nhật directory/path-hash locations khi ghi lại.
- Nhận diện tên file UTF8 PAK v12 và locale en-001; bỏ LOCRES nội bộ Engine trong PAK hiện đại.
- IoStore: đọc header/chunk, báo file cặp thiếu và giới hạn adapter; không đọc toàn bộ UCAS lớn chỉ để tìm chuỗi nhị phân.
- Bỏ manifest/dữ liệu launcher GSE/steam_settings khỏi text dịch; báo rõ Oodle chưa giải nén và tài nguyên Vietnamese có sẵn.
- Kiểm tra index Shady Job thực tế: 4.670 member, 16 LOCRES game, có vi-VN; English nén Oodle nên chưa thể trích xuất/cài ở bản này.

## 0.7.7

- Bắt lỗi Ollama đóng/reset kết nối, báo lỗi có thể tiếp tục từ checkpoint thay vì traceback HTTP.
- Kiểm tra lại bản dịch cũ khi mở project/thử lại lỗi và trước xuất/cài; báo đầy đủ mục lỗi thay vì chỉ lỗi đầu tiên. Khôi phục tên/thuật ngữ đứng riêng theo quy tắc hiện tại trước cài.
- Bỏ tự bảo vệ từ chung Forest/Temple từ bảng Locations; kiểm tra tên không báo sai chỉ vì khác chữ hoa/thường.
- Phục hồi đoạn dài Ollama: tối đa 64 đoạn/16.000 ký tự, lô tối đa 5 đoạn/1.500 ký tự; chia về từng đoạn nếu lô sai JSON/ID. Giữ token cục bộ và không ghi câu chưa hợp lệ.

## 0.7.6

- Ollama: lô sai JSON/ID hoặc câu mất token được thử riêng; phục hồi đoạn chữ có giới hạn khi vẫn mất token, ghép token nguyên gốc cục bộ và kiểm tra lại trước lưu.
- Thêm Thử lại câu lỗi, chỉ xử lý mục lỗi đang chọn, sao lưu project và giữ bản dịch cũ khi thất bại. Lỗi kết nối vẫn dừng tác vụ.
- Bảo vệ tên từ bảng Locations/CharacterNames và một số tên đã xác định của Children of Morta.
- CSV: dùng câu lân cận trong cùng bảng/object/ngôn ngữ, không tách ngữ cảnh theo số dòng.
- Bổ sung hướng dẫn phân biệt Level theo tiến trình/màn chơi với Resolution; không tự sửa bản dịch cũ hoặc cam kết đúng mọi ngữ cảnh.

## 0.7.5

- Thêm API Responses và tự nhận diện URL /responses trong preset tương thích OpenAI; chuẩn hóa URL, gửi instructions/input/store:false và đọc output hoàn tất.
- Chặn response bị cắt/từ chối/sai cấu trúc; kiểm tra ID, tên riêng, biến và thẻ trước khi lưu.
- Nút Tối ưu tốc độ đặt lô/thời gian nghỉ theo provider, giữ giới hạn ký tự và các kiểm tra chất lượng.
- Ren’Py: bảo vệ tên người nói được khai báo dạng chuỗi, cải thiện ngữ cảnh qua người nói khác trong cùng label.

## 0.7.4

- Thông báo 403/429 Google Dịch web phân biệt chặn kết nối với key/billing Gemini; giữ retry có giới hạn.

- Thêm lối chọn Google Dịch không cần key từ màn hình Bắt đầu; không tự gửi text hoặc chuyển sang API trả phí.

- Google Dịch web: cache từng đoạn trong project, giảm gọi lại nội dung trùng; giữ cache khi quét lại cùng game, không mang sang game khác.
- Bỏ thời gian nghỉ trùng giữa lô và yêu cầu; vẫn giữ nghỉ tối thiểu giữa yêu cầu mạng, retry giới hạn và lưu từng câu.
- Chia đoạn dài tại ranh giới câu/từ, giữ khoảng trắng và biến/thẻ; chặn từ quá dài không có điểm ngắt.
- Dịch lại bỏ qua cache; nút Xóa cache Google Dịch giữ nguyên bản dịch, cấu hình và key.

## 0.7.3

- Sửa lỗi CLI dừng khi console Windows dùng code page không chứa ký tự tiếng Việt.

- Mở rộng visual novel Ren’Py: câu thoại có thuộc tính/tên người nói, extend, menu có điều kiện, say arguments và chuỗi trải qua nhiều dòng vật lý.
- Monologue triple quote mặc định: tách từng khối theo dòng trống, giữ ranh giới lượt thoại và nội dung không được chọn.
- Bổ sung label/người nói/thuộc tính vào ngữ cảnh; giữ tên người nói, Python, script và đường dẫn tài nguyên.
- Chặn script có chuỗi chưa đóng; bỏ qua các chế độ monologue/cú pháp chưa hỗ trợ thay vì lấy nội dung bên trong làm thoại.
- Thêm kiểm thử parser, đọc lại, bảo vệ biến/thẻ và xuất/chép/khôi phục. RPA/RPYC và xác minh bằng runtime vẫn chưa hỗ trợ.

## 0.7.2

- Làm rõ chức năng Xuất để chép: thư mục files/ giữ đường dẫn game, gồm catalog đã cập nhật và backup riêng.
- Gói xuất có hướng dẫn chép/khôi phục thủ công, danh sách file và giới hạn phiên bản/font; vẫn tương thích cài/khôi phục bằng ToolVH.
- Kiểm thử chép thủ công, khôi phục nguyên byte và bundle/catalog Unity đi cùng nhau.

## 0.7.1

- Kiểm tra trước dịch thử cả câu nguồn và tiếng Việt dài hơn để phát hiện writer/catalog không xử lý được dữ liệu mở rộng trước khi gọi API.
- GUI/CLI báo số text ứng viên, mục chưa chọn và file chưa trích xuất được text; không coi đây là tỷ lệ bao phủ toàn game.
- Kiểm tra không sửa project, ghi game hoặc tạo bản vá; hỗ trợ dừng giữa các bước.

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
