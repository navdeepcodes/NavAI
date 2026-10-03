# PyInstaller spec for Mike on macOS -> dist/Mike.app
#
# The macOS counterpart of mike.spec. Differences that matter:
#   * no Piper runtime and no win32com/comtypes/faster-whisper: on a Mac,
#     speech is `say` + SFSpeechRecognizer (pyobjc), all system-provided;
#   * a BUNDLE step producing Mike.app with an Info.plist carrying the
#     privacy strings macOS shows in its permission prompts;
#   * the platform-dispatched modules (computer/macos, voice/*/macos, ...)
#     are listed explicitly because nothing on the static import graph
#     reaches them.
#
# Build (from the repo root):
#     pyinstaller packaging/mike_macos.spec --noconfirm
import glob
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# Read the version from config/settings.py without importing the package.
VERSION = "0.0.0"
with open(os.path.join(REPO_ROOT, "config", "settings.py"), encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("VERSION"):
            VERSION = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

def repo_modules(*packages):
    """Every module under Mike's own packages, found by walking the disk.

    Not PyInstaller's collect_submodules: that imports the package in a child
    process, and with the repo root off sys.path it returns nothing -- so the
    tools ToolRegistry finds at runtime (browser, system, ide, permissions,
    the terminal tool) were silently left out of the app, and every web
    search failed with "Unknown tool: browser".
    """
    found = []
    for package in packages:
        base = os.path.join(REPO_ROOT, *package.split("."))
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            rel = os.path.relpath(root, REPO_ROOT).replace(os.sep, ".")
            if "__init__.py" in files:
                found.append(rel)
            found.extend(f"{rel}.{f[:-3]}" for f in files
                         if f.endswith(".py") and f != "__init__.py")
    return found


hiddenimports = [
    "computer.macos",
    "voice.recognizer.macos",
    "voice.wake.macos",
    "voice.providers.native",
    "objc",
    "AVFoundation",
    "Speech",
    "Foundation",
    "AppKit",
    "Quartz",
    "pypdf",
    "PySide6.QtPdf",
    *repo_modules("auth", "brain", "computer", "config", "core", "hostplatform",
                  "ide", "installer", "logs", "storage", "tools", "ui", "vision",
                  "voice"),
    *collect_submodules("docx"),
    *collect_submodules("pptx"),
    *collect_submodules("pygments"),
    *collect_submodules("markdown_it"),
]

vsix = glob.glob(os.path.join(REPO_ROOT, "vscode-extension", "mike-bridge-*.vsix"))

analysis = Analysis(
    [os.path.join(REPO_ROOT, "main.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[
        (os.path.join(REPO_ROOT, "packaging", "icon.ico"), "packaging"),
        (os.path.join(REPO_ROOT, "ui", "fonts"), os.path.join("ui", "fonts")),
        (os.path.join(REPO_ROOT, "docs", "legal"), os.path.join("docs", "legal")),
        *[(v, "vscode-extension") for v in vsix],
        *collect_data_files("docx"),
        *collect_data_files("pptx"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest", "_pytest", "pyinstaller", "PyInstaller", "google.genai",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtQuick3D",
        "PySide6.QtMultimediaWidgets", "PySide6.QtDesigner",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
        "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Mike",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="Mike",
)

app = BUNDLE(
    coll,
    name="Mike.app",
    icon=os.path.join(SPECPATH, "Mike.icns"),
    bundle_identifier="com.mikeassistant.app",
    version=VERSION,
    info_plist={
        "CFBundleName": "Mike",
        "CFBundleDisplayName": "Mike",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSUIElement": False,
        "NSHighResolutionCapable": True,
        "NSAppleEventsUsageDescription": (
            "Mike uses this to tell what app is in front of you, so he knows "
            "what you're working on."
        ),
        "NSMicrophoneUsageDescription": (
            "Mike listens for the wake word and for what you say when you talk "
            "to him. Nothing is sent anywhere — recognition happens entirely "
            "on this Mac."
        ),
        "NSSpeechRecognitionUsageDescription": (
            "Mike turns what you say into text using Apple's speech recognition, "
            "on this Mac, so you can talk to him instead of typing."
        ),
    },
)
