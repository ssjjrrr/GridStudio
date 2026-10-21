# Native builds: run this spec on each supported OS and CPU architecture.
from pathlib import Path
import runpy
import sys
from PySide6.QtCore import QLibraryInfo

project = Path(SPECPATH)
version = runpy.run_path(str(project / 'gridstudio' / '__init__.py'))['__version__']
windows = sys.platform == 'win32'
macos = sys.platform == 'darwin'
qt_translations = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
a = Analysis(
    [str(project / 'run.py')],
    pathex=[str(project)],
    binaries=[], datas=[(str(project / 'assets' / 'icon.png'), 'assets'),
                        (str(qt_translations / 'qtbase_zh_CN.qm'), 'assets/translations')],
    hiddenimports=[], hookspath=[],
    hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
# Qt for Windows imports the Windows system ICU API (unsuffixed symbols).
# A developer's PATH may contain an incompatible ICU build with the same DLL
# name. Do not bundle it: use the Windows 10/11 system implementation instead.
if windows:
    a.binaries = [item for item in a.binaries
                  if Path(item[0]).name.lower() not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='GridStudio', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
    icon=[str(project / 'assets' / ('icon.icns' if macos else 'icon.ico'))] if windows or macos else None,
    version=str(project / 'assets' / 'version_info.txt') if windows else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='GridStudio')
if macos:
    app = BUNDLE(
        coll, name='GridStudio.app', icon=str(project / 'assets' / 'icon.icns'),
        bundle_identifier='io.github.ssjjrrr.GridStudio', version=version,
        info_plist={
            'CFBundleShortVersionString': version, 'CFBundleVersion': version,
            'CFBundleDisplayName': 'GridStudio', 'LSMinimumSystemVersion': '13.0',
            'NSHighResolutionCapable': True, 'NSPrincipalClass': 'NSApplication',
            'CFBundleLocalizations': ['en', 'zh_CN'],
            'NSHumanReadableCopyright': 'Copyright © 2026 GridStudio contributors',
        },
    )
