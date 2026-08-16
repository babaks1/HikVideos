#!/usr/bin/env bash
# Installe le raccourci HikVideos dans le menu des applications.
#
# Le raccourci est posé dans ~/.local/share/applications et les icônes dans
# ~/.local/share/icons/hicolor : les emplacements standards, pris en compte
# par GNOME, KDE et Xfce sans droits administrateur.
#
# Usage :  ./installer-raccourci.sh            installe
#          ./installer-raccourci.sh --bureau   installe et copie sur le bureau
#          ./installer-raccourci.sh --retirer  désinstalle

set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS="$HOME/.local/share/applications"
ICONES="$HOME/.local/share/icons/hicolor"
CIBLE="$APPS/hikvideos.desktop"

retirer() {
    rm -f "$CIBLE"
    for t in 48 64 128 256; do
        rm -f "$ICONES/${t}x${t}/apps/hikvideos.png"
    done
    rm -f "$ICONES/scalable/apps/hikvideos.svg"
    # Le dossier du bureau n'est pas nommé pareil selon la langue du système.
    local bureau
    bureau="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Bureau")"
    # Ne retirer du bureau que le lanceur posé par ce script : l'utilisateur
    # peut y avoir le sien, écrit à la main, qu'on n'a pas à supprimer.
    if [ -f "$bureau/hikvideos.desktop" ] && \
       grep -q "^Exec=hikvideos-qt$" "$bureau/hikvideos.desktop" 2>/dev/null; then
        rm -f "$bureau/hikvideos.desktop"
    elif [ -f "$bureau/hikvideos.desktop" ]; then
        echo "Lanceur du bureau conservé : il n'a pas été posé par ce script."
    fi
    command -v update-desktop-database >/dev/null && \
        update-desktop-database "$APPS" 2>/dev/null || true
    echo "Raccourci retiré."
}

if [ "${1:-}" = "--retirer" ]; then
    retirer
    exit 0
fi

if ! command -v hikvideos-qt >/dev/null 2>&1; then
    echo "Attention : la commande hikvideos-qt est introuvable dans le PATH." >&2
    echo "Le raccourci sera installé mais ne se lancera pas tant que HikVideos" >&2
    echo "n'est pas installé (voir installer.sh)." >&2
fi

for t in 48 64 128 256; do
    install -Dm644 "$ICI/hikvideos-$t.png" "$ICONES/${t}x${t}/apps/hikvideos.png"
done
install -Dm644 "$ICI/hikvideos.svg" "$ICONES/scalable/apps/hikvideos.svg"
install -Dm644 "$ICI/hikvideos.desktop" "$CIBLE"

command -v update-desktop-database >/dev/null && \
    update-desktop-database "$APPS" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && \
    gtk-update-icon-cache -f -t "$ICONES" 2>/dev/null || true

echo "Raccourci installé — HikVideos apparaît dans le menu des applications."

if [ "${1:-}" = "--bureau" ]; then
    bureau="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Bureau")"
    if [ -d "$bureau" ]; then
        install -Dm755 "$ICI/hikvideos.desktop" "$bureau/hikvideos.desktop"
        # GNOME n'exécute un lanceur du bureau que s'il est marqué de confiance.
        command -v gio >/dev/null && \
            gio set "$bureau/hikvideos.desktop" metadata::trusted true 2>/dev/null || true
        echo "Copié sur le bureau : $bureau"
    else
        echo "Dossier bureau introuvable, copie ignorée." >&2
    fi
fi
