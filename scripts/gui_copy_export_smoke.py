"""Verify GUI export produces a copy-ready package without touching the game."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton
from toolvh.gui import MainWindow, configure_app
from toolvh.scanner import scan

app = QApplication([])
configure_app(app)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    game = root / 'game'
    game.mkdir()
    source = game / 'en.json'
    source.write_text('{"text":"Start game"}', encoding='utf-8')
    original = source.read_bytes()
    project = scan(game)
    project.entries[0].translation = 'Bắt đầu chơi'
    saved = root / 'project.toolvh.json'
    project.save(saved)
    window = MainWindow(str(saved), settings_path=root / 'settings.json')
    jobs = []
    window.run_job = lambda work, success, **kwargs: jobs.append((work, success))
    button, = [button for button in window.findChildren(QPushButton) if button.text() == 'Xuất để chép…']
    with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(root)):
        button.click()
    assert len(jobs) == 1
    result = jobs[0][0](lambda _: None)
    with patch.object(QMessageBox, 'information') as message:
        jobs[0][1](result)
    assert 'BÊN TRONG files/' in message.call_args.args[2]
    package, = root.glob('ToolVH-patch-*')
    assert (package / 'files/en.json').exists()
    assert (package / 'backup/en.json').read_bytes() == original
    assert source.read_bytes() == original
    window.dirty = False
    window.close()
print('GUI copy export OK: button, package, instructions and unchanged game')
