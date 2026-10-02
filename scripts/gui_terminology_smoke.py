"""Real Qt controls and local mocked translation; no service or game changes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from toolvh.gui import MainWindow, configure_app
from toolvh.model import Project, Entry
app=QApplication([]);configure_app(app)
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    e=Entry('a','resources.assets',{'type':'MoonTranslatedMessageProvider'},'Defeat the Willow Stone','Quest / English / message 1',translation='Đánh bại đá')
    p=Project(str(root),entries=[e]);path=root/'test.toolvh.json';p.save(path)
    w=MainWindow(str(path),settings_path=root/'settings.json');w.show();app.processEvents()
    assert w.preserve_names.isChecked()
    w.protected_names.setPlainText('Jade Palace')
    w.game_context.setPlainText('Fantasy adventure');w.sync_settings()
    assert w.project.protected_names==['Jade Palace']
    with patch.object(QMessageBox,'information',return_value=QMessageBox.Ok):w.audit_translations()
    assert 'Willow Stone' in w.project.entries[0].error
    assert w.state.currentText()=='Có lỗi'
    assert w.project.entries[0].translation=='Đánh bại đá'
    assert w.save_project()
    w.api_config=lambda: __import__('toolvh.translation',fromlist=['APIConfig']).APIConfig(provider='ollama',base_url='http://localhost:11434',model='test')
    jobs=[];w.run_job=lambda task,callback: jobs.append(task)
    with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):w.start_translation(overwrite=True)
    assert len(jobs)==1
    backups=list(root.glob('*.before-retranslate-*.json'))
    assert len(backups)==1
    assert Project.load(backups[0]).entries[0].translation=='Đánh bại đá'
    w.dirty=False;w.close()
print('GUI terminology smoke OK: settings, audit, backup and retranslation controls')
