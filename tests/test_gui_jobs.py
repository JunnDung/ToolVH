import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication
from toolvh.gui import MainWindow
from toolvh.model import Project, Entry


class GuiJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.window = MainWindow(settings_path=Path(self.temp.name) / 'settings.json')

    def drain(self, done):
        deadline = time.monotonic() + 5
        while not done() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(done(), 'Qt worker did not finish')
        self.app.processEvents()

    def tearDown(self):
        self.drain(lambda: not self.window.busy)
        self.window.dirty = False
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_results_delivered_after_thread_cleanup_and_can_start_next_job(self):
        results = []
        def success(value):
            self.assertEqual(QThread.currentThread(), self.app.thread())
            self.assertFalse(self.window.busy)
            self.assertIsNone(self.window.thread)
            results.append(value)
            if value == 1:
                self.window.run_job(lambda progress: 2, success)
        self.window.run_job(lambda progress: 1, success)
        self.drain(lambda: results == [1, 2] and not self.window.busy)

    def test_failure_does_not_prevent_next_job(self):
        def work(progress):
            raise ValueError('fixture failure')
        with patch.object(self.window, 'error') as error:
            self.window.run_job(work, lambda _: self.fail('failure returned success'))
            self.drain(lambda: not self.window.busy)
            error.assert_called_once_with('ValueError: fixture failure')
        results=[]
        self.window.run_job(lambda progress: 3, results.append)
        self.drain(lambda: results == [3] and not self.window.busy)

    def test_close_while_running_is_ignored_and_cancel_keeps_window_alive(self):
        entered = threading.Event()
        self.window.show()
        def work(progress):
            entered.set()
            self.window.stop.wait(3)
            return 4
        results=[]
        self.window.run_job(work, results.append)
        self.drain(entered.is_set)
        self.assertFalse(self.window.close())
        self.assertTrue(self.window.isVisible())
        self.window.cancel_job()
        self.drain(lambda: not self.window.busy)
        self.assertEqual(results, [4])
        self.assertIn('dừng', self.window.status.text())

    def test_actions_and_empty_filter_recovery(self):
        self.assertFalse(self.window.action_buttons['Xuất để chép…'].isEnabled())
        p=Project(self.temp.name,entries=[Entry('a','en.json',{},'Start game','menu',translation='Bắt đầu chơi')])
        self.window.set_project(p)
        self.assertTrue(self.window.action_buttons['Xuất để chép…'].isEnabled())
        self.assertFalse(self.window.action_buttons['Khôi phục'].isEnabled())
        self.window.search.setText('no match')
        self.window.update_filter()
        self.assertEqual(self.window.proxy.rowCount(),0)
        self.assertIn('Hiện tất cả',self.window.filter_hint.text())
        self.window.clear_filters()
        self.assertEqual(self.window.proxy.rowCount(),1)
        self.assertIsNone(self.window.current_entry())

    def test_unexpected_gui_error_is_logged_and_hook_is_restored(self):
        import sys
        from toolvh.crashlog import install
        previous = sys.excepthook
        directory = Path(self.temp.name) / 'logs'
        install(self.app, self.window, directory)
        with patch.object(self.window, 'error') as error:
            sys.excepthook(ValueError, ValueError('GUI fixture'), None)
            self.drain(lambda: error.called)
        self.assertIn('GUI fixture', (directory / 'errors.log').read_text(encoding='utf-8'))
        self.app.aboutToQuit.emit()
        self.assertIs(sys.excepthook, previous)

    def test_stale_model_index_and_enum_check_state(self):
        from PySide6.QtCore import Qt
        from toolvh.gui import EntriesModel
        model=EntriesModel()
        entry=Entry('a','en.json',{},'Start game','menu',enabled=False)
        model.set_entries([entry])
        index=model.index(0,0)
        self.assertTrue(model.setData(index,Qt.Checked,Qt.CheckStateRole))
        self.assertTrue(entry.enabled)
        model.set_entries([])
        self.assertIsNone(model.data(index))
        self.assertFalse(model.setData(index,Qt.Unchecked,Qt.CheckStateRole))

    def test_unread_resources_are_visible_in_workspace(self):
        from toolvh.model import FileRecord
        self.window.set_project(Project(self.temp.name,files=[FileRecord('game.utoc','utoc',note='chưa hỗ trợ')]))
        self.assertIn('1 tài nguyên',self.window.scan_notice.text())
        self.assertIn('Xem báo cáo',self.window.scan_notice.text())
        self.assertFalse(self.window.windowIcon().isNull())

    def test_styled_worker_render_and_shutdown_in_separate_process(self):
        import subprocess,sys
        repo=Path(__file__).resolve().parents[1]
        env=os.environ.copy()
        env['PYTHONPATH']=str(repo)
        env['QT_QPA_PLATFORM']='offscreen'
        result=subprocess.run([sys.executable,'-X','utf8','-X','faulthandler',str(repo/'scripts/gui_smoke.py')],cwd=repo,env=env,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout.decode('utf-8',errors='replace')+result.stderr.decode('utf-8',errors='replace'))

    def test_completed_worker_releases_project_payload(self):
        import gc,weakref
        class Payload:
            pass
        payload=Payload()
        reference=weakref.ref(payload)
        work=lambda progress,value=payload:value
        self.window.run_job(work,lambda _:None)
        del payload,work
        self.drain(lambda:not self.window.busy)
        gc.collect()
        self.assertIsNone(reference())
        self.assertIsNone(self.window.job_result)
