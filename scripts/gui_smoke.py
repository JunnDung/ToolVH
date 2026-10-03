"""Exercise real Qt widgets using original synthetic text and temporary files."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
from pathlib import Path
from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from toolvh.gui import MainWindow, configure_app
from toolvh.scanner import scan

app = QApplication([])
configure_app(app)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'en.json').write_text(json.dumps({f'StartScreen.Option{i}': f'Start game {i}' for i in range(12)}), encoding='utf-8')
    project = scan(root)
    saved = root / 'test.toolvh.json'
    project.save(saved)
    window = MainWindow(str(saved), settings_path=root / 'settings.json')
    window.show()
    window.search.setText('StartScreen')
    QTest.qWait(250)
    app.processEvents()
    assert window.proxy.rowCount() == 12
    window.table.selectRow(0)
    app.processEvents()
    entry = window.current_entry()
    assert window.source.toPlainText() == entry.source
    source_index = window.model.index(window.model.entries.index(entry), 0)
    window.model.setData(source_index, Qt.Unchecked.value, Qt.CheckStateRole)
    assert not entry.enabled
    window.model.setData(source_index, Qt.Checked.value, Qt.CheckStateRole)
    assert entry.enabled
    assert window.grab().save(str(root / 'preview.png'))
    completed = []
    def success(result):
        assert QThread.currentThread() == app.thread()
        completed.append(result)
    window.run_job(lambda progress: 42, success)
    def finish():
        if not window.busy:
            window.dirty = False
            window.close()
            app.quit()
        else:
            QTimer.singleShot(25, finish)
    QTimer.singleShot(25, finish)
    QTimer.singleShot(15000, app.quit)
    app.exec()
    assert completed == [42]
print('GUI smoke passed: synthetic project, search, select, enable, render, main-thread callback')
