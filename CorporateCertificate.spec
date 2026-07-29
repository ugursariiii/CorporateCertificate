# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller yapılandırması — tek dosyalık (onefile) dağıtım.

Çıktı: dist/CorporateCertificate.exe

Bu tek dosya, kurulum gerektirmeden herhangi bir 64-bit Windows makinesine
kopyalanıp çalıştırılabilir. Python, PyQt6 ve pymssql (FreeTDS TDS istemcisi
dahil) exe'nin içindedir; hedef makineye ayrıca ODBC sürücüsü kurmak gerekmez.
Uygulama veriyi daima main.py'deki merkezî MSSQL sunucusundan okur; yanına
herhangi bir veritabanı dosyası kopyalanmaz.
"""

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    # pymssql'in C uzantıları dinamik olarak yüklendiğinden statik analizde
    # gözden kaçabilir; garanti olsun diye açıkça belirtiliyor.
    hiddenimports=['pymssql._pymssql', 'pymssql._mssql'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Kullanılmayan bağımlılıklar exe boyutunu şişirmesin.
    excludes=['tkinter', 'pyodbc', 'sqlite3', 'unittest', 'pydoc', 'pdb'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Tek dosya (onefile): binaries/datas EXE'nin içine gömülür, COLLECT kullanılmaz.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CorporateCertificate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX, Qt DLL'lerinde zaman zaman bozulmaya yol açtığı için kapalı.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
