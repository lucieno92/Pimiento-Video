#!/bin/bash
# ============================================================
#  Pimiento Video - Creation du fichier d'installation .dmg
#  A lancer APRES build_mac.sh :
#      bash make_dmg.sh
#
#  Le .dmg est l'equivalent Mac du Setup.exe : l'utilisateur
#  l'ouvre et glisse l'app dans son dossier Applications.
# ============================================================

set -e

APP="dist/Pimiento Video.app"
NOM="PimientoVideo-1.0"
DMG="dist/$NOM.dmg"
DOSSIER_TMP="dist/dmg_temp"

if [ ! -d "$APP" ]; then
    echo "ERREUR : $APP introuvable."
    echo "Lance d'abord : bash build_mac.sh"
    exit 1
fi

echo ""
echo "== Preparation du contenu du disque =="
rm -rf "$DOSSIER_TMP" "$DMG"
mkdir -p "$DOSSIER_TMP"

# Copier l'application
cp -R "$APP" "$DOSSIER_TMP/"

# Ajouter un raccourci vers le dossier Applications
# (c'est ce qui permet le glisser-deposer)
ln -s /Applications "$DOSSIER_TMP/Applications"

echo "== Creation du fichier .dmg =="
hdiutil create \
    -volname "Pimiento Video" \
    -srcfolder "$DOSSIER_TMP" \
    -ov \
    -format UDZO \
    "$DMG"

rm -rf "$DOSSIER_TMP"

TAILLE=$(du -sh "$DMG" | cut -f1)

echo ""
echo "=========================================="
echo "  TERMINE"
echo ""
echo "  Fichier cree : $DMG"
echo "  Taille : $TAILLE"
echo ""
echo "  C'est ce fichier que tes utilisateurs Mac"
echo "  telechargeront."
echo "=========================================="
