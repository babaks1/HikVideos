"""Point d'entrée de l'exécutable autonome.

Lance directement l'interface graphique : l'exécutable est fait pour être
lancé d'un double-clic, sans terminal ni options en ligne de commande.

Au tout premier lancement, il s'installe dans le dossier personnel et pose
son icône sur le bureau et dans le menu des applications.
"""
import multiprocessing
import os
import sys


def _racine_donnees():
    """Dossier des ressources : décompression temporaire sous PyInstaller."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def _installer_si_besoin():
    """Pose l'icône au premier lancement. N'interrompt jamais le démarrage."""
    if not getattr(sys, "frozen", False):
        return  # lancé depuis les sources : rien à installer
    try:
        import premier_lancement as pl
        if pl.deja_installe():
            return
        message = pl.installer(_racine_donnees())
        if message:
            from PyQt5 import QtWidgets
            QtWidgets.QMessageBox.information(None, "HikVideos", message)
    except Exception:
        # L'installation de l'icône est un confort : si elle échoue,
        # l'application doit démarrer quand même.
        pass


def main():
    # Sans cet appel, un exécutable gelé qui créerait un processus fils
    # relancerait l'application entière au lieu du fils.
    multiprocessing.freeze_support()

    from PyQt5 import QtWidgets
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    _installer_si_besoin()

    from hikvideos.__main__ import main_ui
    from hikvideos.download import parse_args

    # parse_args() lit sys.argv : un double-clic ne passe aucun argument,
    # mais un lancement depuis le terminal peut en passer, on les respecte.
    args = parse_args()
    args.ui = True
    main_ui(args)


if __name__ == '__main__':
    sys.exit(main() or 0)
