"""Retry only selected failed entries and backup, using simulated local responses."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QPushButton
from toolvh.gui import MainWindow, configure_app
from toolvh.formats import extract
from toolvh.model import Project
from toolvh.translation import Client

app = QApplication([])
configure_app(app)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    project = Project(str(root), entries=extract('["Hello{comma} friend.","Start game"]', 'json', 'en.json'))
    project.entries[0].translation = 'Old translation'
    project.entries[0].error = 'Lost token'
    project.entries[1].translation = 'Bắt đầu'
    file = root / 'sample.toolvh.json'
    project.save(file)
    window = MainWindow(file, settings_path=root / 'settings.json')
    window.provider.setCurrentIndex(window.provider.findData('ollama'))
    window.api_model.setEditText('test')
    window.delay_seconds.setValue(0)
    window.save_project = lambda: True
    jobs = []
    window.run_job = lambda work, success, **kwargs: jobs.append((work, success))
    button, = [button for button in window.findChildren(QPushButton) if button.text() == 'Thử lại câu lỗi']
    button.click()
    assert len(jobs) == 1
    backups = list(root.glob('*.before-retranslate-*'))
    assert len(backups) == 1
    assert Project.load(backups[0]).entries[0].translation == 'Old translation'
    calls = []
    def complete(client, messages, stop):
        rows = json.loads(messages[-1]['content'])['items']
        calls.extend(row['id'] for row in rows)
        return {'translations': [{'id': row['id'], 'text': row['text'].replace('Hello', 'Chào')} for row in rows]}
    with patch('toolvh.patching.preflight'), patch.object(Client, 'complete', complete):
        count = jobs[0][0](lambda _: None)
    jobs[0][1](count)
    assert count == 1
    assert calls == [window.project.entries[0].id]
    assert window.project.entries[0].translation == 'Chào{comma} friend.'
    assert not window.project.entries[0].error
    assert window.project.entries[1].translation == 'Bắt đầu'
    assert Project.load(file).entries[0].translation == 'Chào{comma} friend.'
    old = Project(str(root), entries=extract('["City Of Thieves","Reach City Of Thieves"]', 'json', 'en.json'), protected_names=['City Of Thieves'])
    old.entries[0].translation = 'Thành phố cướp'
    old.entries[1].translation = 'Đến thành phố cướp'
    window.set_project(old)
    assert all(entry.error for entry in old.entries)
    errors = []
    window.error = errors.append
    with patch.object(Client, 'complete') as request:
        assert not window.check_patch_translations()
    request.assert_not_called()
    assert old.entries[0].translation == 'City Of Thieves'
    assert not old.entries[0].error
    assert old.entries[1].error
    assert window.state.currentText() == 'Có lỗi'
    assert '1 mục' in errors[0]
    window.dirty = False
    window.close()
print('GUI retry errors OK: only failed entries, backup, checkpoint and old good target retained')
