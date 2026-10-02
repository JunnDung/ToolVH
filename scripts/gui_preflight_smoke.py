"""GUI preflight: real dry writer, blocked sources never call translation API."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from toolvh.gui import MainWindow,configure_app
from toolvh.scanner import scan
from toolvh.translation import APIConfig

app=QApplication([]);configure_app(app)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);game=root/'game';game.mkdir();source=game/'en.json';source.write_text('{"text":"Start game"}')
    saved=root/'project.toolvh.json';scan(game).save(saved)
    w=MainWindow(str(saved),settings_path=root/'settings.json');w.show();app.processEvents()
    jobs=[];w.run_job=lambda work,success,**kwargs:jobs.append((work,success))
    w.check_installability()
    result=jobs[-1][0](lambda _:None)
    assert result['selected_entries']==1
    assert result['expanded_text_checked']
    assert result['scan_summary']['candidate_entries']==1
    with patch.object(QMessageBox,'information'):
        jobs[-1][1](result)
    w.api_config=lambda:APIConfig(provider='ollama',base_url='http://localhost:11434',model='test')
    w.save_project=lambda:True
    source.write_text('{"text":"Changed source"}')
    w.start_translation()
    with patch('toolvh.gui.translate') as api:
        try:jobs[-1][0](lambda _:None)
        except ValueError as exc:assert 'thay đổi' in str(exc)
        else:raise AssertionError('Changed source should block translation')
        api.assert_not_called()
    source.write_text('{"text":"Start game"}')
    w.start_translation()
    from toolvh.patching import prepare_changes
    def bounded_writer(project, groups, progress):
        if any(len(entry.translation)>len(entry.source) for entries in groups.values() for entry in entries):
            raise ValueError('Expanded text is unsupported')
        return prepare_changes(project, groups, progress)
    with patch('toolvh.patching.prepare_changes', side_effect=bounded_writer), patch('toolvh.gui.translate') as api:
        try:jobs[-1][0](lambda _:None)
        except ValueError as exc:assert 'Expanded text' in str(exc)
        else:raise AssertionError('Expanded writer failure should block translation')
        api.assert_not_called()
    w.dirty=False;w.close()
print('GUI preflight OK: check button, source change and expanded writer failure block API')

