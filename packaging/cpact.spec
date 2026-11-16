# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for building a standalone single-file CPACT executable.

Build from the repository root:
    pyinstaller --clean --noconfirm packaging/cpact.spec

Output: dist/cpact (self-contained, no Python required on target systems)
"""
import os

# SPECPATH is provided by PyInstaller (directory containing this spec file)
REPO_ROOT = os.path.dirname(SPECPATH)

block_cipher = None

# Read-only resources bundled at the same relative layout the source tree uses,
# so existing __file__-relative path resolution keeps working when frozen.
resource_trees = [
    Tree(os.path.join(REPO_ROOT, "spec"), prefix="spec",
         excludes=["__pycache__", "*.pyc"]),
    Tree(os.path.join(REPO_ROOT, "tests"), prefix="tests",
         excludes=["__pycache__", "*.pyc"]),
    Tree(os.path.join(REPO_ROOT, "cpact", "scenario_recipe_creator", "icons"),
         prefix=os.path.join("cpact", "scenario_recipe_creator", "icons")),
]

a = Analysis(
    [os.path.join(REPO_ROOT, "main.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Pulled in dynamically by jsonschema at runtime
        "jsonschema_specifications",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev/test-only dependencies not needed at runtime
        "pytest",
        "pytest_html",
        "pytest_metadata",
        "pytest_sugar",
        # CPACT_NO_GUI=1 drops the scenario-creator GUI for a much smaller binary
    ] + (["PyQt5"] if os.environ.get("CPACT_NO_GUI") == "1" else []),
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    *resource_trees,
    [],
    name="cpact",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
