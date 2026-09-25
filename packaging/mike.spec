# PyInstaller spec for Mike on Windows.
#
# onedir, not onefile. The website already promises "unzip and run", and the
# macOS release ships a .app bundle (also a directory), so this matches both
# the published instructions and the other platform. onefile would also
# re-extract ~300MB to %TEMP% on every launch, which is startup latency the
# user feels for no benefit.
#
# windowed, not console: Mike is a tray/panel application. A console window
# appearing behind it would be the single most obvious "this is a developer
# script" tell.
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# SPECPATH is injected by PyInstaller into the spec's exec globals -- using
# it instead of a relative literal means this spec builds correctly whether
# invoked as `pyinstaller packaging/mike.spec` from the repo root or from
# inside packaging/, rather than silently depending on the caller's cwd.
REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# comtypes generates UI Automation bindings by reading a type library at
# runtime and writing Python into comtypes/gen. That write cannot be relied
# on once frozen -- the bundle may sit in Program Files, and comtypes
# disables its own codegen when sys.frozen is set. build_windows.py
# generates these before the build so they ship as ordinary modules.
COMTYPES_GEN = [
    "comtypes.gen.UIAutomationClient",
    "comtypes.gen.stdole",
    "comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0",
    "comtypes.gen._944DE083_8FB8_45CF_BCB7_C477ACB2F897_0_1_0",
]

hiddenimports = [
    *COMTYPES_GEN,
    # Imported through a platform dispatch (hostplatform/*, voice/*,
    # computer/*), so nothing statically references them on the import graph
    # PyInstaller walks.
    "computer.windows",
    "voice.recognizer.windows",
    "voice.providers.windows",
    # The wake word ("Hey Mike") and the first-run tour are reached the same
    # way -- a platform dispatch and a lazy import inside run() -- so they are
    # invisible to the static graph and, without these, the packaged app would
    # silently have no wake word and no welcome on a machine that isn't this one.
    "voice.wake.windows",
    "ui.welcome",
    # Mike's Windows neural voice. Reached through the voice-provider dispatch
    # (get_provider), so nothing statically imports it; without this the
    # packaged app would silently have only the SAPI fallback.
    "voice.providers.piper",
    # Reading a student's PDF / Word / PowerPoint files. document_reader
    # imports these inside the function that needs them, and they were never
    # installed at all until the production pass found "pypdf isn't
    # installed" on an attached PDF -- listed explicitly so a lazy import can
    # never again silently leave them out of the package.
    "pypdf",
    *collect_submodules("docx"),
    *collect_submodules("pptx"),
    "win32com.client",
    # Pygments loads lexers and styles by name at runtime (get_lexer_by_name,
    # the "one-dark"/"friendly" styles), which the static graph never sees --
    # without these the packaged app would render every code block as plain,
    # uncoloured text. markdown_it's rules load the same way.
    *collect_submodules("pygments"),
    *collect_submodules("markdown_it"),
    # main.py imports these only when the exe is sitting outside its install
    # location, so nothing on the static import graph reaches them -- and a
    # missing installer is invisible until a real user unzips the release.
    "installer.core",
    "installer.window",
    *collect_submodules("faster_whisper"),
    # ToolRegistry finds Mike's tools by walking the tools package at runtime
    # (pkgutil.iter_modules), so the static graph only ever reached the ones
    # something else happened to import. Measured in the installed app: every
    # open_application / open_url / ide call failed with "Unknown tool: system"
    # and Mike fell back to run_command, turning a 4s "open notepad" into a
    # minute of retries. Collect the whole package so the frozen app has the
    # same tools as source.
    *collect_submodules("tools"),
]

# Mike is one app, but its optional surfaces each drag in a large dependency
# tree. These stay because they are real features a user can reach: the
# Google tools (Gmail, Docs, Sheets) and local speech-to-text.
analysis = Analysis(
    [os.path.join(REPO_ROOT, "main.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[
        (os.path.join(REPO_ROOT, "packaging", "icon.ico"), "packaging"),
        # Mike's typeface, Source Serif 4 (SIL Open Font License; OFL.txt ships
        # with it). Registered at startup by ui.panel.style.load_fonts() --
        # without these files every surface falls back to Segoe UI.
        (os.path.join(REPO_ROOT, "ui", "fonts"), os.path.join("ui", "fonts")),
        # The Privacy Policy, Terms and open-source licences, shown in
        # Settings -> About and on first run; they must ship with the app.
        (os.path.join(REPO_ROOT, "docs", "legal"), os.path.join("docs", "legal")),
        # The VS Code bridge extension. Without this the editor integration
        # is unreachable for anyone who didn't clone the repo: ide/bridge.py
        # starts, listens on 8787, and nothing ever connects, because the
        # .vsix that the other half of the protocol lives in was never
        # shipped. Bundling it is what lets Mike offer to install it.
        (os.path.join(REPO_ROOT, "vscode-extension", "mike-bridge-0.1.0.vsix"),
         "vscode-extension"),
        # The Piper neural-voice runtime: piper.exe, its DLLs and espeak-ng
        # data, and the bundled English voice models. This is what makes Mike
        # speak in a natural voice on a machine that only unzipped the release
        # -- without it the voice provider finds no runtime and falls back to
        # the SAPI system voice. Lives in runtime/ (git-ignored, fetched at
        # setup) and is copied to piper/ beside the app.
        (os.path.join(REPO_ROOT, "runtime", "piper"), "piper"),
        # python-docx / python-pptx load their XML templates from package data.
        *collect_data_files("docx"),
        *collect_data_files("pptx"),
        # faster-whisper's Silero voice-activity model, which the wake word
        # uses to skip sound that isn't speech before running Whisper.
        *collect_data_files("faster_whisper"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Development-only. Shipping pytest inside a user's application
        # would be packaging the test harness as a product.
        "pytest",
        "_pytest",
        "pyinstaller",
        "PyInstaller",
        # Qt modules Mike never loads. PySide6 is the single largest
        # contributor to bundle size; these are the ones with no call site.
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtQuick3D",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtDesigner",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtSerialPort",
        "PySide6.QtSql",
        "PySide6.QtTest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

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
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(REPO_ROOT, "packaging", "icon.ico"),
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Mike",
)
