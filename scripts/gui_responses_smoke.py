"""Responses provider configuration/probe and speed controls with mock API."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QPushButton
from toolvh.gui import MainWindow, configure_app
from toolvh.translation import Client

app = QApplication([])
configure_app(app)
with tempfile.TemporaryDirectory() as directory:
    window = MainWindow(settings_path=Path(directory) / 'settings.json')
    window.provider.setCurrentIndex(window.provider.findData('openai-responses'))
    assert not window.endpoint.isReadOnly()
    window.endpoint.setText('https://example.org/v1/responses')
    window.api_model.setEditText('test')
    window.api_key.setText('dummy-key')
    button, = [button for button in window.findChildren(QPushButton) if button.text() == 'Tối ưu tốc độ']
    with patch.object(Client, '_request') as request:
        button.click()
    request.assert_not_called()
    assert window.batch_size.value() == 40
    assert window.delay_seconds.value() == 0
    jobs = []
    window.run_job = lambda work, success, **kwargs: jobs.append((work, success))
    window.test_api()
    reply = {'status': 'completed', 'error': None, 'output': [{'type': 'message', 'role': 'assistant',
             'content': [{'type': 'output_text', 'text': '{"translation":"Bắt đầu chơi"}'}]}]}
    with patch.object(Client, '_request', return_value=reply) as request:
        result = jobs[0][0](lambda _: None)
    jobs[0][1](result)
    assert request.call_args.args[0] == 'https://example.org/v1/responses'
    assert 'thành công' in window.api_status.text()
    for provider, batch, delay in [('google-web', 1, 2), ('ollama', 5, 0), ('openrouter-free', 10, 2)]:
        window.provider.setCurrentIndex(window.provider.findData(provider))
        button.click()
        assert (window.batch_size.value(), window.delay_seconds.value()) == (batch, delay)
    window.dirty = False
    window.close()
print('GUI Responses OK: URL, probe, speed limits and no automatic API call')
