import os
import sys

import pytest

# Make sure the repo root is on sys.path so `import core.*` works under pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Run Qt headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    QApplication.setApplicationName("bifrost-tests")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
