# PyInstaller configuration for the Windows portable distribution.
from pathlib import Path

project = Path(SPECPATH)
a = Analysis(
    [str(project / 'run.py')],
    pathex=[str(project)],
    binaries=[], datas=[], hiddenimports=[], hookspath=[],
    hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
# Qt for Windows imports the Windows system ICU API (unsuffixed symbols).
# A developer's PATH may contain an incompatible ICU build with the same DLL
# name. Do not bundle it: use the Windows 10/11 system implementation instead.
a.binaries = [item for item in a.binaries
              if Path(item[0]).name.lower() not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='GridStudio', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
    icon=[str(project / 'assets' / 'icon.ico')],
    version=str(project / 'assets' / 'version_info.txt'),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='GridStudio')
