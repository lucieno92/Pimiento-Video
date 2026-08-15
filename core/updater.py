"""
Vérification de mise à jour pour Pimiento Video.

Au démarrage, l'app lit un petit fichier version.json hébergé en ligne et
le compare à sa version locale. Si une version plus récente existe, un
pop-up propose à l'utilisateur d'aller la télécharger.

Format attendu du fichier version.json en ligne :
{
    "latest": "1.2",
    "url": "https://pimientovideo.com/download",
    "notes": "Bug fixes and a new audio module."
}
"""

import json
import urllib.request

# ── Version actuelle de CE build ──────────────────────────────────────────────
# ⚠ Incrémente ce numéro à chaque nouvelle version que tu distribues.
CURRENT_VERSION = "1.1"

# ── URL du fichier version.json en ligne ──────────────────────────────────────
# ⚠ Remplace par l'URL réelle où tu héberges version.json
#    (GitHub, Netlify, ton site... — un simple fichier texte accessible).
VERSION_CHECK_URL = "https://pimientovideo.com/version.json"

# Timeout court pour ne jamais bloquer le démarrage
_TIMEOUT = 4


def _parse_version(v: str):
    """Transforme '1.2.3' en tuple (1, 2, 3) pour comparaison numérique."""
    parts = []
    for p in str(v).split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _is_newer(remote: str, local: str) -> bool:
    """True si remote > local."""
    return _parse_version(remote) > _parse_version(local)


def check_for_update():
    """Vérifie s'il existe une version plus récente.
    Retourne un dict {latest, url, notes} si une MAJ est dispo, sinon None.
    Ne lève jamais d'exception : en cas d'erreur réseau, retourne None
    silencieusement (l'app démarre normalement)."""
    try:
        req = urllib.request.Request(
            VERSION_CHECK_URL,
            headers={"User-Agent": f"PimientoVideo/{CURRENT_VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        latest = data.get("latest", "")
        if latest and _is_newer(latest, CURRENT_VERSION):
            return {
                "latest": latest,
                "url": data.get("url", ""),
                "notes": data.get("notes", ""),
            }
    except Exception:
        pass  # pas de réseau, fichier absent, JSON invalide... on ignore
    return None
