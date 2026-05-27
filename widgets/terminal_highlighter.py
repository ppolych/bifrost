from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import QRegularExpression

class TerminalHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        # 1. IP Addresses
        ip_format = QTextCharFormat()
        ip_format.setForeground(QColor("#ce9178")) # Light Orange
        ip_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((QRegularExpression(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"), ip_format))

        # 2. Status: ERROR (Red)
        error_format = QTextCharFormat()
        error_format.setForeground(QColor("#f44747"))
        error_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((QRegularExpression(r"\b(ERROR|FAILED|FAILURE|CRITICAL|SEVERE)\b"), error_format))

        # 3. Status: WARNING (Yellow)
        warn_format = QTextCharFormat()
        warn_format.setForeground(QColor("#cca700"))
        self.highlighting_rules.append((QRegularExpression(r"\b(WARN|WARNING|ATTENTION)\b"), warn_format))

        # 4. Status: SUCCESS/OK (Green)
        success_format = QTextCharFormat()
        success_format.setForeground(QColor("#6a9955"))
        self.highlighting_rules.append((QRegularExpression(r"\b(SUCCESS|OK|CONNECTED|COMPLETED|ONLINE)\b"), success_format))

        # 5. Dates/Times
        date_format = QTextCharFormat()
        date_format.setForeground(QColor("#808080")) # Gray
        self.highlighting_rules.append((QRegularExpression(r"\b\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\b"), date_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)
