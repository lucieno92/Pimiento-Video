# -*- mode: python ; coding: utf-8 -*-
"""
Fichier de configuration PyInstaller pour Pimiento Video.
Lancer avec :  pyinstaller pimiento.spec
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
        # Restes de Chatterbox (retiré) qui ne servent plus — mais on GARDE
        # torch/torchaudio car l'onglet Vocals/Music (Demucs) en a besoin.
        'chatterbox', 'transformers', 'diffusers', 's3tokenizer',
        'tensorflow', 'jax', 'torchvision',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    upx=True,
    console=False,          # False = pas de fenêtre noire de console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.ico',  # icône du .exe (voir note dans le guide)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Pimiento Video',
)
