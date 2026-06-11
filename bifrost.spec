# PyInstaller spec for Bifrost Connection Manager.
#
# Build a distributable bundle with:
#   pip install pyinstaller
#   pyinstaller bifrost.spec
#
# Output lands in dist/bifrost/ (onedir — recommended for Qt apps: faster
# startup than onefile and easier to debug missing plugins). On macOS a
# dist/Bifrost.app bundle is produced as well.
#
# `core/icons.py` resolves res/icons relative to its own __file__, which under
# PyInstaller points inside the bundle — so shipping the directory as data at
# the same relative path ("res/icons") is all that's needed; no code changes.

from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["bifrost_app.py"],
    pathex=[],
    binaries=[],
    datas=[("res/icons", "res/icons")],
    # keyring discovers its backends via entry points at runtime; make sure
    # they are all bundled so credential storage works in the frozen app.
    hiddenimports=collect_submodules("keyring.backends"),
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Test-only / never imported by the app.
        "pytest",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="bifrost",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # GUI app — no console window on Windows
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="bifrost",
)

app = BUNDLE(
    coll,
    name="Bifrost.app",
    bundle_identifier="io.github.ppolych.bifrost",
)
