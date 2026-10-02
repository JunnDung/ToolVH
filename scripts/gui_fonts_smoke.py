"""Font dialog: Qt controls, diagnostics, selection and Unicode with mocked jobs."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox
from toolvh.gui import MainWindow, configure_app
from toolvh.model import Project, Entry
from toolvh.fonts import diagnose, suggested_font
app=QApplication([]);configure_app(app)
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'menu.ttf').write_bytes(suggested_font('candara').read_bytes())
    p=Project(str(root),entries=[Entry('x','en.json',{},'Language','',translation='Ngôn ngữ')]);path=root/'p.toolvh.json';p.save(path)
    w=MainWindow(str(path),settings_path=root/'settings.json');w.open_font_manager();app.processEvents()
    buttons={b.text():b for b in w.font_dialog.findChildren(QPushButton)}
    report=diagnose(p)
    # Feed one supported Ori record to assert only bitmap fonts are auto-selected.
    report['fonts'].append(dict(name='candara',file='resources.assets',kind='ori-bitmap',repairable=True,missing='ữ',note='SDF'))
    def job(work,success,**kw):success(report)
    w.run_job=job
    buttons['Quét font'].click();app.processEvents()
    assert w.font_tree.topLevelItemCount()==2
    from PySide6.QtCore import Qt
    assert w.font_tree.topLevelItem(0).checkState(0)==Qt.Unchecked
    assert w.font_tree.topLevelItem(1).checkState(0)==Qt.Checked
    buttons['Chuẩn hóa Unicode'].click();app.processEvents()
    assert w.project.entries[0].translation=='Ngôn ngữ'
    assert list(root.glob('*.before-unicode-*.json'))
    assert w.font_state['report'] is None
    with patch.object(w,'error') as error:buttons['Xuất bản vá font…'].click();assert error.called
    w.font_dialog.close()
    patch_dir=root/'manual-font';patch_dir.mkdir()
    (patch_dir/'manifest.json').write_text(__import__('json').dumps({'schema':1,'kind':'font','game_root':str(root),'files':[]}))
    def immediate(work,success,**kw):success(work(lambda _:None))
    w.run_job=immediate
    with patch('toolvh.gui.QFileDialog.getExistingDirectory',side_effect=[str(patch_dir),str(root)]), patch.object(QMessageBox,'question',return_value=QMessageBox.Yes), patch.object(QMessageBox,'information'), patch('toolvh.patching.install_patch',return_value=1):
        w.apply_patch(False)
    assert w.project.font_patches==[str(patch_dir.resolve())]
    with patch('toolvh.gui.QFileDialog.getExistingDirectory',side_effect=[str(patch_dir),str(root)]), patch.object(QMessageBox,'question',return_value=QMessageBox.Yes), patch.object(QMessageBox,'information'), patch('toolvh.patching.install_patch',return_value=1):
        w.apply_patch(True)
    assert w.project.font_patches==[]
    w.dirty=False;w.close()
print('GUI font smoke OK: scan, selection, Unicode backup, stale-report guard')
