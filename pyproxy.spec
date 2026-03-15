# pyproxy.spec
# Build with: pyinstaller pyproxy.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['tray_app.py'],
    pathex=[str(Path('.'))]  ,
    binaries=[],
    datas=[
        ('config.yaml', '.'),          # bundle default config
        ('proxy/*.py', 'proxy'),       # all proxy modules
    ],
    hiddenimports=[
        'proxy',
        'proxy.config',
        'proxy.logger',
        'proxy.filters',
        'proxy.cache',
        'proxy.bandwidth',
        'proxy.http_parser',
        'proxy.ftp_handler',
        'proxy.handler',
        'proxy.server',
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'yaml',
        'ftplib',
        'logging.handlers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PyProxy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no terminal window – tray only
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',      # uncomment and add icon.ico to use a custom icon
)
