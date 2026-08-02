# Suite Post-Production — Prototype

Application desktop regroupant plusieurs outils de post-production dans
une seule interface, avec une page d'accueil pour naviguer entre les
modules.

## Modules disponibles dans ce prototype

- **Téléchargement multiplateforme** : télécharge vidéos/audio depuis
  YouTube, TikTok, Facebook, Instagram, Vimeo, etc. (basé sur yt-dlp).
- **Métadonnées (rush)** : glisser un fichier vidéo pour voir toutes ses
  métadonnées techniques (codec, résolution, frame rate, profondeur de
  couleur, sous-échantillonnage chroma, pistes audio, sous-titres...),
  basé sur pymediainfo (équivalent du logiciel MediaInfo).
- **Encodeur** (type Shutter Encoder) : glisser une ou plusieurs vidéos,
  choisir une catégorie (montage, diffusion/broadcast, web, audio seul,
  suite d'images, réencapsulation), un format précis, ajuster résolution
  et frame rate (préréglages ou valeurs personnalisées), prévisualiser le
  rush sélectionné, et lancer l'encodage. Basé directement sur FFmpeg.
- **Transcription** : glisser un fichier audio/vidéo, choisir la langue,
  transcrire en local avec Whisper (faster-whisper), puis exporter en
  TXT/DOCX/PDF ou en sous-titres SRT/VTT (nombre de mots par sous-titre
  réglable). 100% autonome, aucun compte tiers requis.

## Installation

### 1. Python
Il faut Python 3.10 ou plus récent : https://www.python.org/downloads/
(cocher "Add python.exe to PATH" pendant l'installation).

### 2. FFmpeg et MediaInfo
Rien à installer séparément : les deux sont embarqués automatiquement
via les paquets Python `imageio-ffmpeg` et `pymediainfo`, installés à
l'étape suivante.

### 3. Dépendances Python
Dans le dossier du projet :

```bash
python3 -m venv venv
source venv/bin/activate        # Sur Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## Lancer l'application

```bash
python3 main.py
```

Une page d'accueil s'ouvre avec une carte par module. Clique sur celui
que tu veux utiliser.

## Structure du projet

```
main.py                    -> point d'entrée, assemble les pages
core/
  ffmpeg_utils.py           -> détection FFmpeg (partagée par tous les modules)
  settings_store.py         -> préférences persistantes (registre Windows / plist Mac)
pages/
  home_page.py              -> page d'accueil avec les cartes de modules
  downloader_page.py        -> module Téléchargement multiplateforme
  mediainfo_page.py         -> module Métadonnées (type MediaInfo)
  encoder_page.py           -> module Encodeur (type Shutter Encoder)
  transcription_page.py     -> module Transcription (Whisper local)
  settings_page.py          -> paramètres avancés (dépannage FFmpeg), caché par défaut
```

## Note sur la Transcription (téléchargement de modèle)

Au premier lancement d'une transcription, Whisper télécharge le modèle
choisi (quelques centaines de Mo à plus d'1 Go selon la taille du modèle) —
il faut donc une connexion internet la première fois, sans création de
compte. Les lancements suivants avec le même modèle sont locaux et plus
rapides.

## Paramètres avancés (FFmpeg)

Dans l'immense majorité des cas, tout fonctionne sans rien configurer.
Si jamais un souci technique persiste, un petit bouton ⚙ discret en bas
à droite de la page d'accueil permet d'indiquer manuellement où se
trouve FFmpeg sur la machine. Ce n'est qu'un filet de sécurité — pas une
étape normale d'utilisation.

## Limitations connues de ce prototype

- Pas encore de file d'attente persistante pour les téléchargements.
- Pas encore de gestion de profils/préréglages sauvegardés.
- Le module Métadonnées met en avant les champs les plus utiles en
  post-prod (codec, résolution, frame rate, bit depth, chroma
  subsampling...) ; pour les caméras qui embarquent des informations
  spécifiques (profil LOG, LUT, timecode...), elles restent consultables
  dans la section "métadonnées brutes" si la caméra les a enregistrées
  dans le fichier — toutes les caméras ne le font pas systématiquement.
- Pas encore packagé en `.exe` / `.app` — pour l'instant ça se lance avec
  Python installé. `imageio-ffmpeg` et `pymediainfo` fournissent tous
  les deux des hooks PyInstaller, donc leur contenu embarqué sera
  automatiquement inclus dans l'exécutable final le moment venu.
