# pyproxy.spec – no GUI, tray only
block_cipher = None

a = Analysis(
    ['tray_app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('config.yaml', '.'),
        ('proxy/*.py', 'proxy'),
    ],
    hiddenimports=[
        'proxy', 'proxy.config', 'proxy.logger', 'proxy.filters',
        'proxy.cache', 'proxy.bandwidth', 'proxy.http_parser',
        'proxy.ftp_handler', 'proxy.handler', 'proxy.server', 'proxy.stats',
        'pystray', 'pystray._win32',
        'PIL', 'PIL.Image', 'PIL.ImageDraw',
        'yaml', 'ftplib', 'logging.handlers',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'PyQt5', 'wx'],
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
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    target_arch=None,
)
