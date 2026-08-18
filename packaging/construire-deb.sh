#!/usr/bin/env bash
# Construit le paquet .deb à partir de l'exécutable produit par PyInstaller.
#
# Le .deb règle le principal obstacle du fichier seul : Ubuntu refuse
# d'exécuter un fichier téléchargé tant que l'utilisateur n'a pas coché
# « Autoriser l'exécution » dans ses propriétés — une case qu'un débutant
# ne trouve pas. Un .deb s'installe d'un double-clic.
#
# Usage :  ./packaging/construire-deb.sh [version]

set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-1.3.1}"
ARCH="$(dpkg --print-architecture)"
NOM="hikvideos_${VERSION}_${ARCH}"
BUILD="$ICI/build/deb/$NOM"

if [ ! -x "$ICI/dist/HikVideos" ]; then
    echo "Erreur : dist/HikVideos est introuvable." >&2
    echo "Lancez d'abord :  pyinstaller --noconfirm --clean hikvideos.spec" >&2
    exit 1
fi

rm -rf "$BUILD"
mkdir -p "$BUILD/DEBIAN" \
         "$BUILD/usr/bin" \
         "$BUILD/usr/share/applications" \
         "$BUILD/usr/share/doc/hikvideos"

# --- L'exécutable --------------------------------------------------------
install -Dm755 "$ICI/dist/HikVideos" "$BUILD/usr/lib/hikvideos/HikVideos"
# Lancé depuis /usr/bin, l'exécutable ne doit pas réinstaller l'icône : le
# paquet s'en charge. Un lien symbolique suffit pour la ligne de commande.
ln -sf /usr/lib/hikvideos/HikVideos "$BUILD/usr/bin/hikvideos"

# --- Icônes --------------------------------------------------------------
for t in 48 64 128 256; do
    install -Dm644 "$ICI/packaging/hikvideos-$t.png" \
        "$BUILD/usr/share/icons/hicolor/${t}x${t}/apps/hikvideos.png"
done
install -Dm644 "$ICI/packaging/hikvideos.svg" \
    "$BUILD/usr/share/icons/hicolor/scalable/apps/hikvideos.svg"

# --- Raccourci -----------------------------------------------------------
cat > "$BUILD/usr/share/applications/hikvideos.desktop" <<'FIN'
[Desktop Entry]
Type=Application
Version=1.0
Name=HikVideos
GenericName=Récupération d'enregistrements caméra
Comment=Télécharger les enregistrements d'une caméra Hikvision autonome
Exec=/usr/lib/hikvideos/HikVideos
Icon=hikvideos
Terminal=false
Categories=AudioVideo;Video;
Keywords=camera;hikvision;video;surveillance;enregistrement;
StartupNotify=true
FIN

# --- Documentation -------------------------------------------------------
install -Dm644 "$ICI/README.md" "$BUILD/usr/share/doc/hikvideos/README.md"
install -Dm644 "$ICI/LICENSE" "$BUILD/usr/share/doc/hikvideos/copyright"
# Le travail d'origine reste sous MIT : sa licence accompagne le paquet.
install -Dm644 "$ICI/LICENSE-MIT-HikLoad" \
    "$BUILD/usr/share/doc/hikvideos/LICENSE-MIT-HikLoad"

# --- Métadonnées ---------------------------------------------------------
TAILLE=$(du -sk "$BUILD" | cut -f1)
cat > "$BUILD/DEBIAN/control" <<FIN
Package: hikvideos
Version: $VERSION
Section: video
Priority: optional
Architecture: $ARCH
Depends: libc6, ffmpeg
Installed-Size: $TAILLE
Maintainer: HikVideos
Description: Récupérer les enregistrements d'une caméra Hikvision
 Interroge une caméra Hikvision autonome, affiche la liste de ses
 enregistrements sur la période choisie, et télécharge ceux que vous
 sélectionnez.
 .
 Conçu pour les caméras autonomes, dont l'interface web ne propose pas
 d'onglet de relecture. Interface en français.
 .
 Toutes les dépendances Python sont embarquées : aucune installation
 supplémentaire n'est nécessaire.
Homepage: https://github.com/babaks1/HikVideos
FIN

# Rafraîchit les caches après installation et après retrait, sans quoi
# l'icône n'apparaît (ou ne disparaît) qu'à la session suivante.
cat > "$BUILD/DEBIAN/postinst" <<'FIN'
#!/bin/sh
set -e
if [ -x "$(command -v update-desktop-database)" ]; then
    update-desktop-database -q /usr/share/applications || true
fi
if [ -x "$(command -v gtk-update-icon-cache)" ]; then
    gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
fi
exit 0
FIN

cat > "$BUILD/DEBIAN/postrm" <<'FIN'
#!/bin/sh
set -e
if [ -x "$(command -v update-desktop-database)" ]; then
    update-desktop-database -q /usr/share/applications || true
fi
if [ -x "$(command -v gtk-update-icon-cache)" ]; then
    gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
fi
exit 0
FIN

chmod 755 "$BUILD/DEBIAN/postinst" "$BUILD/DEBIAN/postrm"

# --- Construction --------------------------------------------------------
mkdir -p "$ICI/dist"
dpkg-deb --build --root-owner-group "$BUILD" "$ICI/dist/$NOM.deb" >/dev/null

echo "Paquet construit : dist/$NOM.deb"
if command -v lintian >/dev/null 2>&1; then
    lintian --suppress-tags-from-file /dev/null "$ICI/dist/$NOM.deb" 2>/dev/null \
        | head -12 || true
fi
