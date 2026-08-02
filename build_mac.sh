#!/bin/bash
# ============================================================
#  Pimiento Video - Construction de l'application macOS
#  A lancer sur le Mac, depuis la racine du projet :
#      bash build_mac.sh
# ============================================================

set -e

echo ""
echo "=========================================="
echo "  Pimiento Video - Build macOS"
echo "=========================================="
echo ""

# --- Verification : on est bien a la racine du projet ---
if [ ! -f "main.py" ]; then
    echo "ERREUR : main.py introuvable."
    echo "Place-toi a la racine du projet avant de lancer ce script."
    exit 1
fi

# --- Verification : l'icone macOS existe ---
if [ ! -f "assets/logo.icns" ]; then
    echo "L'icone macOS n'existe pas encore, generation en cours..."
    bash make_icns.sh
    echo ""
fi

echo "== Etape 1/3 : nettoyage des anciens builds =="
rm -rf build dist
echo "OK"
echo ""

echo "== Etape 2/3 : construction de l'application =="
echo "(cela peut prendre 5 a 15 minutes)"
pyinstaller pimiento_mac.spec --noconfirm
echo ""

echo "== Etape 3/3 : verification =="
if [ -d "dist/Pimiento Video.app" ]; then
    TAILLE=$(du -sh "dist/Pimiento Video.app" | cut -f1)
    echo "Application creee : dist/Pimiento Video.app"
    echo "Taille : $TAILLE"
else
    echo "ERREUR : l'application n'a pas ete creee."
    exit 1
fi

echo ""
echo "=========================================="
echo "  TERMINE"
echo ""
echo "  Pour tester :"
echo "     open \"dist/Pimiento Video.app\""
echo ""
echo "  Pour creer le fichier d'installation (.dmg) :"
echo "     bash make_dmg.sh"
echo "=========================================="
