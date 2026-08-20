"""Installation de l'icône au premier lancement.

L'utilisateur télécharge un fichier et le double-clique. Au premier
lancement, l'application se copie dans son dossier personnel et pose son
icône dans le menu des applications et sur le bureau : les lancements
suivants passent par l'icône, sans avoir à retrouver le fichier téléchargé.

Rien n'est écrit hors du dossier personnel, et aucun droit administrateur
n'est demandé.
"""
import os
import shutil
import subprocess
import sys

DOSSIER_APP = os.path.expanduser("~/.local/share/hikvideos")
DOSSIER_LANCEURS = os.path.expanduser("~/.local/share/applications")
DOSSIER_ICONES = os.path.expanduser("~/.local/share/icons/hicolor")
# Même dossier que les réglages de l'application (voir hikvideos/config.py).
DOSSIER_CONFIG = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "hikvideos")
LANCEUR = os.path.join(DOSSIER_LANCEURS, "hikvideos.desktop")
EXE_INSTALLE = os.path.join(DOSSIER_APP, "HikVideos")

# Emplacement du paquet .deb. Une installation système fait toujours autorité
# sur la copie personnelle : c'est elle que le gestionnaire de paquets met à
# jour, et elle que la désinstallation retire.
EXE_SYSTEME = "/usr/lib/hikvideos/HikVideos"

GABARIT = """[Desktop Entry]
Type=Application
Version=1.0
Name=HikVideos
GenericName=Récupération d'enregistrements caméra
Comment=Télécharger les enregistrements d'une caméra Hikvision autonome
Exec={exe}
Icon=hikvideos
Terminal=false
Categories=AudioVideo;Video;
Keywords=camera;hikvision;video;surveillance;enregistrement;
StartupNotify=true
"""


def _dossier_bureau():
    """Le bureau ne s'appelle pas « Desktop » sur un système en français."""
    try:
        chemin = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                capture_output=True, text=True, timeout=5)
        candidat = chemin.stdout.strip()
        if candidat and os.path.isdir(candidat):
            return candidat
    except (OSError, subprocess.SubprocessError):
        pass
    for nom in ("Bureau", "Desktop"):
        candidat = os.path.expanduser("~/" + nom)
        if os.path.isdir(candidat):
            return candidat
    return None


def _est_notre_lanceur(chemin):
    """Un lanceur posé par cette application, quelle que soit l'installation.

    Deux origines possibles : la copie dans le dossier personnel, ou
    l'exécutable d'un paquet système. Un lanceur écrit à la main par
    l'utilisateur — pointant ailleurs, avec ses propres options — n'est
    pas reconnu ici, donc jamais écrasé.
    """
    connus = {"Exec=" + EXE_INSTALLE,
              "Exec=" + os.path.realpath(sys.executable),
              "Exec=/usr/bin/hikvideos",
              "Exec=/usr/lib/hikvideos/HikVideos"}
    try:
        with open(chemin, encoding="utf-8") as f:
            return any(ligne.strip() in connus for ligne in f)
    except OSError:
        return False


def _ecrire_icones(racine_donnees):
    """Décline l'icône aux tailles attendues par les environnements de bureau."""
    source = os.path.join(racine_donnees, "packaging", "hikvideos-256.png")
    if not os.path.isfile(source):
        return False
    try:
        from PyQt5.QtGui import QImage
        image = QImage(source)
        if image.isNull():
            return False
        for taille in (48, 64, 128, 256):
            cible = os.path.join(DOSSIER_ICONES, f"{taille}x{taille}", "apps")
            os.makedirs(cible, exist_ok=True)
            image.scaled(taille, taille, 1, 1).save(
                os.path.join(cible, "hikvideos.png"))
        return True
    except Exception:
        return False


def installe_par_le_systeme(chemin=None):
    """Vrai si l'exécutable provient d'un paquet plutôt que d'un téléchargement.

    Le gestionnaire de paquets a alors déjà posé l'icône et le raccourci :
    se recopier dans le dossier personnel créerait un doublon que la
    désinstallation du paquet ne retirerait pas.
    """
    chemin = os.path.realpath(chemin or sys.executable)
    return chemin.startswith(("/usr/", "/opt/", "/snap/"))


def _poser_icone_bureau(contenu, systeme=False):
    """Écrit le lanceur sur le bureau. Renvoie un message, ou None si rien
    n'a été posé (pas de dossier bureau, ou lanceur existant à préserver)."""
    bureau = _dossier_bureau()
    if not bureau:
        return None

    cible = os.path.join(bureau, "hikvideos.desktop")
    # Ne jamais écraser un lanceur que l'utilisateur a écrit lui-même : il
    # peut pointer vers une autre installation, avec ses propres options.
    if os.path.exists(cible) and not _est_notre_lanceur(cible):
        return None

    try:
        with open(cible, "w", encoding="utf-8") as f:
            f.write(contenu)
        os.chmod(cible, 0o755)
    except OSError:
        return None

    # GNOME n'exécute un lanceur du bureau que s'il est marqué de confiance.
    try:
        subprocess.run(["gio", "set", cible, "metadata::trusted", "true"],
                       capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass

    if systeme:
        return ("HikVideos est installé.\n\nSon icône a été ajoutée à votre "
                "bureau ; il figure aussi dans le menu des applications.")
    return "pose"


def _icone_bureau_posee():
    """Trace du passage : l'icône a déjà été proposée une fois."""
    return os.path.isfile(os.path.join(DOSSIER_CONFIG, "icone-bureau-posee"))


def _marquer_icone_bureau():
    try:
        os.makedirs(DOSSIER_CONFIG, exist_ok=True)
        open(os.path.join(DOSSIER_CONFIG, "icone-bureau-posee"), "w").close()
    except OSError:
        pass


def _paquet_installe():
    """Le paquet système est-il en place, quel que soit ce qui tourne ?"""
    return os.path.isfile(EXE_SYSTEME)


def _raccourci_bureau_perime(exe_attendu):
    """Le raccourci du bureau désigne-t-il un autre exécutable ?

    Cas rencontré : l'exécutable autonome avait été lancé une première fois
    et s'était recopié dans le dossier personnel ; l'installation ultérieure
    du paquet n'a pas touché ce raccourci, qui a continué de lancer une
    version périmée. Deux copies coexistaient, et le comportement dépendait
    du chemin emprunté — bureau ou menu.
    """
    bureau = _dossier_bureau()
    if not bureau:
        return False
    cible = os.path.join(bureau, "hikvideos.desktop")
    if not os.path.isfile(cible) or not _est_notre_lanceur(cible):
        return False
    try:
        with open(cible, encoding="utf-8") as f:
            contenu = f.read()
    except OSError:
        return False
    for ligne in contenu.splitlines():
        if ligne.startswith("Exec="):
            actuel = ligne[len("Exec="):].strip()
            return os.path.realpath(actuel) != os.path.realpath(exe_attendu)
    return False


def deja_installe():
    if installe_par_le_systeme():
        # Le paquet a posé le raccourci du menu, mais aucun .deb ne peut
        # poser d'icône sur le bureau : celui-ci appartient à chaque
        # utilisateur, et le paquet s'installe pour toute la machine.
        # GNOME ne permet plus non plus de tirer une application du menu
        # vers le bureau — sans ce passage, l'icône n'existerait nulle part.
        if _raccourci_bureau_perime(sys.executable):
            return False
        return _icone_bureau_posee()
    # Lancé depuis la copie personnelle alors que le paquet est installé :
    # ne pas détourner les raccourcis vers soi. Sans ce garde-fou, les deux
    # installations se les disputent — le postinst du paquet les fait pointer
    # vers /usr/lib, puis le premier lancement de la copie personnelle les
    # ramène vers elle, et ainsi de suite. Chacun croit réparer une erreur,
    # et le dernier lancé gagne (constaté le 20/08/2026).
    #
    # Le paquet fait autorité : c'est lui que le gestionnaire met à jour.
    if _paquet_installe():
        return True

    if _raccourci_bureau_perime(EXE_INSTALLE):
        return False
    return os.path.isfile(LANCEUR) and os.path.isfile(EXE_INSTALLE)


def installer(racine_donnees):
    """Copie l'exécutable et pose les raccourcis. Renvoie un message ou None."""
    source = sys.executable  # sous PyInstaller : l'exécutable lui-même

    # Déjà lancé depuis l'emplacement installé : rien à faire.
    if os.path.realpath(source) == os.path.realpath(EXE_INSTALLE):
        return None

    if installe_par_le_systeme(source):
        # Installation système : ne rien recopier ni réécrire dans le menu,
        # le paquet s'en charge. Seule l'icône du bureau est posée, une fois.
        _marquer_icone_bureau()
        return _poser_icone_bureau(GABARIT.format(exe=source), systeme=True)

    os.makedirs(DOSSIER_APP, exist_ok=True)
    shutil.copy2(source, EXE_INSTALLE)
    os.chmod(EXE_INSTALLE, 0o755)

    _ecrire_icones(racine_donnees)

    os.makedirs(DOSSIER_LANCEURS, exist_ok=True)
    contenu = GABARIT.format(exe=EXE_INSTALLE)
    with open(LANCEUR, "w", encoding="utf-8") as f:
        f.write(contenu)

    sur_bureau = _poser_icone_bureau(contenu) is not None

    for commande in (["update-desktop-database", DOSSIER_LANCEURS],
                     ["gtk-update-icon-cache", "-f", "-t", DOSSIER_ICONES]):
        try:
            subprocess.run(commande, capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass

    if sur_bureau:
        return ("HikVideos a été installé.\n\nSon icône est maintenant sur votre "
                "bureau et dans le menu des applications : les prochaines fois, "
                "lancez-le depuis là.\n\nVous pouvez supprimer le fichier que "
                "vous avez téléchargé.")
    if bureau and os.path.exists(os.path.join(bureau, "hikvideos.desktop")):
        return ("HikVideos a été installé.\n\nSon icône est maintenant dans le "
                "menu des applications. Un raccourci HikVideos existait déjà sur "
                "votre bureau : il a été conservé tel quel.\n\nVous pouvez "
                "supprimer le fichier que vous avez téléchargé.")
    return ("HikVideos a été installé.\n\nSon icône est maintenant dans le menu "
            "des applications.\n\nVous pouvez supprimer le fichier que vous "
            "avez téléchargé.")
