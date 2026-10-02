from dataclasses import asdict

from .model import Project


def compatibility_report(project: Project):
    deferred = [f for f in project.files if f.kind == "bundle"]
    skipped = [f for f in project.files if f.kind == "skipped"]
    unsupported = [f for f in project.files if f.note.startswith("Định dạng chưa hỗ trợ") or "chưa hỗ trợ" in f.note or "cần đọc tài nguyên đích" in f.note]
    errors = [f for f in project.files if f.kind == "error" or f.note.startswith("Không đọc được")]
    partial = [f for f in project.files if "thiếu type tree" in f.note]
    selected = [e for e in project.entries if e.enabled]
    translated = sum(bool(e.translation) for e in selected)
    return {
        "engines": project.engines, "candidate_entries": len(project.entries),
        "selected_entries": len(selected), "translated_entries": translated,
        "remaining_entries": len(selected) - translated,
        "unique_source_texts": len({e.source for e in selected}),
        "scan_revision": project.scan_revision,
        "english_entries": sum(e.source_locale == "en" or e.source_locale.startswith("en-") for e in project.entries),
        "review_entries": sum(not e.source_locale or "chưa xác nhận" in e.detection for e in project.entries),
        "bundle_files_not_scanned": len(deferred), "oversized_files": len(skipped),
        "unsupported_files": len(unsupported), "read_errors": len(errors),
        "files_with_missing_type_tree": len(partial),
        "font_and_in_game_status": "Chưa kiểm tra trong game",
        "coverage": "Có dữ liệu để dịch; không khẳng định đã tìm hết text của game" if selected else "Chưa có text được chọn để dịch",
        "files_needing_attention": [asdict(f) for f in deferred + skipped + unsupported + errors + partial],
    }


def report_text(project: Project):
    r = compatibility_report(project)
    lines = [f"Engine: {', '.join(r['engines'])}",
             f"{r['candidate_entries']:,} chuỗi ứng viên • {r['selected_entries']:,} vị trí được chọn • {r['unique_source_texts']:,} câu nguồn khác nhau",
             f"Đã dịch {r['translated_entries']:,} / {r['selected_entries']:,} vị trí được chọn."]
    lines.append(f"Nguồn tiếng Anh theo locale/cột/file: {r['english_entries']:,}; cần duyệt: {r['review_entries']:,}.")
    if project.scan_revision < 2:
        lines.append("Project dùng bộ quét cũ. Cần quét lại trước khi dịch/xuất bản vá.")
    if r["bundle_files_not_scanned"]:
        lines.append(f"Còn {r['bundle_files_not_scanned']} bundle/PCK chưa đọc → bật Quét sâu bundle / PCK.")
    if r["oversized_files"]:
        lines.append(f"{r['oversized_files']} file vượt giới hạn → tăng giới hạn quét trong Cấu hình.")
    if r["unsupported_files"]:
        lines.append(f"{r['unsupported_files']} file cần adapter riêng → xem báo cáo chẩn đoán.")
    if r["files_with_missing_type_tree"]:
        lines.append(f"{r['files_with_missing_type_tree']} file có MonoBehaviour thiếu type tree; phần dữ liệu này chưa được trích xuất.")
    if r["read_errors"]:
        lines.append(f"{r['read_errors']} file bị lỗi đọc; xem Nhật ký.")
    lines.append("Khả năng cài: bấm Kiểm tra khả năng cài để thử writer/catalog trước khi dịch; kết quả chỉ áp dụng các câu đã chọn.")
    lines.append("Font và bố cục: cần kiểm tra trong game sau khi cài thử bản vá.")
    return "\n".join(lines)
