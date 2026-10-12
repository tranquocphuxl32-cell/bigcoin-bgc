# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Spezifikation fuer BGC-Miner (eine einzige .exe, ohne Python lauffaehig).
# Build:  pyinstaller BGC-Miner.spec       (auf Windows ausfuehren -> ergibt dist\BGC-Miner.exe)
import os
block_cipher = None

a = Analysis(
    ['bgc_app.py'],
    pathex=[os.getcwd()],
    binaries=[],
    # genesis-Datei mit einbuendeln (Fallback; die App erzeugt sie sonst deterministisch)
    datas=[('bgcfl_genesis.json', '.')],
    # Module, die nur dynamisch importiert werden -> explizit angeben
    hiddenimports=['bigcoin_pq','bgcfl_engine','bgcfl_wallet','bgc_secure','run_miner','bgcfl_genesis',
                   'qrcode','qrcode.image.svg'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter','numpy','matplotlib','PIL','pandas','scipy','test','unittest'],
    win_no_prefer_redirects=False, win_private_assemblies=False,
    cipher=block_cipher, noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='BGC-Miner',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    runtime_tmpdir=None,
    console=True,            # Konsolenfenster zeigen (Status/Logs); zum Ausblenden: False
    disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None,
    icon=('bgc.ico' if os.path.exists('bgc.ico') else None),   # App-Symbol
)
