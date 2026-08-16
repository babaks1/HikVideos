#!/usr/bin/env bash
# Désinstalle HikVideos.
#
# Couvre les deux façons dont il peut être présent :
#   - installé par le fichier autonome, dans le dossier personnel ;
#   - installé par le paquet .deb, dans /usr (retrait délégué à apt).
#
# Les vidéos téléchargées ne sont jamais touchées.
#
# Usage :  ./desinstaller.sh          demande confirmation
#          ./desinstaller.sh --oui    sans confirmation

set -euo pipefail

APP="$HOME/.local/share/hikvideos"
LANCEUR="$HOME/.local/share/applications/hikvideos.desktop"
ICONES="$HOME/.local/share/icons/hicolor"
CONFIG="$HOME/.config/hikvideos"

dossier_bureau() {
    # xdg-user-dir peut annoncer un dossier qui n'existe pas — il répond
    # « Desktop » par défaut quand la configuration de session est absente,
    # alors qu'un système en français crée « Bureau ». On ne retient sa
    # réponse que si le dossier existe vraiment.
    local candidat
    candidat="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
    if [ -n "$candidat" ] && [ -d "$candidat" ]; then
        echo "$candidat"
        return
    fi
    for nom in Bureau Desktop; do
        if [ -d "$HOME/$nom" ]; then
            echo "$HOME/$nom"
            return
        fi
    done
    echo "$HOME/Bureau"
}

# --- Inventaire de ce qui est présent ------------------------------------
TROUVE=()
[ -d "$APP" ]      && TROUVE+=("l'application ($APP)")
[ -f "$LANCEUR" ]  && TROUVE+=("le raccourci du menu")
[ -f "$(dossier_bureau)/hikvideos.desktop" ] && TROUVE+=("l'icône du bureau")
ls "$ICONES"/*/apps/hikvideos.* >/dev/null 2>&1 && TROUVE+=("les icônes")
[ -d "$CONFIG" ]   && TROUVE+=("les réglages ($CONFIG)")

PAQUET=""
if command -v dpkg >/dev/null 2>&1 && dpkg -l hikvideos 2>/dev/null | grep -q '^ii'; then
    PAQUET="oui"
fi

if [ ${#TROUVE[@]} -eq 0 ] && [ -z "$PAQUET" ]; then
    echo "HikVideos ne semble pas installé."
    exit 0
fi

echo "HikVideos va être désinstallé."
echo
if [ ${#TROUVE[@]} -gt 0 ]; then
    echo "Seront supprimés :"
    for e in "${TROUVE[@]}"; do echo "  - $e"; done
fi
if [ -n "$PAQUET" ]; then
    echo "  - le paquet système (mot de passe administrateur demandé)"
fi
echo
echo "Vos vidéos téléchargées ne seront pas touchées."
echo

if [ "${1:-}" != "--oui" ]; then
    read -r -p "Continuer ? [o/N] " REP
    case "${REP:-N}" in
        [oOyY]*) ;;
        *) echo "Annulé." ; exit 0 ;;
    esac
fi

# --- Installation dans le dossier personnel ------------------------------
rm -rf "$APP"
rm -f "$LANCEUR"
rm -f "$(dossier_bureau)/hikvideos.desktop"
for t in 48 64 128 256; do
    rm -f "$ICONES/${t}x${t}/apps/hikvideos.png"
done
rm -f "$ICONES/scalable/apps/hikvideos.svg"
rm -rf "$CONFIG"

command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -q -f -t "$ICONES" 2>/dev/null || true

# --- Paquet système ------------------------------------------------------
if [ -n "$PAQUET" ]; then
    echo
    echo "Retrait du paquet système..."
    sudo apt-get remove -y hikvideos
fi

echo
echo "HikVideos a été désinstallé."
echo "Vos vidéos sont restées dans leur dossier de téléchargement."
