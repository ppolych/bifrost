"""Minimal text editor for previewing/editing files opened from the SFTP browser.

`Save` writes back to the file path the editor was opened with; if the file
came from SFTP and has no local path yet (`set_content(..., path=None)`),
`Save` falls back to `Save As`.
"""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


class SimpleHighlighter(QSyntaxHighlighter):
    """Tiny Python-ish highlighter — keywords, strings, comments.

    Intentional scope cap: a full lexer per language is out of scope.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        kw_format = QTextCharFormat()
        kw_format.setForeground(QColor("#569cd6"))
        kw_format.setFontWeight(QFont.Weight.Bold)
        keywords = (
            "def class import from if elif else return for while try except "
            "finally raise with as in is not and or pass break continue lambda "
            "yield None True False"
        ).split()
        for word in keywords:
            self.rules.append((QRegularExpression(rf"\b{word}\b"), kw_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#ce9178"))
        self.rules.append((QRegularExpression(r"'[^']*'"), string_format))
        self.rules.append((QRegularExpression(r'"[^"]*"'), string_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6a9955"))
        self.rules.append((QRegularExpression(r"#[^\n]*"), comment_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class MobaEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: str | None = None
        self._dirty = False

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.toolbar = QToolBar()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save)
        self.save_as_btn = QPushButton("Save As…")
        self.save_as_btn.clicked.connect(self.save_as)
        self.toolbar.addWidget(self.save_btn)
        self.toolbar.addWidget(self.save_as_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; padding: 0 8px;")
        self.toolbar.addWidget(self.status_label)
        self.layout.addWidget(self.toolbar)

        self.editor = QTextEdit()
        self.editor.setFont(QFont("Consolas", 11))
        self.editor.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; border: none;"
        )
        self.editor.textChanged.connect(self._mark_dirty)
        self.highlighter = SimpleHighlighter(self.editor.document())
        self.layout.addWidget(self.editor)

        self._update_status()

    # ----- public API -----

    def set_content(self, text: str, path: str | None = None) -> None:
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)
        self._path = path
        self._dirty = False
        self._update_status()

    def open_path(self, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            QMessageBox.warning(self, "Open failed", f"{path}\n\n{e}")
            log.warning("open failed for %s: %s", path, e)
            return False
        self.set_content(text, path)
        return True

    def save(self) -> bool:
        if not self._path:
            return self.save_as()
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
        except OSError as e:
            QMessageBox.warning(self, "Save failed", f"{self._path}\n\n{e}")
            log.warning("save failed for %s: %s", self._path, e)
            return False
        self._dirty = False
        self._update_status(extra="saved")
        return True

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save file as", self._path or "")
        if not path:
            return False
        self._path = path
        return self.save()

    def path(self) -> str | None:
        return self._path

    def is_dirty(self) -> bool:
        return self._dirty

    # ----- helpers -----

    def _mark_dirty(self):
        self._dirty = True
        self._update_status()

    def _update_status(self, extra: str | None = None) -> None:
        base = os.path.basename(self._path) if self._path else "(unsaved)"
        suffix = " •" if self._dirty else ""
        if extra:
            suffix = f"  ({extra})"
        self.status_label.setText(f"{base}{suffix}")
