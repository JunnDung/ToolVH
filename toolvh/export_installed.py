"""Export from verified backups without changing the installed game."""
import copy
import json
import os
import shutil
import tempfile
from pathlib import Path

from .model import safe_child, atomic_write


def export_copy(project, destination, progress=lambda text: None):
    from .patching import export_patch, install_patch
    from .terminology import validate_entry, term_policy, repair_protected_names
    project.require_current_scan()
    candidate = copy.deepcopy(project)
    repair_protected_names(candidate)
    terms = term_policy(candidate)
    skipped = []
    for entry in candidate.entries:
        if entry.enabled and entry.translation:
            errors = validate_entry(candidate, entry, entry.translation, terms)
            if errors:
                skipped.append({'id': entry.id, 'context': entry.context, 'errors': errors})
                entry.translation = ''
    root = Path(project.root).resolve()
    destination = Path(destination).resolve()
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError('Chọn thư mục bản vá ngoài game.')
    patches = ([project.applied_patch] if project.applied_patch else []) + list(project.font_patches)
    if patches:
        with tempfile.TemporaryDirectory(prefix='toolvh-export-') as directory:
            mirror = Path(directory) / root.name
            progress('Đang chuẩn bị bản gốc từ backup; không thay đổi game đang cài…')
            mirror.mkdir()
            relatives = {record.path for record in project.files}
            for patch in patches:
                manifest = json.loads((Path(patch) / 'manifest.json').read_text(encoding='utf-8'))
                relatives.update(file['path'] for file in manifest['files'])
            for relative in sorted(relatives):
                original = safe_child(root, relative)
                if not original.is_file():
                    continue
                target = safe_child(mirror, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                # Atomic restoration cannot modify the original hard link.
                try:
                    os.link(original, target)
                except OSError:
                    shutil.copyfile(original, target)
            for patch in reversed(patches):
                install_patch(patch, mirror, restore=True)
            candidate.root = str(mirror)
            candidate.applied_patch = ''
            candidate.font_patches = []
            result = export_patch(candidate, destination, progress)
    else:
        result = export_patch(candidate, destination, progress)
    result['game_root'] = str(root)
    result['skipped_invalid'] = skipped
    atomic_write(destination / 'manifest.json', json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
    instructions = (destination / 'README.txt').read_text(encoding='utf-8-sig')
    instructions = instructions.replace('Game nguồn: game\n', f'Game nguồn: {root.name}\n')
    instructions += '\nBản xuất chỉ chứa text hợp lệ; không kèm font đang cài.\n'
    if skipped:
        instructions += f'{len(skipped)} bản dịch không hợp lệ được giữ nguyên tiếng Anh. Xem skipped-invalid.json.\n'
        atomic_write(destination / 'skipped-invalid.json', json.dumps(skipped, ensure_ascii=False, indent=2).encode('utf-8'))
    atomic_write(destination / 'README.txt', instructions.encode('utf-8-sig'))
    return result
