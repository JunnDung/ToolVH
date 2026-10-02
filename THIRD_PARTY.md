# Phụ thuộc bên thứ ba

Giấy phép Apache-2.0 của ToolVH áp dụng cho mã của dự án. Các gói cài bằng pip giữ giấy phép riêng. Repo có decoder Oodle WASM biên dịch từ oozextract, nguồn wrapper, Cargo.lock và thông báo phụ thuộc trong native/oodle; runtime Wasmtime được cài bằng pip và đóng gói vào EXE.

| Gói | Giấy phép ghi trong metadata gói | Nguồn |
|---|---|---|
| PySide6 / Qt for Python | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | https://pyside.org |
| UnityPy | MIT | https://github.com/K0lb3/UnityPy |
| FontTools | MIT | https://github.com/fonttools/fonttools |
| Pillow | HPND | https://python-pillow.org |
| Wasmtime | Apache-2.0 WITH LLVM-exception | https://github.com/bytecodealliance/wasmtime-py |
| oozextract (decoder WASM) | MIT theo metadata upstream; lock, nguồn wrapper và thông báo nằm trong native/oodle | https://github.com/lvlvllvlvllvlvl/oozextract |
| PyInstaller (build) | GPLv2-or-later với ngoại lệ cho chương trình được đóng gói | https://pyinstaller.org |

Phụ thuộc gián tiếp và thư viện đi kèm bản EXE cũng có giấy phép riêng. Khi phát hành binary, kiểm tra và giữ các thông báo/license của những thành phần được đóng gói; không coi LICENSE của ToolVH là license chung cho toàn bộ binary.

Không đóng gói font hệ thống Windows; font nguồn do người dùng chọn và chỉ dùng tại máy họ. Không đưa font hoặc asset game vào release của ToolVH.
