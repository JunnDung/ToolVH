from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QSortFilterProxyModel, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QFont, QFontDatabase, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QTableView, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QGridLayout, QScrollArea, QDialog,
)

from .model import Project
from .patching import export_csv, export_patch, import_csv, install_patch, apply_project, restore_project
from .scanner import scan
from .translation import APIConfig, Client, PROVIDERS, translate, validate, environment_key, normalize_translation
from .terminology import validate_entry, audit, inferred_names, repair_protected_names
from .settings import SettingsStore
from .diagnostics import report_text, compatibility_report

STYLE = """
QWidget { background: #11131d; color: #e8e8f3; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow { background: #11131d; }
QLabel#title { font-size: 26px; font-weight: 700; color: #faf9ff; }
QLabel#muted { color: #a0a5bc; }
QLabel#version { color: #c2b7ff; background: #27223e; border: 1px solid #40355d; border-radius: 12px; padding: 5px 12px; }
QLabel#metric { font-size: 14px; color: #84e8cc; padding: 14px; background: #1a2330; border: 1px solid #2e394b; border-radius: 10px; }
QFrame#card { background: #1c1e2e; border: 1px solid #33364c; border-radius: 14px; }
QFrame#card QLabel { background: transparent; }
QLabel#step { font-size: 18px; font-weight: 600; color: #c4b8ff; }
QPushButton { background: #25283b; border: 1px solid #3b4058; padding: 9px 16px; border-radius: 8px; }
QPushButton:hover { background: #34324f; border-color: #8b7acd; }
QPushButton:pressed { background: #423b64; }
QPushButton:focus { border: 1px solid #b5a6ff; }
QPushButton:disabled { color: #70758b; background: #1b1d2a; border-color: #2b2e40; }
QPushButton#primary { background: #6854c7; border-color: #8d78eb; color: #ffffff; font-weight: 600; }
QPushButton#primary:hover { background: #8069df; }
QPushButton#primary:pressed { background: #53429d; }
QPushButton#primary:disabled { background: #2c2940; border-color: #3c3554; color: #8e87a5; }
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox { background: #191c2b; border: 1px solid #373c52; padding: 8px; border-radius: 7px; selection-background-color: #594695; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #a393ea; }
QTableView, QTreeWidget { background: #171b28; alternate-background-color: #1c2030; border: 1px solid #343a50; border-radius: 8px; gridline-color: #2b3043; selection-background-color: #3b335c; }
QHeaderView::section { background: #252a3b; color: #c1c7dc; padding: 10px; border: 0; border-right: 1px solid #353a50; }
QTabWidget::pane { border: 1px solid #30354a; border-radius: 12px; top: -1px; }
QTabBar::tab { background: #1a1d2b; padding: 12px 22px; color: #a5adc5; margin-right: 5px; border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:hover { background: #28243c; }
QTabBar::tab:selected { color: #dbd4ff; background: #302849; border-bottom: 3px solid #9b88ec; }
QProgressBar { border: none; background: #24283a; height: 7px; }
QProgressBar::chunk { background: #71dabb; }
QToolTip { background: #2d2945; color: #f4f0ff; border: 1px solid #75639e; padding: 6px; }
QSplitter::handle { background: #11131d; width: 8px; height: 8px; }
QScrollBar:vertical { background: #1a1d2a; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #42475e; min-height: 24px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #1a1d2a; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #42475e; min-width: 24px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""


class EntriesModel(QAbstractTableModel):
    changed = Signal()
    HEADERS = ["Dịch", "Text gốc", "Tiếng Việt", "Vị trí / ngữ cảnh", "Nguồn"]

    def __init__(self):
        super().__init__()
        self.entries = []

    def set_entries(self, entries):
        self.beginResetModel()
        self.entries = entries
        self.endResetModel()

    def refresh(self):
        if self.entries:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.entries) - 1, 4))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 5

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.entries) and 0 <= index.column() < 5):
            return None
        e = self.entries[index.row()]
        col = index.column()
        if role == Qt.CheckStateRole and col == 0:
            return Qt.Checked if e.enabled else Qt.Unchecked
        if role == Qt.DisplayRole:
            return ["", e.source.replace("\n", " ↵ "), e.translation.replace("\n", " ↵ "), e.context, e.source_locale.upper() or "Cần duyệt"][col]
        if role == Qt.ToolTipRole:
            return e.error or f"{e.file}\n{e.context}\n{e.detection or 'Project cũ — cần quét lại'}\n\n{e.source}"
        if role == Qt.ForegroundRole and e.error:
            return QColor("#ffa3a3")
        if role == Qt.ForegroundRole and col == 2 and e.translation:
            return QColor("#78ddbc")

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return flags | Qt.ItemIsUserCheckable if index.column() == 0 else flags

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or not 0 <= index.row() < len(self.entries):
            return False
        if role == Qt.CheckStateRole and index.column() == 0:
            self.entries[index.row()].enabled = value in (Qt.Checked, Qt.Checked.value)
            self.dataChanged.emit(index, index, [role])
            self.changed.emit()
            return True
        return False


class TextFilter(QSortFilterProxyModel):
    text = ""
    file = ""
    state = "Tất cả"

    def filterAcceptsRow(self, row, parent):
        e = self.sourceModel().entries[row]
        if self.file and e.file != self.file:
            return False
        if self.text and self.text not in (e.source + e.translation + e.context + e.file).casefold():
            return False
        return (self.state == "Tất cả" or self.state == "Đã chọn" and e.enabled
                or self.state == "Chưa dịch" and e.enabled and not e.translation
                or self.state == "Đã dịch" and bool(e.translation)
                or self.state == "Cần duyệt" and (not e.source_locale or "chưa xác nhận" in e.detection)
                or self.state == "Có lỗi" and bool(e.error))


class Worker(QObject):
    message = Signal(str)
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, function):
        super().__init__()
        self.function = function

    @Slot()
    def run(self):
        try:
            self.result.emit(self.function(self.message.emit))
        except Exception as exc:
            logging.getLogger("toolvh").exception("Background task failed")
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self, project_path=None, settings_path=None):
        super().__init__()
        self.project = None
        self.project_path = None
        self.busy = False
        self.thread = None
        self.worker = None
        self.action_buttons = {}
        self.dirty = False
        self.stop = threading.Event()
        self.settings_store = SettingsStore(settings_path)
        self.profiles, self.recent, self.active_provider = {}, [], None
        self.verified_api = None
        from . import __version__
        self.setWindowTitle(f"ToolVH {__version__} · Việt hóa game")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets/toolvh.svg")))
        self.resize(1360, 900)
        self.setMinimumSize(1060, 740)
        base = QWidget()
        self.setCentralWidget(base)
        outer = QVBoxLayout(base)
        outer.setContentsMargins(24, 20, 24, 16)
        title_row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(self.windowIcon().pixmap(56, 56))
        logo.setFixedSize(64, 64)
        title_row.addWidget(logo)
        title = QLabel("ToolVH  ·  Việt hóa game")
        title.setObjectName("title")
        title_row.addWidget(title)
        version = QLabel(f"v{__version__}")
        version.setObjectName("version")
        version.setFixedHeight(30)
        version.setAlignment(Qt.AlignCenter)
        title_row.addWidget(version)
        title_row.addStretch()
        self.open_btn = self.button("Mở project", self.open_project)
        self.save_btn = self.button("Lưu project", self.save_project)
        title_row.addWidget(self.open_btn)
        title_row.addWidget(self.save_btn)
        outer.addLayout(title_row)
        subtitle = QLabel("Tìm dữ liệu  →  Kiểm tra text  →  Dịch tiếng Việt  →  Xuất bản vá")
        subtitle.setObjectName("muted")
        outer.addWidget(subtitle)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self.home_page = self.build_home()
        self.tabs.addTab(self.home_page, "Bắt đầu")
        scan_tab = QWidget()
        self.workspace_page = scan_tab
        layout = QVBoxLayout(scan_tab)
        layout.setContentsMargins(16, 16, 16, 16)
        row = QHBoxLayout()
        self.game_path = QLineEdit()
        self.game_path.setPlaceholderText("Chọn thư mục cài đặt game…")
        row.addWidget(self.game_path, 1)
        row.addWidget(self.button("Chọn game…", self.choose_game))
        self.deep = QCheckBox("Quét sâu bundle / PCK")
        self.deep.setToolTip("Đọc Unity bundle, Godot PCK và Unreal PAK hỗ trợ. LOCRES rời được đọc ở cả hai chế độ; IoStore chỉ báo chẩn đoán.")
        self.deep.setChecked(True)
        self.deep.setToolTip("Đọc Unity bundle/data.unity3d theo asset, Godot PCK và Unreal PAK hỗ trợ. Có thể mất vài phút; IoStore chỉ báo chẩn đoán.")
        row.addWidget(self.deep)
        row.addWidget(self.button("Quét dữ liệu", self.start_scan, primary=True))
        layout.addLayout(row)
        help_text = QLabel("Chọn thư mục chứa file chạy game → Quét dữ liệu → Dịch thử 10 câu → Duyệt bản dịch → Xuất để chép.")
        help_text.setObjectName("muted")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.metrics = QLabel("Chưa có project · Chọn thư mục game để bắt đầu")
        self.metrics.setObjectName("metric")
        self.metrics.setWordWrap(True)
        layout.addWidget(self.metrics)
        self.scan_notice = QLabel("Quét dữ liệu để biết định dạng game có thể đọc và tạo bản vá.")
        self.scan_notice.setObjectName("muted")
        self.scan_notice.setWordWrap(True)
        self.scan_notice.linkActivated.connect(lambda _: self.tabs.setCurrentWidget(self.report_page))
        layout.addWidget(self.scan_notice)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm text, bản dịch, tên asset hoặc khóa hội thoại…")
        self.filter_timer = QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(200)
        self.filter_timer.timeout.connect(self.update_filter)
        self.search.textChanged.connect(lambda: self.filter_timer.start())
        search_row.addWidget(self.search, 1)
        self.state = QComboBox()
        self.state.addItems(["Tất cả", "Đã chọn", "Chưa dịch", "Đã dịch", "Cần duyệt", "Có lỗi"])
        self.state.currentTextChanged.connect(self.update_filter)
        search_row.addWidget(self.state)
        search_row.addWidget(self.button("Chọn kết quả lọc", lambda: self.enable_visible(True)))
        search_row.addWidget(self.button("Bỏ chọn kết quả", lambda: self.enable_visible(False)))
        layout.addLayout(search_row)
        self.filter_hint = QLabel()
        self.filter_hint.setObjectName("muted")
        self.filter_hint.setWordWrap(True)
        self.filter_hint.setTextFormat(Qt.RichText)
        self.filter_hint.linkActivated.connect(self.clear_filters)
        layout.addWidget(self.filter_hint)

        horizontal = QSplitter(Qt.Horizontal)
        self.files = QTreeWidget()
        self.files.setHeaderLabels(["File dữ liệu", "Text"])
        self.files.setColumnWidth(0, 280)
        self.files.currentItemChanged.connect(self.select_file)
        horizontal.addWidget(self.files)
        vertical = QSplitter(Qt.Vertical)
        self.model = EntriesModel()
        self.model.changed.connect(self.on_edit)
        self.proxy = TextFilter()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for col, size in enumerate([48, 290, 270, 350, 75]):
            self.table.setColumnWidth(col, size)
        self.table.selectionModel().selectionChanged.connect(self.select_entry)
        for signal in (self.proxy.rowsRemoved, self.proxy.rowsInserted, self.proxy.layoutChanged):
            signal.connect(lambda *args: QTimer.singleShot(0, self.select_entry))
        vertical.addWidget(self.table)
        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 8, 0, 0)
        self.context = QLabel("Chọn một dòng để xem đầy đủ và chỉnh bản dịch.")
        self.context.setWordWrap(True)
        self.context.setObjectName("muted")
        editor_layout.addWidget(self.context)
        fields = QHBoxLayout()
        self.source = QPlainTextEdit()
        self.source.setReadOnly(True)
        self.source.setPlaceholderText("Text gốc")
        self.target = QPlainTextEdit()
        self.target.setPlaceholderText("Bản dịch tiếng Việt · Giữ nguyên biến và thẻ định dạng")
        fields.addWidget(self.source)
        fields.addWidget(self.target)
        editor_layout.addLayout(fields)
        edit_actions = QHBoxLayout()
        self.validation = QLabel("")
        self.validation.setWordWrap(True)
        edit_actions.addWidget(self.validation, 1)
        edit_actions.addWidget(self.button("Lưu câu dịch", self.save_entry, primary=True))
        editor_layout.addLayout(edit_actions)
        vertical.addWidget(editor)
        vertical.setSizes([390, 190])
        horizontal.addWidget(vertical)
        horizontal.setSizes([290, 1060])
        layout.addWidget(horizontal, 1)
        actions = QHBoxLayout()
        actions.addWidget(self.button("Xuất CSV", self.export_csv))
        actions.addWidget(self.button("Nhập CSV", self.import_csv))
        actions.addStretch()
        actions.addWidget(self.button("Dịch thử 10 câu", lambda: self.start_translation(limit=10)))
        layout.addLayout(actions)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.button("Dịch các câu đã chọn", self.start_translation, primary=True))
        actions.addWidget(self.button("Xuất để chép…", self.start_export, primary=True))
        actions.addWidget(self.button("Cài vào game", self.apply_current_project, primary=True))
        actions.addWidget(self.button("Khôi phục", self.restore_current_project))
        layout.addLayout(actions)
        self.tabs.addTab(scan_tab, "01   Dữ liệu / Bản dịch")

        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        settings_layout.setContentsMargins(24, 24, 24, 24)
        note = QLabel("Có thể quét, sửa tay và xuất CSV khi chưa có API. Khi bấm Dịch, text đã chọn được gửi tới endpoint bên dưới.")
        note.setWordWrap(True)
        settings_layout.addWidget(note)
        form = QFormLayout()
        self.provider = QComboBox()
        for key, (label, _) in PROVIDERS.items():
            self.provider.addItem(label, key)
        self.endpoint = QLineEdit()
        self.api_model = QComboBox()
        self.api_model.setEditable(True)
        self.api_model.lineEdit().setPlaceholderText("Bấm Tải danh sách model sau khi nhập key, hoặc nhập tên model")
        model_row = QWidget()
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.addWidget(self.api_model, 1)
        model_layout.addWidget(self.button("Tải danh sách model", self.fetch_models))
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("Dán key tại đây; không cần gửi key vào chat")
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.api_key, 1)
        self.show_key = QCheckBox("Hiện key")
        self.show_key.toggled.connect(lambda checked: self.api_key.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password))
        key_layout.addWidget(self.show_key)
        self.remember_key = QCheckBox("Nhớ key trên tài khoản Windows này (mã hóa bằng DPAPI)")
        self.api_help = QLabel()
        self.api_help.setWordWrap(True)
        self.api_help.setOpenExternalLinks(True)
        settings_layout.addWidget(self.api_help)
        self.api_status = QLabel("Chưa kiểm tra kết nối.")
        self.api_status.setWordWrap(True)
        self.api_status.setObjectName("metric")
        self.batch_size = QSpinBox()
        self.batch_size.setRange(1, 100)
        self.batch_size.setValue(20)
        self.delay_seconds = QSpinBox()
        self.delay_seconds.setRange(0, 120)
        self.delay_seconds.setValue(2)
        self.delay_seconds.setSuffix(" giây")
        self.json_mode = QCheckBox("Yêu cầu API trả JSON (tắt nếu endpoint không hỗ trợ)")
        self.json_mode.setChecked(True)
        self.instructions = QPlainTextEdit("Dịch tự nhiên, ngắn gọn, phù hợp giao diện và hội thoại game.")
        self.instructions.setMaximumHeight(100)
        self.instructions.setToolTip("Giữ mức độ lời chửi như nguồn. Có thể chỉ định giọng Bắc/Nam, cách xưng hô và thuật ngữ. Google Dịch web không nhận chỉ dẫn này.")
        self.glossary = QPlainTextEdit()
        self.glossary.setPlaceholderText("Mỗi dòng: thuật ngữ = bản dịch\nChef = Đầu bếp\nOnion King = Vua Hành Tây")
        self.glossary.setMaximumHeight(180)
        self.preserve_names = QCheckBox("Giữ nguyên tên nhân vật, địa danh, vật phẩm và kỹ năng")
        self.preserve_names.setChecked(True)
        self.protected_names = QPlainTextEdit()
        self.protected_names.setMaximumHeight(110)
        self.protected_names.setPlaceholderText("Mỗi dòng một tên cần giữ nguyên. Tool nhận diện một số tên theo dữ liệu game; thêm tên còn thiếu tại đây.")
        self.game_context = QPlainTextEdit()
        self.game_context.setMaximumHeight(100)
        self.game_context.setPlaceholderText("Thể loại game, vai trò nhân vật, cách xưng hô, ngữ cảnh nhiệm vụ…")
        review_actions = QWidget()
        review_layout = QHBoxLayout(review_actions)
        review_layout.setContentsMargins(0, 0, 0, 0)
        review_layout.addWidget(self.button("Xem tên nhận diện", self.show_names))
        review_layout.addWidget(self.button("Kiểm tra bản dịch", self.audit_translations))
        review_layout.addWidget(self.button("Xóa cache Google Dịch", self.clear_google_cache))
        review_layout.addWidget(self.button("Dịch lại các câu đã chọn", lambda: self.start_translation(overwrite=True)))
        review_layout.addWidget(self.button("Thử lại câu lỗi", lambda: self.start_translation(only_errors=True)))
        review_layout.addStretch()
        self.max_mb = QSpinBox()
        self.max_mb.setRange(1, 4096)
        self.max_mb.setValue(256)
        self.max_mb.setSuffix(" MB / file hoặc asset")
        self.max_mb.setToolTip("Packed UnityFS data.unity3d: giới hạn mỗi asset; các định dạng còn lại: giới hạn mỗi file.")
        api_actions_widget = QWidget()
        api_actions = QHBoxLayout(api_actions_widget)
        api_actions.setContentsMargins(0, 0, 0, 0)
        api_actions.addWidget(self.button("Kiểm tra kết nối", self.test_api, primary=True))
        api_actions.addWidget(self.button("Tối ưu tốc độ", self.optimize_translation_speed))
        api_actions.addWidget(self.button("Lưu cấu hình", self.save_api_settings))
        api_actions.addWidget(self.button("Xóa key đã nhớ", self.forget_key))
        api_actions.addStretch()
        for label, widget in [("Dịch vụ", self.provider), ("Base URL", self.endpoint), ("API key", key_row),
                              ("Lưu key", self.remember_key), ("Model", model_row),
                              ("Câu mỗi lô", self.batch_size), ("Nghỉ giữa các lô", self.delay_seconds), ("Định dạng", self.json_mode),
                              ("Văn phong", self.instructions), ("Ngữ cảnh game", self.game_context),
                              ("Tên riêng", self.preserve_names), ("Giữ thêm tên", self.protected_names),
                              ("Thuật ngữ", self.glossary), ("Duyệt bản dịch", review_actions), ("Giới hạn quét", self.max_mb)]:
            form.addRow(label, widget)
            if label == "Model":
                form.addRow("", api_actions_widget)
                form.addRow("Trạng thái", self.api_status)
        settings_layout.addLayout(form)
        settings_layout.addStretch()
        self.settings_page = QScrollArea()
        self.settings_page.setWidgetResizable(True)
        self.settings_page.setWidget(settings)
        self.tabs.addTab(self.settings_page, "02   Dịch vụ dịch / Cấu hình")
        self.instructions.textChanged.connect(self.on_edit)
        self.glossary.textChanged.connect(self.on_edit)
        self.preserve_names.toggled.connect(self.on_edit)
        self.protected_names.textChanged.connect(self.on_edit)
        self.game_context.textChanged.connect(self.on_edit)

        report = QWidget()
        self.report_page = report
        report_layout = QVBoxLayout(report)
        report_layout.setContentsMargins(16, 16, 16, 16)
        help_text = QLabel("Bản vá được xuất ra thư mục riêng, kèm backup và SHA-256. Đóng game trước khi cài hoặc khôi phục.\n"
                           "Bản dịch thay vào ngôn ngữ nguồn: nếu dịch cột English, chọn English trong game. Font và bố cục cần kiểm tra trong game.")
        help_text.setWordWrap(True)
        report_layout.addWidget(help_text)
        self.support_report = QLabel("Chưa quét game. Sau khi quét, mức hỗ trợ và phần dữ liệu còn thiếu sẽ hiện ở đây.")
        self.support_report.setWordWrap(True)
        self.support_report.setObjectName("metric")
        report_layout.addWidget(self.support_report)
        patch_actions = QHBoxLayout()
        patch_actions.addWidget(self.button("Cài bản vá…", lambda: self.apply_patch(False)))
        patch_actions.addWidget(self.button("Khôi phục bản gốc…", lambda: self.apply_patch(True)))
        patch_actions.addWidget(self.button("Kiểm tra khả năng cài", self.check_installability))
        patch_actions.addWidget(self.button("Xuất chẩn đoán…", self.export_diagnostics))
        patch_actions.addWidget(self.button("Mở nhật ký lỗi", self.open_error_logs))
        patch_actions.addWidget(self.button("Kiểm tra / sửa font…", self.open_font_manager, primary=True))
        patch_actions.addStretch()
        report_layout.addLayout(patch_actions)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        report_layout.addWidget(self.log, 1)
        self.tabs.addTab(report, "03   Kiểm tra / Khôi phục")

        footer = QHBoxLayout()
        self.status = QLabel("Sẵn sàng · File game chỉ thay đổi khi bạn chọn Cài bản vá.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self.cancel = self.button("Dừng tác vụ", self.cancel_job)
        self.cancel.setEnabled(False)
        footer.addWidget(self.cancel)
        outer.addLayout(footer)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 1)
        outer.addWidget(self.progress_bar)
        self.provider.currentIndexChanged.connect(self.change_provider)
        self.api_model.currentTextChanged.connect(self.api_changed)
        self.api_key.textChanged.connect(self.api_changed)
        self.endpoint.textChanged.connect(self.api_changed)
        self.load_api_settings()
        if project_path:
            self.load_project(project_path)
        self.update_actions()

    def build_home(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        heading = QLabel("Biến ngôn ngữ thành trải nghiệm.")
        heading.setObjectName("title")
        layout.addWidget(heading)
        intro = QLabel("Không cần sửa file thủ công. Bắt đầu với một game, dịch thử một vài câu, rồi tạo bản vá có backup.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        grid = QGridLayout()
        steps = [
            ("01  Chọn game", "Quét thư mục và bundle. Nhận diện engine, bảng ngôn ngữ và các định dạng cần bổ sung bộ đọc.", "Chọn game & quét", self.choose_and_scan),
            ("02  Chọn dịch vụ dịch", "Chọn Google Dịch không cần key, Ollama trên máy hoặc dịch vụ API. Kiểm tra kết nối trước khi dịch.", "Chọn cách dịch", lambda: self.tabs.setCurrentWidget(self.settings_page)),
            ("03  Dịch tiếng Việt", "Dịch thử 10 câu trước, xem kết quả rồi dịch tiếp. Tự lưu mỗi lô và dùng lại câu có cùng ngữ cảnh.", "Xem & dịch dữ liệu", lambda: self.tabs.setCurrentWidget(self.workspace_page)),
            ("04  Xuất và cài bản vá", "Xuất file đã dịch kèm backup. Đóng game để cài, sau đó kiểm tra font và bố cục trong game.", "Bản vá & khôi phục", lambda: self.tabs.setCurrentWidget(self.report_page)),
        ]
        for index, (title, description, action, callback) in enumerate(steps):
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(18, 16, 18, 16)
            label = QLabel(title)
            label.setObjectName("step")
            box.addWidget(label)
            body = QLabel(description)
            body.setWordWrap(True)
            body.setMinimumHeight(48)
            box.addWidget(body)
            box.addWidget(self.button(action, callback, primary=index == 0))
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        layout.addWidget(self.button("Chọn Google Dịch miễn phí", self.choose_google_free))
        self.home_summary = QLabel("Chưa mở project • Bắt đầu bằng Chọn game & quét hoặc Mở project.")
        self.home_summary.setObjectName("metric")
        self.home_summary.setWordWrap(True)
        layout.addWidget(self.home_summary)
        self.completion = QProgressBar()
        self.completion.setRange(0, 100)
        self.completion.setValue(0)
        self.completion.setTextVisible(False)
        layout.addWidget(self.completion)
        recent_row = QHBoxLayout()
        recent_row.addWidget(QLabel("Project gần đây"))
        self.recent_combo = QComboBox()
        self.recent_combo.setMinimumWidth(400)
        recent_row.addWidget(self.recent_combo, 1)
        recent_row.addWidget(self.button("Mở lại", self.open_recent))
        layout.addLayout(recent_row)
        support = QLabel("Hỗ trợ đọc/ghi: Unity TextAsset, MonoBehaviour có type tree, JSON, CSV/TSV, XML, INI, TXT, SRT.\n"
                         "Unity · Unreal · Godot · Visual novel: hỗ trợ theo từng định dạng. Dữ liệu mã hóa, text trong ảnh và container chưa có bộ đọc cần xử lý riêng; xem báo cáo sau khi quét.")
        support.setObjectName("muted")
        support.setWordWrap(True)
        layout.addWidget(support)
        layout.addStretch()
        return page

    def choose_and_scan(self):
        path = QFileDialog.getExistingDirectory(self, "Chọn thư mục gốc của game", self.game_path.text())
        if path:
            self.game_path.setText(path)
            self.tabs.setCurrentWidget(self.workspace_page)
            self.start_scan()

    def open_recent(self):
        path = self.recent_combo.currentData()
        if path and self.maybe_save():
            self.load_project(path)

    def remember_project(self):
        if not self.project_path:
            return
        path = str(self.project_path.resolve())
        self.recent = [path] + [p for p in self.recent if p != path][:9]
        self.recent_combo.clear()
        for p in self.recent:
            self.recent_combo.addItem(p, p)
        try:
            self.settings_store.save(self.active_provider, self.profiles, self.recent)
        except Exception:
            self.log.appendPlainText("Chưa lưu được danh sách project gần đây. Project vẫn dùng được.")

    def button(self, text, callback, primary=False):
        button = QPushButton(text.replace("&", "&&"))
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(callback)
        hints = {
            "Dịch thử 10 câu": "Dịch tối đa 10 câu đã chọn để kiểm tra chất lượng trước khi dịch toàn bộ.",
            "Dịch các câu đã chọn": "Dịch tiếp những câu chưa dịch; bản dịch được tự lưu sau mỗi lô.",
            "Xuất để chép…": "Tạo thư mục files/ để chép vào game. Không thay đổi game đang cài.",
            "Cài vào game": "Thay file game bằng bản dịch đã kiểm tra và lưu backup. Đóng game trước khi cài.",
            "Khôi phục": "Trả file game về trạng thái trước khi cài bản dịch; giữ bản dịch trong project.",
            "Chọn kết quả lọc": "Đánh dấu dịch tất cả các câu đang hiện trong bộ lọc.",
            "Bỏ chọn kết quả": "Bỏ đánh dấu dịch các câu đang hiện; không xóa bản dịch.",
            "Lưu project": "Lưu danh sách câu, bản dịch và đường dẫn backup để tiếp tục lần sau.",
        }
        if text in hints:
            button.setToolTip(hints[text])
            self.action_buttons[text] = button
        return button

    def update_actions(self):
        project = self.project
        selected = bool(project and any(e.enabled for e in project.entries))
        translated = bool(project and any(e.enabled and e.translation for e in project.entries))
        available = {
            "Dịch thử 10 câu": selected, "Dịch các câu đã chọn": selected,
            "Xuất để chép…": translated, "Cài vào game": translated,
            "Khôi phục": bool(project and project.applied_patch),
            "Chọn kết quả lọc": bool(project), "Bỏ chọn kết quả": bool(project),
            "Lưu project": bool(project),
        }
        for name, enabled in available.items():
            self.action_buttons[name].setEnabled(enabled and not self.busy)

    @Slot(str)
    def error(self, message):
        self.log.appendPlainText(message)
        self.status.setText("Thao tác chưa hoàn tất. Bản dịch đã lưu được giữ; xem Kiểm tra / Khôi phục để biết chi tiết.")
        if "API HTTP" in message:
            self.verified_api = None
            self.api_status.setText(message)
        QMessageBox.warning(self, "ToolVH", message)

    def choose_game(self):
        path = QFileDialog.getExistingDirectory(self, "Chọn thư mục game", self.game_path.text())
        if path:
            self.game_path.setText(path)

    def load_project(self, path):
        try:
            project = Project.load(path)
            self.project_path = Path(path)
            self.set_project(project)
            self.dirty = False
            self.remember_project()
            self.tabs.setCurrentWidget(self.workspace_page)
        except Exception as exc:
            self.error(str(exc))

    def maybe_save(self):
        if not self.dirty:
            return True
        response = QMessageBox.question(self, "Lưu tiến độ", "Lưu thay đổi của project hiện tại?",
                                        QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if response == QMessageBox.Cancel:
            return False
        return self.save_project() if response == QMessageBox.Save else True

    def open_project(self):
        if not self.maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Mở project", "", "ToolVH (*.toolvh.json);;JSON (*.json)")
        if path:
            self.load_project(path)

    def sync_settings(self):
        if not self.project:
            return
        glossary = {}
        for line in self.glossary.toPlainText().splitlines():
            if not line.strip():
                continue
            if "=" not in line:
                raise ValueError("Thuật ngữ phải có dạng: từ gốc = bản dịch")
            key, value = line.split("=", 1)
            if not key.strip() or not value.strip():
                raise ValueError("Thuật ngữ và bản dịch không được để trống.")
            glossary[key.strip()] = value.strip()
        self.project.glossary = glossary
        self.project.instructions = self.instructions.toPlainText()
        self.project.preserve_names = self.preserve_names.isChecked()
        self.project.protected_names = [s.strip() for s in self.protected_names.toPlainText().splitlines() if s.strip()]
        self.project.game_context = self.game_context.toPlainText().strip()

    def save_project(self):
        if not self.project:
            return False
        try:
            self.sync_settings()
            if not self.project_path:
                path, _ = QFileDialog.getSaveFileName(self, "Lưu project", "game.toolvh.json", "ToolVH (*.toolvh.json)")
                if not path:
                    return False
                self.project_path = Path(path)
            self.project.save(self.project_path)
            self.dirty = False
            self.remember_project()
            self.status.setText(f"Đã lưu: {self.project_path}")
            return True
        except Exception as exc:
            self.error(str(exc))
            return False

    def set_project(self, project):
        self.project = project
        audit(project)
        self.game_path.setText(project.root)
        self.instructions.setPlainText(project.instructions)
        self.preserve_names.setChecked(project.preserve_names)
        self.protected_names.setPlainText("\n".join(project.protected_names))
        self.game_context.setPlainText(project.game_context)
        self.glossary.setPlainText("\n".join(f"{k} = {v}" for k, v in project.glossary.items()))
        self.model.set_entries(project.entries)
        self.search.clear()
        self.state.setCurrentText("Đã chọn" if any(e.enabled for e in project.entries) else "Tất cả")
        self.update_filter()
        self.files.clear()
        all_files = QTreeWidgetItem(["Tất cả dữ liệu", str(len(project.entries))])
        all_files.setData(0, Qt.UserRole, "")
        self.files.addTopLevelItem(all_files)
        for record in sorted(project.files, key=lambda f: (-f.count, f.path)):
            if record.count or record.note:
                item = QTreeWidgetItem([record.path, str(record.count) if record.count else "—"])
                item.setData(0, Qt.UserRole, record.path)
                item.setToolTip(0, record.note or record.path)
                self.files.addTopLevelItem(item)
        self.files.setCurrentItem(all_files)
        self.log.setPlainText("Engine: " + ", ".join(project.engines) + "\n\n" + "\n".join(
            f"{f.path} — {f.count} text. {f.note}" for f in project.files if f.count or f.note))
        self.update_metrics()
        if not any(e.enabled for e in project.entries):
            self.status.setText("Chưa tìm được text English dùng được; đang hiện tất cả ứng viên để duyệt. Xem Báo cáo / Cài đặt để biết tài nguyên bị chặn.")

    def update_metrics(self):
        self.update_actions()
        if self.project:
            selected = sum(e.enabled for e in self.project.entries)
            translated = sum(e.enabled and bool(e.translation) for e in self.project.entries)
            errors = sum(bool(e.error) for e in self.project.entries)
            self.metrics.setText(f"{' · '.join(self.project.engines)}     |     {len(self.project.entries):,} text ứng viên     |     "
                                 f"{selected:,} đã chọn     |     {translated:,} đã dịch     |     {errors:,} lỗi")
            if self.project.scan_revision < 2:
                self.metrics.setText("Project dùng bộ quét cũ — bấm Quét dữ liệu lại để xác định đúng tiếng Anh; giữ bản dịch khớp nguồn/vị trí.")
            next_step = "Duyệt ứng viên và chọn câu cần dịch." if not selected else ("Chọn dịch vụ dịch rồi dịch thử 10 câu." if not translated else ("Dịch tiếp các câu còn lại hoặc xuất bản vá hiện có." if translated < selected else "Xuất để chép; đóng game trước khi cài và kiểm tra hiển thị."))
            self.home_summary.setText(f"{Path(self.project.root).name} • {translated:,}/{selected:,} vị trí đã dịch • {selected - translated:,} còn lại\n"
                                      f"Project: {self.project_path or 'Chưa lưu — bấm Lưu project trước khi dịch'}\nBước tiếp theo: {next_step}")
            self.completion.setValue(round(100 * translated / selected) if selected else 0)
            self.support_report.setText(report_text(self.project))
            coverage = compatibility_report(self.project)
            blocked = len({f['path'] for f in coverage['files_needing_attention']})
            self.scan_notice.setText(
                f'{blocked} tài nguyên cần kiểm tra thêm; có thể còn text chưa trích xuất. <a style="color:#b6a7ff" href="report">Xem báo cáo hỗ trợ</a>' if blocked else
                'Đã quét dữ liệu; chưa khẳng định tìm hết text. Dịch thử rồi kiểm tra font và bố cục trong game.')

    def select_file(self, current, previous):
        self.proxy.file = current.data(0, Qt.UserRole) if current else ""
        self.update_filter()
        self.select_entry()

    def update_filter(self, *args):
        self.proxy.text = self.search.text().casefold()
        self.proxy.state = self.state.currentText()
        self.proxy.invalidateFilter()
        count = self.proxy.rowCount()
        self.filter_hint.setText(f"Đang hiển thị {count:,} câu trong bộ lọc." if count else
            'Không có câu khớp bộ lọc. <a style="color:#71e0c4" href="all">Hiện tất cả câu</a> hoặc xem báo cáo sau khi quét.')

    def clear_filters(self, *_):
        self.search.clear()
        self.state.setCurrentText("Tất cả")
        self.files.setCurrentItem(self.files.topLevelItem(0))
        self.proxy.file = ""
        self.update_filter()

    def current_entry(self):
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return None
        index = self.proxy.mapToSource(indexes[0])
        return self.model.entries[index.row()] if index.isValid() and 0 <= index.row() < len(self.model.entries) else None

    def select_entry(self, *args):
        if self.busy:
            return
        entry = self.current_entry()
        self.editor_entry = entry
        self.source.setPlainText(entry.source if entry else "")
        self.target.setPlainText(entry.translation if entry else "")
        self.context.setText(f"{entry.file}  /  {entry.context}" if entry else "Chọn một dòng để chỉnh bản dịch.")
        self.validation.setText(entry.error if entry else "")

    def save_entry(self):
        entry = self.current_entry()
        if not entry:
            return
        if entry is not getattr(self, "editor_entry", None):
            self.select_entry()
            return
        text = normalize_translation(self.target.toPlainText())
        try:
            self.sync_settings()
        except ValueError as exc:
            return self.error(str(exc))
        errors = validate_entry(self.project, entry, text) if text else []
        if errors:
            self.validation.setText(" ".join(errors))
            return
        entry.translation, entry.error = text, ""
        self.target.setPlainText(text)
        self.model.refresh()
        self.on_edit()
        self.validation.setText("Đã cập nhật câu dịch." + (" Bản dịch dài hơn 1,7 lần; kiểm tra bố cục." if len(text) > max(30, len(entry.source) * 1.7) else ""))

    def on_edit(self):
        self.dirty = self.project is not None
        self.update_metrics()

    def enable_visible(self, enabled):
        entries = [self.model.entries[self.proxy.mapToSource(self.proxy.index(i, 0)).row()] for i in range(self.proxy.rowCount())]
        for entry in entries:
            entry.enabled = enabled
        self.model.refresh()
        self.update_filter()
        self.on_edit()

    def start_scan(self):
        if not self.maybe_save():
            return
        root, deep, max_mb = self.game_path.text(), self.deep.isChecked(), self.max_mb.value()
        if self.project and (self.project.applied_patch or self.project.font_patches) and Path(root).resolve() == Path(self.project.root).resolve():
            return self.error("Khôi phục bản gốc trước khi quét lại game đã cài bản dịch.")
        previous = self.project
        def success(project):
            from .scanner import carry_translations
            carry_translations(previous, project)
            self.project_path = None
            self.set_project(project)
            self.dirty = True
        self.run_job(lambda progress: scan(root, progress, self.stop.is_set, deep, max_mb), success)

    def change_provider(self, index):
        if self.active_provider:
            self.profiles[self.active_provider] = (self.api_config(provider=self.active_provider), self.remember_key.isChecked())
        provider = self.provider.currentData()
        self.active_provider = provider
        default_key = environment_key(provider)
        config, remember = self.profiles.get(provider, (APIConfig(provider=provider, base_url=PROVIDERS[provider][1], api_key=default_key), False))
        self.endpoint.setText(config.base_url)
        self.endpoint.setReadOnly(provider in ("gemini", "google-web", "groq", "openrouter-free"))
        self.api_model.clear()
        self.api_model.setEditText(config.model)
        self.api_key.setText(config.api_key)
        self.show_key.setChecked(False)
        self.remember_key.setChecked(remember)
        self.batch_size.setValue(config.batch_size)
        if provider == "ollama":
            self.batch_size.setValue(min(config.batch_size, 5))
        self.delay_seconds.setValue(config.delay_seconds)
        if provider in ("groq", "openrouter-free") and provider not in self.profiles:
            self.batch_size.setValue(5)
            self.delay_seconds.setValue(4)
        self.json_mode.setChecked(config.json_mode)
        web = provider == "google-web"
        for widget in (self.api_key, self.show_key, self.remember_key, self.api_model, self.batch_size, self.json_mode):
            widget.setEnabled(not web)
        if web:
            self.api_key.clear()
            self.remember_key.setChecked(False)
            self.api_model.setEditText("Không cần model")
            self.batch_size.setValue(1)
            self.delay_seconds.setValue(max(2, config.delay_seconds))
        if provider == "gemini":
            self.api_help.setText('1. Mở <a style="color:#71e0c4" href="https://aistudio.google.com/api-keys">Google AI Studio → API keys</a> và tạo/copy key. '
                                 '2. Dán key bên dưới. 3. Tải danh sách model, chọn model dịch văn bản và Kiểm tra kết nối. '
                                 'Kiểm tra sẽ gửi một câu mẫu; danh sách model chưa bảo đảm tài khoản còn quota. '
                                 'HTTP 402: mở AI Studio → Billing kiểm tra số dư Prepay. Key đúng không bảo đảm tài khoản có credits.')
        elif provider == "groq":
            self.api_help.setText('Groq có Free Plan với hạn mức tùy model/tài khoản. '
                'Tạo key tại <a style="color:#71e0c4" href="https://console.groq.com/keys">Groq Console → API keys</a>, '
                'dán key, Tải danh sách model rồi Kiểm tra kết nối. '
                'Tool không xác định được tài khoản đang Free hay trả phí; kiểm tra Plan/Billing trong Groq trước khi dịch. '
                'Chạm 429: kiểm tra Limits, giảm lô hoặc tiếp tục khi quota phục hồi. Không tự chuyển dịch vụ/model.')
        elif provider == "openrouter-free":
            self.api_help.setText('Tạo key tại <a style="color:#71e0c4" href="https://openrouter.ai/settings/keys">OpenRouter → Keys</a>, '
                'dán key rồi Tải danh sách model. Preset chỉ hiện model :free có giá input/output bằng 0 và đầu ra text; chặn chọn model trả phí. '
                'Free có giới hạn theo tài khoản, model có thể bận hoặc ngừng cung cấp. '
                'Tắt JSON mode nếu model không hỗ trợ; kết quả vẫn phải đúng JSON. Kiểm tra kết nối dùng một lượt gọi dịch.')
        elif provider == "google-web":
            self.api_help.setText("Google Dịch web: không cần key/model. Dịch English → Vietnamese, lưu từng câu, nghỉ tối thiểu 2 giây mỗi yêu cầu. "
                                 "Cache theo project giúp giảm gọi lại đoạn trùng; tự chia đoạn dài tại điểm ngắt. Không dùng văn phong/ngữ cảnh của project; cần duyệt lại từ đa nghĩa. "
                                 "Endpoint web thử nghiệm có thể bị giới hạn hoặc thay đổi; không bảo đảm miễn phí vô hạn. "
                                 "Tên riêng và glossary được bảo vệ cục bộ. Dịch lại bỏ qua cache; có nút Xóa cache Google Dịch. Bấm Kiểm tra kết nối rồi Dịch thử 10 câu.")
        elif provider == "ollama":
            self.api_help.setText("Khởi động Ollama, Tải danh sách model rồi chọn model trên máy. URL: http://localhost:11434. "
                                  "Tool dùng tối đa 5 câu/lô, tắt suy luận, context 8192 và chờ tối thiểu 300 giây khi tải model. "
                                  "Bật JSON mode để ràng buộc cấu trúc. Lô/câu sai được thử riêng; nếu mất token, phục hồi từng đoạn chữ tối đa 64 đoạn, chia lô nhỏ. "
                                  "Câu vẫn sai được giữ lỗi, không bỏ kiểm tra. Dịch thử 10 câu và duyệt chất lượng trước khi dịch cả game.")
        elif provider == "openai-responses":
            self.api_help.setText("Nhập Base URL của API Responses (ví dụ https://api.openai.com/v1), model và key của nhà cung cấp. "
                                  "Có thể dán URL kết thúc bằng /responses; tool tự chuẩn hóa. Tải danh sách model rồi Kiểm tra kết nối. "
                                  "Gửi ngữ cảnh, hướng dẫn và token bảo vệ tên; chỉ nhận response hoàn tất. API có thể mất phí theo nhà cung cấp.")
        else:
            self.api_help.setText("Nhập Base URL, model và key của nhà cung cấp. URL dừng ở /v1 hoặc đường dẫn API tương thích, không thêm /chat/completions. URL kết thúc /responses được tự nhận diện dùng Responses.")
        self.api_changed()

    def api_config(self, provider=None):
        return APIConfig(provider or self.provider.currentData(), self.endpoint.text().strip(),
                         self.api_model.currentText().strip(), self.api_key.text().strip(),
                         self.batch_size.value(), json_mode=self.json_mode.isChecked(),
                         delay_seconds=self.delay_seconds.value())

    def api_changed(self, *args):
        self.verified_api = None
        self.api_status.setText("Chưa kiểm tra cấu hình này • Chọn model rồi bấm Kiểm tra kết nối.")
        if self.provider.currentData() == "google-web":
            self.api_status.setText("Không cần key/model • Bấm Kiểm tra kết nối. Endpoint web thử nghiệm có thể bị giới hạn.")

    def load_api_settings(self):
        try:
            data = self.settings_store.load()
            self.profiles, self.recent = data["profiles"], data["recent"]
            selected = data["provider"] if data["provider"] in PROVIDERS else "gemini"
            if data["key_errors"]:
                self.log.appendPlainText("Không mở được key cũ của: " + ", ".join(data["key_errors"]) + ". Hãy dán lại key.")
        except Exception:
            selected = "gemini"
            self.log.appendPlainText("Không đọc được cấu hình đã lưu. Hãy cấu hình API lại.")
        self.provider.blockSignals(True)
        self.provider.setCurrentIndex(self.provider.findData(selected))
        self.provider.blockSignals(False)
        self.change_provider(self.provider.currentIndex())
        for path in self.recent:
            self.recent_combo.addItem(path, path)

    def save_api_settings(self):
        try:
            config = self.api_config()
            Client(config, require_model=False)
            self.profiles[config.provider] = (config, self.remember_key.isChecked())
            self.settings_store.save(config.provider, self.profiles, self.recent)
            self.api_status.setText("Đã lưu cấu hình. " + ("Key được mã hóa cho tài khoản Windows hiện tại." if self.remember_key.isChecked() else "Key chỉ giữ trong phiên này.") + " Bấm Kiểm tra kết nối để xác nhận dịch được.")
        except Exception as exc:
            self.error(str(exc))

    def forget_key(self):
        self.api_key.clear()
        self.remember_key.setChecked(False)
        self.profiles[self.active_provider] = (self.api_config(), False)
        try:
            self.settings_store.save(self.active_provider, self.profiles, self.recent)
            self.api_status.setText("Đã xóa key đã nhớ của dịch vụ hiện tại.")
        except Exception as exc:
            self.error(str(exc))

    def fetch_models(self):
        if self.provider.currentData() == "google-web":
            self.api_status.setText("Google Dịch web không dùng model. Bấm Kiểm tra kết nối để thử dịch.")
            return
        try:
            client = Client(self.api_config(), require_model=False)
        except Exception as exc:
            return self.error(str(exc))
        previous = self.api_model.currentText()
        def success(models):
            self.api_model.clear()
            self.api_model.addItems(models)
            self.api_model.setCurrentText(previous if previous in models else models[0] if models else "")
            self.api_status.setText(f"Đã tìm thấy {len(models)} model. Chọn model rồi Kiểm tra kết nối để xác nhận quyền dịch và quota." if models else "Không tìm thấy model dịch văn bản. Kiểm tra project/key hoặc nhập tên model trực tiếp.")
        self.run_job(lambda progress: client.list_models(self.stop), success)

    def test_api(self):
        try:
            config = self.api_config()
            client = Client(config)
        except Exception as exc:
            return self.error(str(exc))
        def success(translation):
            self.verified_api = (config.provider, config.base_url, config.model, config.api_key)
            self.api_status.setText(f"Kết nối và sinh bản dịch thành công • {config.model}\nStart game → {translation}")
        self.run_job(lambda progress: client.test_connection(self.stop), success)

    def start_translation(self, checked=False, limit=None, overwrite=False, only_errors=False):
        if not self.project:
            return self.error("Hãy quét game hoặc mở project trước.")
        if self.project.scan_revision < 2:
            return self.error("Bấm Quét dữ liệu lại trước khi dịch project cũ. Tool sẽ giữ bản dịch có cùng nguồn và vị trí.")
        try:
            config = self.api_config()
            Client(config)
        except Exception as exc:
            self.tabs.setCurrentWidget(self.settings_page)
            return self.error(str(exc))
        if only_errors:
            self.sync_settings()
            audit(self.project)
            self.model.refresh()
            self.update_metrics()
        if not any(e.enabled and (bool(e.error) if only_errors else (overwrite or not e.translation)) for e in self.project.entries):
            return QMessageBox.information(self, "Dịch tiếng Việt", "Không còn câu lỗi trong các mục đã chọn." if only_errors else "Không còn câu chưa dịch trong các mục đã chọn.")
        if overwrite and QMessageBox.question(self, "Dịch lại", "Dịch lại mọi câu đang được đánh dấu chọn? Tool lưu bản sao project trước khi bắt đầu và giữ câu cũ nếu dịch thất bại.") != QMessageBox.Yes:
            return
        if not self.save_project():
            return
        project, path = self.project, self.project_path
        if overwrite or only_errors:
            try:
                from datetime import datetime
                backup = path.with_name(path.stem + ".before-retranslate-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + path.suffix)
                project.save(backup)
            except Exception as exc:
                return self.error(str(exc))
        def work(progress):
            from .patching import preflight
            progress("Kiểm tra đọc/ghi trước khi gửi text tới dịch vụ dịch…")
            preflight(project, progress, self.stop.is_set)
            return translate(project, config, progress, self.stop, lambda: project.save(path), limit=limit, overwrite=overwrite, only_errors=only_errors)
        self.run_job(work,
                     lambda count: self.translation_finished(count))

    def optimize_translation_speed(self):
        provider = self.provider.currentData()
        if provider == "google-web":
            batch, delay = 1, 2
        elif provider == "ollama":
            batch, delay = 5, 0
        elif provider in ("groq", "openrouter-free"):
            batch, delay = 10, 2
        else:
            batch, delay = 40, 0
        self.batch_size.setValue(batch)
        self.delay_seconds.setValue(delay)
        self.api_status.setText(f"Đã đặt {batch} câu/lô, nghỉ {delay} giây. Ngữ cảnh và kiểm tra tên/biến vẫn được giữ. "
                                "Tốc độ phụ thuộc model/quota; nếu bị cắt hoặc 429, giảm lô/tăng thời gian nghỉ. Chưa gọi API.")

    def choose_google_free(self):
        self.provider.setCurrentIndex(self.provider.findData("google-web"))
        self.tabs.setCurrentWidget(self.settings_page)
        self.status.setText("Đã chọn Google Dịch web không cần key. Kiểm tra kết nối và dịch thử trước; endpoint có thể bị giới hạn.")

    def clear_google_cache(self):
        if not self.project:
            return self.error("Hãy quét game hoặc mở project trước.")
        count = len(self.project.google_web_cache)
        self.project.google_web_cache.clear()
        self.on_edit()
        self.status.setText(f"Đã xóa {count} đoạn cache Google Dịch. Bản dịch hiện có được giữ; lưu project để ghi thay đổi.")

    def show_names(self):
        if not self.project:
            return self.error("Hãy quét game hoặc mở project trước.")
        names = inferred_names(self.project)
        QMessageBox.information(self, "Tên nhận diện", "Tên này được bảo vệ khi bật Giữ nguyên tên. Có thể bổ sung ở Giữ thêm tên hoặc ghi bản dịch trong Thuật ngữ.\n\n" + "\n".join(names))

    def audit_translations(self):
        if not self.project:
            return self.error("Hãy mở project trước.")
        try:
            self.sync_settings()
            count = audit(self.project)
            self.on_edit()
            self.model.refresh()
            self.select_entry()
            self.status.setText(f"Phát hiện {count} câu cần sửa biến/tên riêng. Kiểm tra nghĩa lời thoại vẫn cần duyệt thủ công.")
            self.state.setCurrentText("Có lỗi")
            self.tabs.setCurrentIndex(1)
            QMessageBox.information(self, "Kiểm tra bản dịch", f"{count} câu vi phạm quy tắc tên riêng/biến. Bản dịch hiện có được giữ lại. Xem bộ lọc Có lỗi; chọn các câu cần sửa rồi dùng Dịch lại ở Cấu hình.")
        except Exception as exc:
            self.error(str(exc))

    def translation_finished(self, count):
        self.dirty = False
        self.model.refresh()
        self.update_metrics()
        self.select_entry()
        self.status.setText(f"Đã lưu {count:,} vị trí dịch trong lượt này. Có thể xem bộ lọc Đã dịch hoặc Có lỗi.")

    def check_installability(self):
        if not self.project:
            return self.error("Hãy quét game hoặc mở project trước.")
        from .patching import preflight
        def success(result):
            self.status.setText(result["status"])
            summary = result["scan_summary"]
            missing = summary["files_without_extracted_text"]
            details = (f"Đã kiểm tra {len(result['checked_files'])} file và {result['selected_entries']} câu.\n"
                       f"Có {summary['candidate_entries']} text ứng viên; {summary['unselected_entries']} mục chưa chọn.\n"
                       f"{len(missing)} file được ghi nhận chưa trích xuất được text (có thể không chứa text).\n\n")
            details += "\n".join(f"{record['path']}: {record['note'] or 'Không tìm thấy text'}" for record in missing[:8])
            if len(missing) > 8:
                details += "\n… Xem đầy đủ trong báo cáo hỗ trợ engine hoặc CLI check."
            QMessageBox.information(self, "Khả năng cài", details + "\n\n" + result["status"])
        self.run_job(lambda progress: preflight(self.project, progress, self.stop.is_set), success)

    def open_error_logs(self):
        directory = self.settings_store.path.parent / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def export_diagnostics(self):
        if not self.project:
            return self.error("Hãy quét game hoặc mở project trước.")
        path, _ = QFileDialog.getSaveFileName(self, "Xuất báo cáo hỗ trợ engine", "game-diagnostics.json", "JSON (*.json)")
        if path:
            try:
                from .model import atomic_write
                atomic_write(Path(path), json.dumps(compatibility_report(self.project), ensure_ascii=False, indent=2).encode("utf-8"))
                self.status.setText(f"Đã xuất báo cáo: {path}")
            except Exception as exc:
                self.error(str(exc))

    def export_csv(self):
        if not self.project:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Xuất text", "translations.csv", "CSV (*.csv)")
        if path:
            try:
                export_csv(self.project, path)
                self.status.setText(f"Đã xuất {len(self.project.entries):,} dòng: {path}")
            except Exception as exc:
                self.error(str(exc))

    def import_csv(self):
        if not self.project:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Nhập bản dịch", "", "CSV (*.csv)")
        if path:
            try:
                count = import_csv(self.project, path)
                self.model.refresh()
                self.on_edit()
                self.select_entry()
                self.status.setText(f"Đã nhập {count:,} dòng.")
            except Exception as exc:
                self.error(str(exc))

    def check_patch_translations(self):
        try:
            self.sync_settings()
            repaired = repair_protected_names(self.project)
            audit(self.project)
            self.on_edit()
            self.model.refresh()
            failed = sum(e.enabled and bool(e.error) for e in self.project.entries)
            if repaired:
                self.log.appendPlainText(f"Đã trả {repaired} mục tên/thuật ngữ về đúng quy tắc; bản dịch lời thoại được giữ.")
            if failed:
                self.search.clear()
                self.state.setCurrentText("Có lỗi")
                self.tabs.setCurrentIndex(1)
                self.error(f"Còn {failed} mục đã chọn vi phạm tên/biến hoặc chưa phục hồi. Đã đánh dấu toàn bộ trong bộ lọc Có lỗi. Dùng Cấu hình → Thử lại câu lỗi, rồi cài lại. Tên đứng riêng đã được sửa theo quy tắc; lưu project để giữ thay đổi.")
                return False
            return True
        except Exception as exc:
            self.error(str(exc))
            return False

    def start_export(self):
        if not self.project:
            return
        if self.project.scan_revision < 2:
            return self.error("Bấm Quét dữ liệu lại trước khi xuất bản vá từ project cũ.")
        parent = QFileDialog.getExistingDirectory(self, "Chọn nơi chứa bản vá (ngoài thư mục game)")
        if not parent:
            return
        from datetime import datetime
        destination = Path(parent) / ("ToolVH-patch-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
        from .export_installed import export_copy
        self.run_job(lambda progress: export_copy(self.project, destination, progress),
                     lambda result: QMessageBox.information(self, "Đã xuất bản vá", f"{destination}\n\nĐã dịch {result['translated']} câu; còn thiếu {result['remaining']} câu đã chọn. Bỏ qua {len(result.get('skipped_invalid', []))} bản dịch lỗi (giữ tiếng Anh).\n\nĐóng game, chép toàn bộ nội dung BÊN TRONG files/ vào thư mục gốc game và thay thế file. Giữ cả catalog/bundle nếu có.\nGiữ backup/ để khôi phục. Đọc README.txt trong gói trước khi chép.\n\nChỉ dùng đúng phiên bản game đã quét; bản vá font cần cài riêng."), cancellable=False)

    def apply_current_project(self):
        if not self.project:
            return self.error("Hãy quét game và dịch các câu cần thiết trước.")
        try:
            self.project.require_current_scan()
            if self.project.font_patches:
                raise ValueError("Khôi phục font trước khi cài bản dịch mới; bản dịch đang cài sẽ được giữ.")
            if self.project.applied_patch:
                raise ValueError("Khôi phục bản gốc trước khi cài bản dịch mới.")
        except Exception as exc:
            return self.error(str(exc))
        if not self.check_patch_translations():
            return
        translated = sum(e.enabled and bool(e.translation) for e in self.project.entries)
        if not translated:
            return self.error("Chưa có bản dịch được chọn để cài.")
        if not self.save_project():
            return
        if QMessageBox.question(self, "Cài trực tiếp vào game",
            f"Cài {translated} vị trí đã dịch vào:\n{self.project.root}\n\nĐóng game trước khi cài. Tool sẽ tạo backup để khôi phục.") != QMessageBox.Yes:
            return
        import uuid
        destination = self.settings_store.path.parent / "patches" / uuid.uuid4().hex
        project, path = self.project, self.project_path
        self.run_job(lambda progress: apply_project(project, destination, progress, lambda: project.save(path)),
            lambda result: QMessageBox.information(self, "Đã cài tiếng Việt",
                f"Đã cài {result['files']} file / {result['translated']} vị trí.\nChọn English trong game và kiểm tra font.\nBackup: {result['patch']}"), cancellable=False)

    def restore_current_project(self):
        if not self.project or not self.project.applied_patch:
            return self.error("Project chưa có bản vá đã cài; dùng Báo cáo / Cài đặt → Khôi phục bản gốc nếu có thư mục bản vá riêng.")
        if not self.save_project():
            return
        if QMessageBox.question(self, "Khôi phục game", f"Đóng game rồi khôi phục bản gốc tại:\n{self.project.root}") != QMessageBox.Yes:
            return
        project, path = self.project, self.project_path
        self.run_job(lambda progress: restore_project(project, lambda: project.save(path)),
            lambda count: QMessageBox.information(self, "Đã khôi phục", f"Đã khôi phục {count} file game."), cancellable=False)

    def apply_patch(self, restore):
        patch = QFileDialog.getExistingDirectory(self, "Chọn thư mục bản vá có manifest.json")
        if not patch:
            return
        game = QFileDialog.getExistingDirectory(self, "Chọn thư mục game cần áp dụng", self.game_path.text())
        if not game:
            return
        action = "Khôi phục bản gốc" if restore else "Cài bản vá"
        if QMessageBox.question(self, action, f"Đã đóng game?\n\n{action} vào:\n{game}\n\nTool sẽ kiểm tra phiên bản file trước khi ghi.") != QMessageBox.Yes:
            return
        try:
            manifest = json.loads((Path(patch) / "manifest.json").read_text(encoding="utf-8"))
            same_game = self.project and Path(self.project.root).resolve() == Path(game).resolve()
            is_font = manifest.get("kind") == "font"
            if same_game and self.project.font_patches and not is_font:
                return self.error("Khôi phục font trước khi cài hoặc khôi phục bản dịch.")
            if same_game and is_font:
                if not self.save_project():
                    return
                from .fonts import apply_font_patch, restore_font
                project, path = self.project, self.project_path
                if restore and project.font_patches:
                    if Path(project.font_patches[-1]).resolve() != Path(patch).resolve():
                        return self.error("Khôi phục bản vá font mới nhất trước để đúng thứ tự backup.")
                    work = lambda progress: restore_font(project, lambda: project.save(path))
                elif not restore:
                    work = lambda progress: apply_font_patch(project, patch, lambda: project.save(path))
                else:
                    work = lambda progress: install_patch(patch, game, True)
            else:
                work = lambda progress: install_patch(patch, game, restore)
            self.run_job(work, lambda count: QMessageBox.information(self, action, f"Hoàn tất {count} file."), cancellable=False)
        except Exception as exc:
            self.error(str(exc))

    def open_font_manager(self):
        if not self.project:
            return self.error("Hãy quét hoặc mở project game trước.")
        dialog = QDialog(self)
        dialog.setWindowTitle("ToolVH · Kiểm tra và sửa font tiếng Việt")
        dialog.resize(1100, 650)
        layout = QVBoxLayout(dialog)
        note = QLabel("Quét font → chọn font thiếu ký tự → tạo/cài bản vá. Ori: bổ sung glyph SDF vào font bitmap đã xác nhận.\n"
                      "Font nguồn lấy từ máy bạn hoặc TTF/OTF tự chọn. Font icon được giữ nguyên. TMP, UE, Godot đóng gói cần adapter riêng; chưa sửa mọi game tự động.")
        note.setWordWrap(True)
        layout.addWidget(note)
        tree = QTreeWidget()
        tree.setHeaderLabels(["Font / file", "Loại", "Ký tự thiếu", "Hỗ trợ"])
        tree.setColumnWidth(0, 320)
        tree.setColumnWidth(1, 130)
        tree.setColumnWidth(2, 250)
        layout.addWidget(tree, 1)
        source_row = QHBoxLayout()
        source = QLineEdit()
        source.setPlaceholderText("Để trống: chọn font có tiếng Việt từ Windows; có thể chọn TTF/OTF khác")
        source_row.addWidget(source, 1)
        def choose_source():
            path, _ = QFileDialog.getOpenFileName(dialog, "Chọn font có tiếng Việt", "", "Font (*.ttf *.otf)")
            if path:
                source.setText(path)
        source_row.addWidget(self.button("Chọn TTF/OTF…", choose_source))
        layout.addLayout(source_row)
        status = QLabel("Bấm Quét font. Tool kiểm tra bộ ký tự tiếng Việt và ký tự của bản dịch đã chọn.")
        status.setWordWrap(True)
        layout.addWidget(status)
        state = {"report": None, "root": self.project.root}
        self.font_state = state
        self.font_tree = tree
        def scan_fonts():
            if self.busy:
                return
            from .fonts import diagnose
            if self.project.root != state["root"]:
                return self.error("Game đã đổi; mở lại cửa sổ font.")
            def finished(report):
                state["report"] = report
                tree.clear()
                has_english_bindings = any(r.get("english_usage") for r in report["fonts"])
                for record in report["fonts"]:
                    item = QTreeWidgetItem([record["name"] + " / " + record["file"], record["kind"], record["missing"], record["note"]])
                    item.setData(0, Qt.UserRole, record)
                    item.setToolTip(2, record["missing"] or "Không thiếu ký tự trong bộ kiểm tra.")
                    if record["repairable"]:
                        default_fix = record["missing"] and record["kind"] == "ori-bitmap" and (not has_english_bindings or record.get("english_usage"))
                        item.setCheckState(0, Qt.Checked if default_fix else Qt.Unchecked)
                    tree.addTopLevelItem(item)
                english = [r for r in report["fonts"] if r.get("english_usage") and r["repairable"]]
                coverage = f" Font English: {len(english)}, còn thiếu ký tự: {sum(bool(r['missing']) for r in english)}." if english else ""
                status.setText(f"{len(report['fonts'])} font đọc được." + coverage + " " + " | ".join(report["notes"][:4]))
            project = self.project
            self.run_job(lambda progress: diagnose(project, progress, self.stop), finished)
        def build_font(install):
            if self.busy:
                return
            report = state["report"]
            if not report:
                return self.error("Quét font trước khi tạo bản vá.")
            if self.project.root != state["root"]:
                return self.error("Game đã đổi; quét font lại.")
            selected = [tree.topLevelItem(i).data(0, Qt.UserRole) for i in range(tree.topLevelItemCount())
                        if tree.topLevelItem(i).checkState(0) == Qt.Checked]
            if not selected:
                return self.error("Chọn ít nhất một font hỗ trợ sửa.")
            if not self.save_project():
                return
            import uuid
            if install:
                if QMessageBox.question(dialog, "Cài font vào game", "Đóng game trước khi cài font. Tool tạo bản vá và backup trạng thái hiện tại, giữ bản dịch đang cài. Tiếp tục?") != QMessageBox.Yes:
                    return
                destination = self.settings_store.path.parent / "font-patches" / uuid.uuid4().hex
            else:
                parent = QFileDialog.getExistingDirectory(dialog, "Chọn nơi chứa bản vá font, ngoài thư mục game")
                if not parent:
                    return
                destination = Path(parent) / ("ToolVH-font-" + uuid.uuid4().hex[:12])
            from .fonts import export_font_patch, apply_font_patch
            project, path = self.project, self.project_path
            font_source = source.text().strip() or None
            def work(progress):
                result = export_font_patch(project, report, selected, destination, font_source, progress)
                if install:
                    result["installed"] = apply_font_patch(project, destination, lambda: project.save(path))
                return result
            def finished(result):
                state["report"] = None  # A second repair requires a fresh scan/hash check.
                status.setText(f"{'Đã cài' if install else 'Đã tạo'} bản vá font: {destination}. Hãy thử menu và hội thoại trong game.")
                self.dirty = False
                QMessageBox.information(dialog, "Bản vá font", status.text())
            self.run_job(work, finished, cancellable=False)
        def undo_font():
            if self.busy:
                return
            if self.project.root != state["root"]:
                return self.error("Game đã đổi; mở lại cửa sổ font.")
            if not self.project.font_patches:
                return self.error("Project chưa ghi nhận bản vá font. Dùng Khôi phục bản gốc… với thư mục bản vá riêng nếu cài bên ngoài.")
            if not self.save_project():
                return
            if QMessageBox.question(dialog, "Khôi phục font", "Đóng game rồi khôi phục bản vá font gần nhất? Bản dịch trước khi sửa font được giữ lại.") != QMessageBox.Yes:
                return
            from .fonts import restore_font
            project, path = self.project, self.project_path
            def finished(count):
                state["report"] = None
                status.setText(f"Đã khôi phục {count} file của bản vá font gần nhất.")
                self.dirty = False
            self.run_job(lambda progress: restore_font(project, lambda: project.save(path)), finished, cancellable=False)
        def normalize_text():
            if self.busy or self.project.root != state["root"]:
                return
            edits = [(e, normalize_translation(e.translation)) for e in self.project.entries if e.translation]
            edits = [(e, text) for e, text in edits if text != e.translation]
            if not edits:
                return QMessageBox.information(dialog, "Unicode", "Bản dịch đã ở dạng NFC; không cần sửa.")
            if not self.save_project():
                return
            try:
                import uuid
                backup = self.project_path.with_name(self.project_path.stem + ".before-unicode-" + uuid.uuid4().hex[:12] + self.project_path.suffix)
                self.project.save(backup)
                for e, text in edits:
                    e.translation = text
                audit(self.project)
                self.on_edit()
                self.model.refresh()
                self.select_entry()
                state["report"] = None
                self.save_project()
                status.setText(f"Đã chuẩn hóa {len(edits)} câu sang NFC, giữ thẻ/biến. Backup: {backup}. Quét font lại; bản dịch trong game cần cài lại nếu dùng dấu kết hợp.")
            except Exception as exc:
                self.error(str(exc))
        actions = QHBoxLayout()
        actions.addWidget(self.button("Quét font", scan_fonts, primary=True))
        actions.addWidget(self.button("Chuẩn hóa Unicode", normalize_text))
        actions.addWidget(self.button("Xuất bản vá font…", lambda: build_font(False)))
        actions.addWidget(self.button("Tạo và cài font", lambda: build_font(True), primary=True))
        actions.addWidget(self.button("Khôi phục font", undo_font))
        actions.addStretch()
        actions.addWidget(self.button("Đóng", dialog.close))
        layout.addLayout(actions)
        self.font_dialog = dialog
        dialog.show()

    def cancel_job(self):
        self.stop.set()
        self.cancel.setEnabled(False)
        self.status.setText("Đang yêu cầu dừng. Chờ thao tác hiện tại kết thúc; tải model local có thể mất vài phút. Bản dịch đã lưu được giữ.")

    def run_job(self, function, success, cancellable=True):
        if self.busy:
            return
        self.busy = True
        self.job_result = None
        self.job_error = None
        self.has_job_result = False
        self.stop.clear()
        self.tabs.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.cancel.setEnabled(cancellable)
        # Show real counts when available; status text describes unknown progress.
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status.setText("Đang xử lý…")
        self.thread = QThread(self)
        self.worker = Worker(function)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.message.connect(self.job_message)
        self.job_callback = success
        self.worker.result.connect(self.job_success)
        self.worker.error.connect(self.job_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.job_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot(object)
    def job_success(self, result):
        # Store signals first; show dialogs only after the native thread stops.
        self.job_result = result
        self.has_job_result = True

    @Slot(str)
    def job_failed(self, message):
        self.job_error = message

    @Slot(str)
    def job_message(self, text):
        self.status.setText(text)
        self.log.appendPlainText(text)
        match = re.match(r"\[(\d+)/(\d+)\]", text)
        if match and int(match[2]) > 0:
            self.progress_bar.setRange(0, int(match[2]))
            self.progress_bar.setValue(int(match[1]))

    @Slot()
    def job_finished(self):
        callback, result, error = self.job_callback, self.job_result, self.job_error
        has_result, stopped = self.has_job_result, self.stop.is_set()
        # finished can arrive before native thread-local cleanup completes.
        self.thread.wait()
        self.worker.function = None
        self.job_result = None
        self.job_error = None
        self.has_job_result = False
        self.thread = None
        self.job_callback = None
        self.busy = False
        self.tabs.setEnabled(True)
        self.open_btn.setEnabled(True)
        self.cancel.setEnabled(False)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0 if error or stopped else 1)
        try:
            self.model.refresh()
            self.update_filter()
            self.update_metrics()
            self.select_entry()
            if error:
                self.error(error)
            elif has_result:
                self.status.setText("Đã dừng tác vụ; các phần đã lưu được giữ." if stopped else "Tác vụ hoàn tất.")
                callback(result)
        except Exception as exc:
            logging.getLogger("toolvh").exception("Task completion failed")
            self.error(str(exc))

    def closeEvent(self, event):
        if self.busy:
            self.status.setText("Tác vụ vẫn đang chạy. Bấm Dừng tác vụ hoặc chờ hoàn tất trước khi đóng.")
            event.ignore()
        elif not self.maybe_save():
            event.ignore()
        else:
            event.accept()


def configure_app(app):
    # Also register the installed font explicitly for offscreen QA and systems
    # where Qt's font enumeration is unavailable. No font is redistributed.
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets/toolvh.svg")))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Segoe UI", 10))


def run(project_path=None, smoke_report=None):
    app = QApplication.instance() or QApplication(sys.argv)
    configure_app(app)
    window = MainWindow(project_path)
    from .crashlog import install
    install(app, window, window.settings_store.path.parent / "logs")
    window.show()
    if smoke_report:
        def finish_smoke():
            from . import __version__
            from .model import atomic_write
            path = Path(smoke_report)
            path.parent.mkdir(parents=True, exist_ok=True)
            image_path = path.with_suffix(".png")
            saved = window.grab().save(str(image_path))
            from .fonts import font_coverage, suggested_font, VIETNAMESE
            font = suggested_font("candara")
            coverage = font_coverage(font)
            window.open_font_manager()
            font_dialog_saved = window.font_dialog.grab().save(str(path.with_name(path.stem + "-fonts.png")))
            window.font_dialog.close()
            atomic_write(path, json.dumps({"version": __version__, "tabs": window.tabs.count(),
                         "providers": [window.provider.itemData(i) for i in range(window.provider.count())],
                         "project_entries": len(window.project.entries) if window.project else 0,
                         "selected_entries": sum(e.enabled for e in window.project.entries) if window.project else 0,
                         "screenshot_saved": saved, "font_dialog_saved": font_dialog_saved,
                         "font_probe": {"vietnamese_supported": VIETNAMESE <= coverage, "source": font.name}, "network_called": False}, indent=2).encode())
            window.dirty = False
            window.close()
            app.quit()
        QTimer.singleShot(300, finish_smoke)
    return app.exec()
