"""Free Google provider and project cache controls, without network or keys."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication, QPushButton
from toolvh.gui import MainWindow, configure_app
from toolvh.scanner import scan
from toolvh.model import Project

app = QApplication([])
configure_app(app)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'en.json').write_text('{"text":"Start game"}', encoding='utf-8')
    project = scan(root)
    project.entries[0].translation = 'Bắt đầu'
    project.google_web_cache['entry'] = 'Bắt đầu'
    saved = root / 'project.toolvh.json'
    project.save(saved)
    window = MainWindow(str(saved), settings_path=root / 'settings.json')
    free_button, = [button for button in window.findChildren(QPushButton) if button.text() == 'Chọn Google Dịch miễn phí']
    free_button.click()
    assert window.provider.currentData() == 'google-web'
    assert window.tabs.currentWidget() == window.settings_page
    assert not window.api_key.isEnabled()
    assert not window.api_model.isEnabled()
    assert not window.api_config().api_key
    button, = [button for button in window.findChildren(QPushButton) if button.text() == 'Xóa cache Google Dịch']
    button.click()
    assert not window.project.google_web_cache
    assert window.project.entries[0].translation == 'Bắt đầu'
    window.save_project()
    assert not Project.load(saved).google_web_cache
    window.dirty = False
    window.close()
print('GUI Google cache OK: no key/model, clear cache keeps translations, saved project')
