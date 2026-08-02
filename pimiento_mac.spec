# -*- mode: python ; coding: utf-8 -*-
"""
Configuration PyInstaller pour Pimiento Video — version macOS.
Lancer sur un Mac avec :  pyinstaller pimiento_mac.spec

Produit "Pimiento Video.app" dans le dossier dist/.
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Embarquer le dossier assets/ (logo, sons, police, exiftool)
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'yt_dlp',
        'imageio_ffmpeg',
        'soundfile',
        'numpy',
        'pedalboard',
    ],
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
    upx=False,              # UPX est deconseille sur macOS
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,    # permet d'ouvrir un fichier en le glissant sur l'app
    target_arch=None,       # None = architecture de la machine qui compile
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

# Etape specifique macOS : emballer le tout dans un vrai .app
app = BUNDLE(
    coll,
    name='Pimiento Video.app',
    icon='assets/logo.icns',      # icone macOS (a generer, voir le guide)
    bundle_identifier='com.pimientovideo.app',
    info_plist={
        'CFBundleName': 'Pimiento Video',
        'CFBundleDisplayName': 'Pimiento Video',
        'CFBundleShortVersionString': '1.0',
        'CFBundleVersion': '1.0',
        'NSHighResolutionCapable': True,
        # Autorisations demandees a l'utilisateur si besoin
        'NSMicrophoneUsageDescription':
            'Pimiento Video needs microphone access for voice recording features.',
        'NSAppleEventsUsageDescription':
            'Pimiento Video uses system events to process your media files.',
        # Types de fichiers que l'app declare savoir ouvrir
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
