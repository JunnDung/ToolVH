"""GUI workflow test with simulated provider responses; never contacts an API."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from toolvh.gui import MainWindow, configure_app
from toolvh.scanner import scan
from toolvh.model import Project
from toolvh.translation import Client, GEMINI_BASE_URL


app = QApplication([])
configure_app(app)


def wait_job(window):
    deadline = time.monotonic() + 15
    while window.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert not window.busy, "Background task did not finish"


with tempfile.TemporaryDirectory(prefix="gui-api-") as directory:
    root = Path(directory)
    window = MainWindow(settings_path=root / "settings.json")
    errors = []
    window.error = errors.append
    window.show()
    app.processEvents()
    assert window.tabs.currentWidget() == window.home_page
    assert window.grab().save(str(root / "home.png"))
    window.tabs.setCurrentWidget(window.settings_page)
    app.processEvents()
    assert window.grab().save(str(root / "settings.png"))
    assert window.provider.currentData() == "gemini"
    assert window.endpoint.text() == GEMINI_BASE_URL
    assert window.endpoint.isReadOnly()
    window.api_key.setText("dummy-ui-secret")
    with patch.object(Client, "list_models", return_value=["gemini-mock-a", "gemini-mock-b"]):
        window.fetch_models()
        wait_job(window)
    assert window.api_model.count() == 2
    with patch.object(Client, "complete", return_value={"translation": "Bắt đầu chơi"}):
        window.test_api()
        wait_job(window)
    assert "thành công" in window.api_status.text()
    window.provider.setCurrentIndex(window.provider.findData("ollama"))
    assert window.api_key.text() == ""
    window.provider.setCurrentIndex(window.provider.findData("gemini"))
    assert window.api_key.text() == "dummy-ui-secret"
    assert window.api_model.currentText() == "gemini-mock-a"
    window.save_api_settings()
    assert "dummy-ui-secret" not in (root / "settings.json").read_text()

    game = root / "game"
    game.mkdir()
    (game / "localization.en.json").write_text(json.dumps([f"Start game number {i}" for i in range(12)]), encoding="utf-8")
    project = scan(game)
    window.project_path = root / "test.toolvh.json"
    window.set_project(project)
    window.delay_seconds.setValue(0)
    def complete(client, messages, stop):
        items = json.loads(messages[1]["content"])["items"]
        return {"translations": [{"id": row["id"], "text": "Bắt đầu chơi"} for row in items]}
    with patch.object(Client, "complete", complete):
        window.start_translation(limit=10)
        wait_job(window)
    assert sum(bool(e.translation) for e in project.entries) == 10
    assert sum(bool(e.translation) for e in Project.load(window.project_path).entries) == 10
    assert errors == [], errors
    window.dirty = False
    window.close()
print("GUI API smoke passed: provider isolation, model list, generation probe, settings, 10-entry preview, autosave (mock API only)")
