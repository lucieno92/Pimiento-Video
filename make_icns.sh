#!/bin/bash
# ============================================================
#  Genere l'icone macOS (logo.icns) a partir de assets/logo.png
#  A lancer sur le Mac, depuis la racine du projet :
#      bash make_icns.sh
# ============================================================

set -e

SRC="assets/logo.png"
OUT="assets/logo.icns"
TMP="icon.iconset"

if [ ! -f "$SRC" ]; then
    echo "ERREUR : $SRC introuvable."
    echo "Place-toi a la racine du projet (la ou se trouve main.py)."
    exit 1
fi

echo "Generation des differentes tailles d'icone..."
rm -rf "$TMP"
mkdir -p "$TMP"

sips -z 16 16     "$SRC" --out "$TMP/icon_16x16.png"      > /dev/null
sips -z 32 32     "$SRC" --out "$TMP/icon_16x16@2x.png"   > /dev/null
sips -z 32 32     "$SRC" --out "$TMP/icon_32x32.png"      > /dev/null
sips -z 64 64     "$SRC" --out "$TMP/icon_32x32@2x.png"   > /dev/null
sips -z 128 128   "$SRC" --out "$TMP/icon_128x128.png"    > /dev/null
sips -z 256 256   "$SRC" --out "$TMP/icon_128x128@2x.png" > /dev/null
sips -z 256 256   "$SRC" --out "$TMP/icon_256x256.png"    > /dev/null
sips -z 512 512   "$SRC" --out "$TMP/icon_256x256@2x.png" > /dev/null
sips -z 512 512   "$SRC" --out "$TMP/icon_512x512.png"    > /dev/null
sips -z 1024 1024 "$SRC" --out "$TMP/icon_512x512@2x.png" > /dev/null

echo "Assemblage en fichier .icns..."
iconutil -c icns "$TMP" -o "$OUT"

rm -rf "$TMP"

echo ""
echo "TERMINE : $OUT a ete cree."
