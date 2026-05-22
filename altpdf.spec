# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

added_files = [
    ('icons/*.ico', 'icons'),           # application icons
    ('help.pdf', '.'),                  # help document — sits next to the exe
    (r'.\ghostscript\gswin64c.exe', 'ghostscript'),  # windows gs
    (r'.\ghostscript\gsdll64.lib', 'ghostscript'),  # windows gs
    (r'.\ghostscript\gsdll64.dll', 'ghostscript'),  # windows gs

    # ('./gs_folder/gs', 'ghostscript')  # linux gs
]

a = Analysis(
    ['main_entry.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AltPDF',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/icon.ico',
)
