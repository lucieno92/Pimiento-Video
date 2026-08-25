# -*- mode: python ; coding: utf-8 -*-
"""
Fichier de configuration PyInstaller pour Pimiento Video.
Lancer avec :  pyinstaller pimiento.spec
"""

block_cipher = None

# Collecte des paquets audio (demucs pour la séparation voix/musique) qui
# ont besoin de leurs données pour fonctionner dans l'exécutable packagé.
from PyInstaller.utils.hooks import collect_all
_extra_datas, _extra_binaries, _extra_hidden = [], [], []
for _pkg in ['torchaudio', 'demucs']:
    try:
        _d, _b, _h = collect_all(_pkg)
        _extra_datas += _d
        _extra_binaries += _b
        _extra_hidden += _h
    except Exception:
        pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_extra_binaries,
    datas=[
        # Embarquer le dossier assets/ (logo, sons, police, exiftool)
        ('assets', 'assets'),
    ] + _extra_datas,
    hiddenimports=[
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'yt_dlp',
        'imageio_ffmpeg',
        'soundfile',
        'numpy',
        'pedalboard',
    ] + _extra_hidden,
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
