#!/usr/bin/env bash
# Installation de HikVideos sur Ubuntu / Debian.
#
# Règle les trois obstacles rencontrés à l'installation manuelle :
#   - le module venv de Python n'est pas installé par défaut sous Ubuntu ;
#   - les versions de dépendances figées par l'amont ne se compilent pas
#     sous Python 3.12 (lxml 4.9.1 notamment) ;
#   - lxml a besoin des bibliothèques de développement XML pour se compiler.
#
# Usage :  ./installer.sh

set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ICI/venv"

echo "Installation de HikVideos"
echo

# --- Python ---------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "Erreur : python3 est introuvable." >&2
    exit 1
fi

PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PYOK="$(python3 -c 'import sys; print(1 if sys.version_info[:2] >= (3, 10) else 0)')"
if [ "$PYOK" != "1" ]; then
    echo "Erreur : Python 3.10 ou plus récent est nécessaire (détecté : $PYVER)." >&2
    exit 1
fi
echo "Python $PYVER détecté."

# --- Paquets système ------------------------------------------------------
# python3-venv est nommé d'après la version : python3.12-venv sous Ubuntu 24.04.
MANQUANTS=()
python3 -m venv --help >/dev/null 2>&1 || MANQUANTS+=("python${PYVER}-venv")
dpkg -s libxml2-dev  >/dev/null 2>&1 || MANQUANTS+=("libxml2-dev")
dpkg -s libxslt1-dev >/dev/null 2>&1 || MANQUANTS+=("libxslt1-dev")
dpkg -s python3-dev  >/dev/null 2>&1 || MANQUANTS+=("python3-dev")
command -v ffmpeg >/dev/null 2>&1   || MANQUANTS+=("ffmpeg")

if [ ${#MANQUANTS[@]} -gt 0 ]; then
    echo
    echo "Paquets système à installer : ${MANQUANTS[*]}"
    echo "Le mot de passe administrateur va être demandé."
    sudo apt-get update
    sudo apt-get install -y "${MANQUANTS[@]}"
else
    echo "Dépendances système déjà présentes."
fi

# --- Environnement isolé --------------------------------------------------
echo
if [ -d "$VENV" ]; then
    echo "Environnement existant réutilisé : $VENV"
else
    echo "Création de l'environnement isolé..."
    python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
python3 -m pip install --quiet --upgrade pip

echo "Installation des dépendances Python..."
# Versions minimales et non figées : voir setup.py.
python3 -m pip install --quiet \
    "lxml>=5.0" "requests>=2.31" "tqdm>=4.66" \
    "xmler>=0.2.0" "ffmpeg-python>=0.2.0" "pyqt5>=5.15.9"

echo "Installation de HikVideos..."
python3 -m pip install --quiet --no-deps -e "$ICI"

# --- Contrôle -------------------------------------------------------------
echo
if QT_QPA_PLATFORM=offscreen python3 -c "
import hikvideos.download, hikvideos.ui
from hikvideos.uifiles.Startup import Ui_Startup
" 2>/dev/null; then
    echo "Contrôle : les modules se chargent correctement."
else
    echo "Attention : les modules ne se chargent pas comme attendu." >&2
    exit 1
fi

# --- Raccourci ------------------------------------------------------------
echo
read -r -p "Ajouter HikVideos au menu des applications ? [O/n] " REP
case "${REP:-O}" in
    [nN]*) echo "Raccourci non installé." ;;
    *) "$ICI/packaging/installer-raccourci.sh" ;;
esac

cat <<FIN

Installation terminée.

Pour lancer HikVideos :
    source "$VENV/bin/activate"
    hikvideos-qt

Au premier lancement, renseignez l'adresse de la caméra, l'identifiant
et le mot de passe, puis « Test connection » avant de rechercher.
FIN
