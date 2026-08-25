# -*- mode: python ; coding: utf-8 -*-
"""
Configuration PyInstaller pour Pimiento Video — version macOS.
Lancer sur un Mac avec :  pyinstaller pimiento_mac.spec
Produit "Pimiento Video.app" dans le dossier dist/.
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Bibliotheques volumineuses qui embarquent des donnees/modeles internes :
# collect_all recupere leur code, leurs donnees et leurs binaires.
datas = []
binaries = []
hiddenimports = []

for pkg in ['torch', 'torchaudio', 'demucs', 'faster_whisper',
            'pedalboard', 'soundfile', 'reportlab', 'docx',
            'pdf2docx', 'docx2pdf', 'deep_translator', 'aaf2',
            'pymediainfo', 'fitz', 'pdfplumber', 'pypdf', 'openpyxl']:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Embarquer le dossier assets/ (logo, sons, police, exiftool, ffmpeg)
datas += [('assets', 'assets')]

# Modules importes de facon indirecte, a declarer explicitement
hiddenimports += [
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'yt_dlp',
    'imageio_ffmpeg',
    'numpy',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'chatterbox', 'transformers', 'diffusers', 's3tokenizer',
        'tensorflow', 'jax', 'torchvision',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Pimiento Video',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Pimiento Video',
)

app = BUNDLE(
    coll,
    name='Pimiento Video.app',
    icon='assets/logo.icns',
    bundle_identifier='com.pimientovideo.app',
    info_plist={
        'CFBundleName': 'Pimiento Video',
        'CFBundleDisplayName': 'Pimiento Video',
        'CFBundleShortVersionString': '1.3',
        'CFBundleVersion': '1.3',
        'NSHighResolutionCapable': True,
        'NSMicrophoneUsageDescription':
            'Pimiento Video needs microphone access for voice recording features.',
        'NSAppleEventsUsageDescription':
            'Pimiento Video uses system events to process your media files.',
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'Video File',
                'CFBundleTypeRole': 'Editor',
                'LSItemContentTypes': [
                    'public.movie', 'public.video', 'public.audio',
                ],
            },
        ],
    },
)
