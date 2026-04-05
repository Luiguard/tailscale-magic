from PyInstaller.utils.hooks import collect_all

tmp_ret = collect_all('pycparser')
p_datas, p_binaries, p_hiddenimports = tmp_ret
tmp_ret = collect_all('tzdata')
t_datas, t_binaries, t_hiddenimports = tmp_ret

# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=p_binaries + t_binaries,
    datas=[
        ('static/', 'static'),
    ] + p_datas + t_datas,
    hiddenimports=[
        'pystray', 
        'PIL.Image', 
        'PIL.ImageDraw', 
        'plyer.platforms.win.notification', 
        'webview.platforms.winforms'
    ] + p_hiddenimports + t_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TailscaleMagic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # Set to False for "Native" feel without terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['static/favicon.ico'], # Use the native .ico file
)
