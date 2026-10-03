"""Keep diagnostic evidence for unexpected GUI and native failures."""
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path


def install(app, window, directory):
    directory = Path(directory)
    logger = logging.getLogger('toolvh')
    logger.setLevel(logging.ERROR)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / 'errors.log', maxBytes=2_000_000,
                                      backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
        native = (directory / 'native-crash.log').open('a', encoding='utf-8')
        faulthandler.enable(file=native, all_threads=True)
    except OSError:
        window.log.appendPlainText('Không ghi được nhật ký lỗi; ứng dụng vẫn sử dụng được.')
        return
    previous = sys.excepthook

    def unexpected(kind, value, traceback):
        if not issubclass(kind, Exception):
            return previous(kind, value, traceback)
        logger.error('Unexpected GUI exception', exc_info=(kind, value, traceback))
        from PySide6.QtCore import QTimer
        message = f'{kind.__name__}: {value}\n\nNhật ký: {directory / "errors.log"}'
        QTimer.singleShot(0, window, lambda: window.error(message))

    def cleanup():
        if sys.excepthook is unexpected:
            sys.excepthook = previous
        faulthandler.disable()
        native.close()
        logger.removeHandler(handler)
        handler.close()

    sys.excepthook = unexpected
    app.aboutToQuit.connect(cleanup)
