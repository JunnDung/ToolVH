"""Switch away from a patched game without modifying its project or backup."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from toolvh.gui import MainWindow,configure_app
from toolvh.model import Project
from toolvh.scanner import scan

app=QApplication([])
configure_app(app)
with tempfile.TemporaryDirectory() as directory:
    folder=Path(directory).resolve()
    oldgame,newgame=folder/'oldgame',folder/'newgame'
    oldgame.mkdir();newgame.mkdir()
    oldbytes=b'{"text":"Old game"}'
    (oldgame/'en.json').write_bytes(oldbytes)
    (newgame/'en.json').write_text('{"text":"New game"}')
    old=scan(oldgame)
    old.entries[0].translation='Game cũ'
    old.glossary={'Old':'Cũ'}
    old.applied_patch=str(folder/'old-backup')
    saved=folder/'old.toolvh.json';old.save(saved)
    savedbytes=saved.read_bytes()
    window=MainWindow(str(saved),settings_path=folder/'settings.json')
    errors=[];calls=[]
    window.error=errors.append
    def run_job(function,success,**kwargs):
        calls.append(1)
        success(function(lambda text:None))
    window.run_job=run_job
    window.game_path.setText(str(newgame))
    window.start_scan()
    assert not errors and len(calls)==1
    assert Path(window.project.root).resolve()==newgame
    assert not window.project.applied_patch and window.project_path is None
    assert window.project.entries[0].source=='New game'
    assert not window.project.entries[0].translation and not window.project.glossary
    assert (oldgame/'en.json').read_bytes()==oldbytes
    assert saved.read_bytes()==savedbytes
    assert Project.load(saved).applied_patch==old.applied_patch
    # An alternate spelling of the same folder must still guard source rescans.
    window.set_project(old)
    window.dirty=False
    window.game_path.setText(str(oldgame)+os.sep+'.')
    window.start_scan()
    assert len(calls)==1 and len(errors)==1 and 'Khôi phục' in errors[0]
    window.dirty=False;window.close()
print('GUI switch passed: other game scans immediately; old translation/backup retained; same-game rescan guarded')
