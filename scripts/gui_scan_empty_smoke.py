"""A scan with only unselected candidates must show them instead of an empty filter."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from toolvh.gui import MainWindow, configure_app
from toolvh.model import Project, make_entry

app = QApplication([])
configure_app(app)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    entry = make_entry('readme.txt', {}, 'Review this candidate.', 'readme', 0.5)
    entry.enabled = False
    project = Project(str(root), entries=[entry])
    window = MainWindow(settings_path=root / 'settings.json')
    window.set_project(project)
    assert window.state.currentText() == 'Tất cả'
    assert window.proxy.rowCount() == 1
    assert 'Chưa tìm được' in window.status.text()
    entry.enabled = True
    window.set_project(project)
    assert window.state.currentText() == 'Đã chọn'
    assert window.proxy.rowCount() == 1
    window.dirty = False
    window.close()
print('GUI empty scan passed: unselected candidates visible; selected filter retained when available')
