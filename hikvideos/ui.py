from __future__ import annotations

import logging
import os
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from io import StringIO
from urllib.parse import parse_qs, urlparse

from PyQt5 import QtCore, QtGui, QtWidgets, uic

from hikvideos.hikvisionapi.classes import HikvisionServer
from hikvideos.uifiles.MainWindow import Ui_MainWindow
from hikvideos.uifiles.Startup import Ui_Startup

from . import config, conteneur, lecteur as lecteur_module
from .download import (create_folder_and_chdir, download_recording,
                       search_for_recordings, search_for_recordings_mock)

log_stream = StringIO()


# ----------------------------------------------------------------------
# Conversion heure locale <-> UTC
#
# Les selecteurs affichent l'HEURE LOCALE. download.py suffixe la valeur
# par "Z", donc la camera l'interprete comme de l'UTC : on convertit au
# moment de l'envoi.
# ----------------------------------------------------------------------
def local_to_utc(dt):
    """datetime naif en heure locale -> datetime naif en UTC."""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local(dt):
    """datetime naif en UTC -> datetime naif en heure locale."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().replace(tzinfo=None)


def _parse_hik_time(value):
    """Interprete 20260815T085846Z ou 2026-08-15T08:58:46Z."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y%m%dT%H%M%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def format_size(size):
    """Formate un volume en octets de facon lisible."""
    if not size:
        return "-"
    if size >= 1024 ** 3:
        return "%.2f Go" % (size / 1024 ** 3)
    if size >= 1024 ** 2:
        return "%.0f Mo" % (size / 1024 ** 2)
    return "%.0f Ko" % (size / 1024)


def recording_size(recordingobj):
    """Taille en octets d'un enregistrement, 0 si l'info est absente."""
    try:
        params = parse_qs(urlparse(getattr(recordingobj, "url", "") or "").query)
        if "size" in params:
            return int(params["size"][0])
    except Exception:
        pass
    return 0


def recording_details(recordingobj):
    """Extrait heure locale, duree et taille d'un enregistrement.

    L'URL de lecture Hikvision porte generalement starttime, endtime et
    size en parametres. Tout est optionnel : on renvoie des tirets si
    l'information est absente, plutot que de faire echouer l'affichage.
    """
    start_utc = _parse_hik_time(getattr(recordingobj, "startTime", None))
    end_utc = None
    size = None

    url = getattr(recordingobj, "url", "") or ""
    try:
        params = parse_qs(urlparse(url).query)
        if "endtime" in params:
            end_utc = _parse_hik_time(params["endtime"][0])
        if start_utc is None and "starttime" in params:
            start_utc = _parse_hik_time(params["starttime"][0])
        if "size" in params:
            size = int(params["size"][0])
    except Exception:
        pass

    local_str = "-"
    if start_utc is not None:
        local_str = utc_to_local(start_utc).strftime("%d/%m/%Y %H:%M:%S")

    duration_str = "-"
    if start_utc is not None and end_utc is not None:
        seconds = int((end_utc - start_utc).total_seconds())
        if seconds >= 0:
            minutes, sec = divmod(seconds, 60)
            hours, minutes = divmod(minutes, 60)
            if hours:
                duration_str = "%dh%02dm%02ds" % (hours, minutes, sec)
            elif minutes:
                duration_str = "%dm%02ds" % (minutes, sec)
            else:
                duration_str = "%ds" % sec

    size_str = format_size(size)

    channel = str(getattr(recordingobj, "cid", "") or "")
    return local_str, duration_str, size_str, channel


# ----------------------------------------------------------------------
# Fil de recherche : interroge la camera SANS rien telecharger
# ----------------------------------------------------------------------
class searchThread(threading.Thread):
    def __init__(self, server, args):
        threading.Thread.__init__(self)
        self.server = server
        self.args = args
        self.recordings = None
        self.error = None

    def run(self):
        logger = logging.getLogger('hikvideos')
        logger.info("Recherche des enregistrements...")
        try:
            if self.args.mock:
                self.recordings = search_for_recordings_mock(self.args)
            else:
                self.recordings = search_for_recordings(self.server, self.args)
        except Exception as exc:
            self.error = str(exc)
            self.recordings = []
            logger.error("Erreur pendant la recherche : %s" % exc)


# ----------------------------------------------------------------------
# Fil de telechargement : recoit une liste deja filtree
# ----------------------------------------------------------------------
class downloadThread(threading.Thread):
    def __init__(self, window: MainWindow, server: HikvisionServer, args,
                 recordings=None):
        threading.Thread.__init__(self)
        self.window = window
        self.running = True
        self.server = server
        self.args = args
        self.recordings = recordings
        self.finished = 0
        self.stopped_by_user = False
        # Octets des fichiers déjà terminés, et du fichier en cours : la
        # somme des deux donne l'avancement réel affiché par la barre.
        self.bytes_done = 0
        self.bytes_current = 0

        if not args:
            raise ValueError("args is not set correctly")

    def run(self):
        logger = logging.getLogger('hikvideos')
        logger.info("Démarrage du téléchargement")
        logger.debug(f"{self.args=}")

        if self.args.debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

        if self.recordings is None:
            try:
                if self.args.mock:
                    self.recordings = search_for_recordings_mock(self.args)
                else:
                    self.recordings = search_for_recordings(self.server, self.args)
            except Exception as exc:
                logger.error("Erreur pendant la recherche : %s" % exc)
                return

        recordings = self.recordings
        total = len(recordings)
        if total == 0:
            logger.info("Aucun enregistrement à télécharger")
            return

        logger.info("Téléchargement de %d fichier(s)" % total)
        create_folder_and_chdir(self.args.downloads)
        original_path = os.path.abspath(os.getcwd())

        interrompus = 0

        for recordingobj in recordings:
            if self.running is False:
                self.stopped_by_user = True
                break

            self.bytes_current = 0

            def avancement(recu, _self=self):
                """Rapporte les octets reçus ; False demande l'arrêt."""
                _self.bytes_current = recu
                return _self.running

            interrompu = False
            try:
                interrompu = bool(download_recording(
                    self.server, self.args, recordingobj, original_path,
                    progress_callback=avancement))
            except Exception as exc:
                logger.error("Échec sur %s : %s" % (recordingobj, exc))

            # La taille annoncée fait foi : le fichier converti n'a pas la
            # même taille que l'original, et la barre doit rester cohérente
            # avec le total calculé au départ.
            self.bytes_done += recording_size(recordingobj)
            self.bytes_current = 0

            # Un fichier interrompu n'est pas un fichier récupéré : le
            # compter fausserait le décompte final. L'arrêt étant testé en
            # tête de boucle, il ne serait jamais vu si l'utilisateur coupe
            # pendant le dernier fichier — d'où la sortie ici.
            if interrompu:
                interrompus += 1
                self.stopped_by_user = True
                break
            self.finished += 1

        if self.stopped_by_user:
            message = ("Arrêt : %d fichier(s) récupéré(s) sur %d"
                       % (self.finished, total))
            if interrompus:
                message += ", %d interrompu(s)" % interrompus
            logger.info(message)
        else:
            logger.info("Tous les enregistrements ont été téléchargés")


# Ordre des formats dans la liste déroulante. Il doit suivre exactement
# celui de uifiles/Startup.ui : Qt ne transmet que la position choisie.
# Regroupé ici pour n'avoir qu'un seul endroit à corriger.
FORMATS_VIDEO = ['mkv', 'mp4', 'avi', 'original']


class MainWindow(QtWidgets.QMainWindow):
    """Deroulement : parametres -> recherche -> selection -> telechargement."""

    COLUMNS = ["Début (heure locale)", "Durée", "Taille", "Canal"]

    def __init__(self, args=None):
        super(MainWindow, self).__init__()
        self.base_args = args
        self.args = None
        self.downloadthread = None
        self.searchthread = None
        self.quitting = False
        self.channel_cache = []
        self.channel_cache_key = None
        self.found_recordings = []

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self._setup_tree()
        self._add_lecteur()
        self._add_controls()

        self.logtimer = QtCore.QTimer(self)
        self.logtimer.timeout.connect(self._tick)
        self.logtimer.start(200)

        self._avertir_si_ffmpeg_absent()
        self._open_startup()

    def _avertir_si_ffmpeg_absent(self):
        """Prévient au démarrage plutôt qu'au premier échec de conversion.

        ffmpeg met les vidéos dans un conteneur exploitable : sans lui, les
        fichiers restent au format brut de la caméra. Le paquet .deb
        l'installe automatiquement, mais rien ne le garantit pour un
        exécutable lancé seul.
        """
        try:
            conteneur.verifier_outils()
        except conteneur.OutilManquant as e:
            logging.warning("%s", e)
            QtWidgets.QMessageBox.warning(
                self, "HikVideos",
                "%s\n\nLes vidéos pourront être téléchargées, mais elles "
                "resteront au format d'origine de la caméra, que certains "
                "lecteurs refusent." % e)

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------
    def _setup_tree(self):
        tree = self.ui.treeWidget
        tree.setColumnCount(len(self.COLUMNS))
        tree.setHeaderLabels(self.COLUMNS)
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        tree.setSortingEnabled(False)

        self._updating_checks = False
        tree.itemChanged.connect(self._on_item_changed)
        tree.currentItemChanged.connect(self._on_current_item_changed)
        self._add_selection_bar()

    def _add_selection_bar(self):
        """Bandeau au-dessus de la liste : case globale + compteur.

        Positionner un widget en absolu dans l'en-tete chevauchait le
        libelle de colonne : un bandeau dedie evite toute superposition
        tout en gardant l'alignement avec la colonne des cases.
        """
        self.selection_bar = QtWidgets.QWidget(self)
        layout = QtWidgets.QHBoxLayout(self.selection_bar)
        layout.setContentsMargins(4, 0, 4, 2)
        layout.setSpacing(6)

        self.header_checkbox = QtWidgets.QCheckBox(
            "Tout sélectionner", self.selection_bar)
        self.header_checkbox.setTristate(True)
        self.header_checkbox.setCheckState(QtCore.Qt.Checked)
        self.header_checkbox.setToolTip(
            "Cocher ou décocher tous les enregistrements")
        self.header_checkbox.clicked.connect(self._on_header_checkbox)

        self.selection_label = QtWidgets.QLabel("", self.selection_bar)
        self.selection_label.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        layout.addWidget(self.header_checkbox)
        layout.addStretch(1)
        layout.addWidget(self.selection_label)

        # La liste n'est pas un enfant direct de gridLayout : elle vit dans
        # horizontalLayout. On y substitue un conteneur vertical
        # [bandeau + liste] pour que le compteur reste au-dessus de la liste
        # et suive sa largeur, au lieu de filer au bord de la fenetre.
        tree = self.ui.treeWidget
        parent_layout = getattr(self.ui, "horizontalLayout", None)
        if parent_layout is None or parent_layout.indexOf(tree) < 0:
            self.ui.gridLayout.addWidget(self.selection_bar, 2, 0, 1, 1)
            return

        index = parent_layout.indexOf(tree)
        column = QtWidgets.QWidget(self.ui.centralwidget)
        vlayout = QtWidgets.QVBoxLayout(column)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(2)

        old_item = parent_layout.replaceWidget(tree, column)
        if old_item is not None:
            del old_item

        vlayout.addWidget(self.selection_bar)
        vlayout.addWidget(tree)

        # Les proportions colonne gauche / droite sont definies par index
        parent_layout.setStretch(1, 2)
        parent_layout.setStretch(index, 1)

    def _on_header_checkbox(self):
        """Clic utilisateur : on ne propose que tout coche / tout decoche."""
        if self.header_checkbox.checkState() == QtCore.Qt.Unchecked:
            self._set_all_checked(False)
        else:
            self.header_checkbox.setCheckState(QtCore.Qt.Checked)
            self._set_all_checked(True)

    def _on_item_changed(self, item, column):
        """Reflete l'etat de la liste sur la case d'en-tete."""
        if self._updating_checks:
            return
        self._refresh_header_checkbox()

    def _refresh_header_checkbox(self):
        tree = self.ui.treeWidget
        total = tree.topLevelItemCount()
        if total == 0:
            self.selection_label.setText("")
            return

        checked = 0
        total_bytes = 0
        for i in range(total):
            item = tree.topLevelItem(i)
            if item.checkState(0) == QtCore.Qt.Checked:
                checked += 1
                rec = item.data(0, QtCore.Qt.UserRole)
                total_bytes += recording_size(rec)

        self.header_checkbox.blockSignals(True)
        if checked == 0:
            self.header_checkbox.setCheckState(QtCore.Qt.Unchecked)
        elif checked == total:
            self.header_checkbox.setCheckState(QtCore.Qt.Checked)
        else:
            self.header_checkbox.setCheckState(QtCore.Qt.PartiallyChecked)
        self.header_checkbox.blockSignals(False)

        text = "%d / %d sélectionné%s" % (
            checked, total, "s" if checked >= 2 else "")
        if total_bytes:
            text += "  -  %s" % format_size(total_bytes)
        self.selection_label.setText(text)

    def _on_current_item_changed(self, item, _precedent):
        """Transmet au lecteur l'enregistrement de la ligne courante."""
        if not hasattr(self, "lecteur"):
            return
        rec = item.data(0, QtCore.Qt.UserRole) if item is not None else None
        self.lecteur.selectionner(rec)

    def _add_lecteur(self):
        """Installe la zone de prévisualisation sous le journal.

        Le journal et le lecteur partagent la colonne de gauche dans un
        séparateur ajustable : selon qu'on surveille un téléchargement ou
        qu'on compare des enregistrements, c'est l'un ou l'autre qu'on veut
        agrandir, et l'utilisateur en décide.
        """
        self.lecteur = lecteur_module.Lecteur(self)

        journal = self.ui.textEdit
        parent_layout = getattr(self.ui, "horizontalLayout", None)
        if parent_layout is None or parent_layout.indexOf(journal) < 0:
            # Disposition inattendue : plutôt que de renoncer au lecteur,
            # on l'ajoute en dessous de la grille.
            self.ui.gridLayout.addWidget(self.lecteur, 3, 0, 1, 1)
            return

        index = parent_layout.indexOf(journal)
        stretch = parent_layout.stretch(index)

        separateur = QtWidgets.QSplitter(
            QtCore.Qt.Vertical, self.ui.centralwidget)
        parent_layout.removeWidget(journal)
        journal.setParent(separateur)
        separateur.addWidget(journal)
        separateur.addWidget(self.lecteur)
        # Le journal garde la main au départ : la prévisualisation est un
        # complément, elle ne doit pas manger l'écran tant qu'on ne s'en
        # sert pas.
        separateur.setStretchFactor(0, 2)
        separateur.setStretchFactor(1, 3)
        separateur.setCollapsible(0, False)
        parent_layout.insertWidget(index, separateur)
        if stretch:
            parent_layout.setStretch(index, stretch)

    def _add_controls(self):
        bar = QtWidgets.QHBoxLayout()
        self.download_button = QtWidgets.QPushButton(
            "Télécharger la sélection", self)
        self.stop_button = QtWidgets.QPushButton("Arrêter", self)
        # Ce bouton referme la liste et rouvre le formulaire de départ :
        # « Retour » décrit mieux que « Nouvelle recherche », qui laissait
        # croire qu'une recherche était relancée directement.
        self.new_button = QtWidgets.QPushButton("Retour", self)
        self.quit_button = QtWidgets.QPushButton("Quitter", self)

        bar.addStretch(1)
        bar.addWidget(self.download_button)
        bar.addWidget(self.stop_button)
        bar.addWidget(self.new_button)
        bar.addWidget(self.quit_button)
        self.ui.gridLayout.addLayout(bar, 2, 0, 1, 1)

        self.download_button.clicked.connect(self.start_download)
        self.stop_button.clicked.connect(self.stop_download)
        self.new_button.clicked.connect(self.new_extraction)
        self.quit_button.clicked.connect(self.quit_application)

        self._set_mode("searching")

    def _set_mode(self, mode):
        """searching | selection | downloading | finished"""
        self.mode = mode
        downloading = mode == "downloading"
        # « finished » garde la liste et les cases cochées à l'écran : tout
        # doit y rester manipulable pour relancer un téléchargement — même
        # sélection ou autre — sans repasser par le formulaire de départ.
        modifiable = mode in ("selection", "finished")
        if hasattr(self, "header_checkbox"):
            self.header_checkbox.setEnabled(modifiable)
        if hasattr(self, "selection_bar"):
            self.selection_bar.setVisible(mode != "searching")
        self.download_button.setEnabled(modifiable)
        self.stop_button.setEnabled(downloading)
        self.new_button.setEnabled(modifiable)
        # Deux flux simultanés vers la caméra : la réaction de l'appareil
        # est inconnue, on l'évite. Un téléchargement qui démarre coupe
        # donc la prévisualisation en cours.
        if hasattr(self, "lecteur"):
            self.lecteur.setEnabled(not downloading)
            if downloading:
                self.lecteur.arreter()

    def _center(self):
        frameGm = self.frameGeometry()
        screen = QtWidgets.QApplication.desktop().screenNumber(
            QtWidgets.QApplication.desktop().cursor().pos())
        centerPoint = QtWidgets.QApplication.desktop().screenGeometry(screen).center()
        frameGm.moveCenter(centerPoint)
        self.move(frameGm.topLeft())

    # ------------------------------------------------------------------
    # Etape 1 : parametres puis recherche
    # ------------------------------------------------------------------
    def _open_startup(self):
        self.args = None
        startup = Startup(parent=self, args=self.base_args)
        startup.show()
        startup.exec_()

        if self.args is None:
            self.quit_application()
            return

        self.ui.textEdit.clear()
        self.ui.treeWidget.clear()
        self.ui.progressBar.setMaximum(1)
        self.ui.progressBar.setValue(0)
        self.found_recordings = []
        # Le lecteur a besoin des identifiants pour bâtir son URL RTSP :
        # ils ne sont connus qu'une fois le formulaire validé.
        self.lecteur.definir_camera(
            self.args.server, self.args.username, self.args.password)

        self.show()
        self._center()
        self._set_mode("searching")

        self.server = HikvisionServer(
            self.args.server, self.args.username, self.args.password)
        self.searchthread = searchThread(self.server, self.args)
        self.searchthread.daemon = True
        self.searchthread.start()

    # ------------------------------------------------------------------
    # Etape 2 : affichage de la liste avec cases a cocher
    # ------------------------------------------------------------------
    def _populate_results(self, recordings):
        self.found_recordings = list(recordings)
        tree = self.ui.treeWidget
        tree.clear()

        self._updating_checks = True
        for rec in self.found_recordings:
            local_str, duration, size, channel = recording_details(rec)
            item = QtWidgets.QTreeWidgetItem(
                [local_str, duration, size, channel])
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(0, QtCore.Qt.Checked)
            item.setData(0, QtCore.Qt.UserRole, rec)
            tree.addTopLevelItem(item)
        self._updating_checks = False

        for c in range(len(self.COLUMNS)):
            tree.resizeColumnToContents(c)
        tree.setColumnWidth(0, max(tree.columnWidth(0) + 10, 170))
        # La dernière colonne absorbe la largeur restante : sans cela, les
        # colonnes s'arrêtent à leur contenu et laissent un vide à droite,
        # ou débordent hors de la fenêtre quand elle est trop étroite.
        tree.header().setStretchLastSection(True)
        self._refresh_header_checkbox()

        logging.getLogger('hikvideos').info(
            "%d enregistrement(s) trouvé(s). Cochez ceux à télécharger, "
            "puis cliquez sur « Télécharger la sélection »."
            % len(self.found_recordings))

        self.ui.progressBar.setMaximum(max(len(self.found_recordings), 1))
        self.ui.progressBar.setValue(0)
        self._set_mode("selection" if self.found_recordings else "finished")

    def _set_all_checked(self, checked):
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        tree = self.ui.treeWidget
        self._updating_checks = True
        for i in range(tree.topLevelItemCount()):
            tree.topLevelItem(i).setCheckState(0, state)
        self._updating_checks = False
        self._refresh_header_checkbox()

    def _checked_recordings(self):
        selected = []
        tree = self.ui.treeWidget
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item.checkState(0) == QtCore.Qt.Checked:
                selected.append(item.data(0, QtCore.Qt.UserRole))
        return selected

    # ------------------------------------------------------------------
    # Etape 3 : telechargement de la selection
    # ------------------------------------------------------------------
    SEUIL_AVERTISSEMENT = 5 * 1024 ** 3   # 5 Go

    def _confirmer_gros_telechargement(self, selected):
        """Prévient au-delà du seuil. Renvoie False si l'utilisateur annule.

        On avertit sans jamais bloquer : l'espace libre annoncé par le
        système est peu fiable sur un disque réseau ou une clé, et refuser
        un téléchargement possible serait pire que le laisser échouer.
        """
        volume = sum(recording_size(r) for r in selected)
        if volume < self.SEUIL_AVERTISSEMENT:
            return True

        message = ("Vous êtes sur le point de télécharger %d enregistrements, "
                   "soit %s.\n\nAssurez-vous de disposer de suffisamment "
                   "d'espace disque." % (len(selected), format_size(volume)))

        libre = None
        try:
            dossier = getattr(self.args, 'downloads', None) if self.args else None
            # shutil.disk_usage exige un chemin existant : on remonte au
            # premier parent réel, le dossier de destination pouvant
            # n'être créé qu'au moment du téléchargement.
            while dossier and not os.path.isdir(dossier):
                parent = os.path.dirname(dossier)
                if parent == dossier:
                    break
                dossier = parent
            if dossier and os.path.isdir(dossier):
                import shutil
                libre = shutil.disk_usage(dossier).free
        except (OSError, ValueError, AttributeError):
            libre = None

        if libre is not None:
            message += "\nEspace disponible : %s." % format_size(libre)

        reponse = QtWidgets.QMessageBox.question(
            self, "Téléchargement volumineux", message,
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Ok)
        return reponse == QtWidgets.QMessageBox.Ok

    def start_download(self):
        selected = self._checked_recordings()
        if not selected:
            QtWidgets.QMessageBox.information(
                self, "Aucune sélection",
                "Cochez au moins un enregistrement à télécharger.")
            return

        if not self._confirmer_gros_telechargement(selected):
            return

        # Progression en octets plutôt qu'en nombre de fichiers : une vidéo
        # de 500 Mo et une de 5 Mo ne représentent pas le même travail, et
        # compter les fichiers laissait la barre figée sur les gros — voire
        # immobile de 0 à 100 % quand un seul fichier est sélectionné.
        total_octets = sum(recording_size(r) for r in selected)
        self._download_total_bytes = total_octets
        if total_octets > 0:
            # Échelle en millièmes, pas en octets : le maximum d'une
            # QProgressBar est un entier 32 bits signé, et une sélection
            # dépassant 2,1 Go — une cinquantaine de vidéos suffisent —
            # provoquait un OverflowError.
            self.ui.progressBar.setMaximum(1000)
        else:
            # Taille inconnue (absente de l'URL) : on retombe sur le compte
            # de fichiers, moins précis mais toujours mieux que rien.
            self.ui.progressBar.setMaximum(max(len(selected), 1))
        self.ui.progressBar.setValue(0)
        self._set_mode("downloading")

        self.downloadthread = downloadThread(
            self, self.server, self.args, recordings=selected)
        self.downloadthread.daemon = True
        self.downloadthread.start()

    # ------------------------------------------------------------------
    def _tick(self):
        value = log_stream.getvalue()
        if value:
            self.ui.textEdit.append(value.rstrip("\n"))
            log_stream.truncate(0)
            log_stream.seek(0)

        if (self.searchthread is not None
                and not self.searchthread.is_alive()
                and self.mode == "searching"):
            recordings = self.searchthread.recordings or []
            self.searchthread = None
            self._populate_results(recordings)

        if self.mode == "downloading" and self.downloadthread is not None:
            total = getattr(self, "_download_total_bytes", 0)
            if total > 0:
                recu = (self.downloadthread.bytes_done
                        + self.downloadthread.bytes_current)
                # Borné à 1000 : un fichier plus lourd qu'annoncé ferait
                # sinon dépasser la barre.
                self.ui.progressBar.setValue(
                    min(1000, int(recu * 1000 / total)))
            else:
                self.ui.progressBar.setValue(self.downloadthread.finished)
            if not self.downloadthread.is_alive():
                self._set_mode("finished")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def stop_download(self):
        if self.downloadthread is not None and self.downloadthread.is_alive():
            self.downloadthread.running = False
            logging.getLogger('hikvideos').info(
                "Arrêt demandé : le téléchargement en cours est interrompu.")
        self.stop_button.setEnabled(False)

    def new_extraction(self):
        if self.downloadthread is not None and self.downloadthread.is_alive():
            self.downloadthread.running = False
            self.downloadthread.join(timeout=10)
        self.downloadthread = None
        self.searchthread = None
        self.hide()
        self._open_startup()

    def _arreter_proprement(self):
        """Coupe le minuteur et attend les fils avant de rendre la main.

        Sans cela, _tick continuait de s'exécuter pendant la destruction
        des widgets, et les fils de téléchargement écrivaient encore dans
        un fichier au moment où l'interpréteur se refermait : la sortie
        était signalée comme un arrêt inattendu.
        """
        if getattr(self, "logtimer", None) is not None:
            self.logtimer.stop()

        # Le lecteur d'abord : son fil de décodage est un QThread, que Qt
        # détruit avec la fenêtre. S'il tourne encore à ce moment-là, Qt
        # abandonne le processus (« QThread: Destroyed while thread is still
        # running ») et la fermeture se solde par un plantage — constaté le
        # 20/08/2026 en fermant la fenêtre pendant une prévisualisation.
        if getattr(self, "lecteur", None) is not None:
            self.lecteur.arreter()

        for fil in (getattr(self, "downloadthread", None),
                    getattr(self, "searchthread", None)):
            if fil is None or not fil.is_alive():
                continue
            # Le fil de téléchargement lit ce drapeau entre deux morceaux
            # reçus ; celui de recherche n'en a pas, il attend la réponse
            # de la caméra et ne peut qu'être laissé finir.
            if hasattr(fil, "running"):
                fil.running = False
            # Court délai : le temps de finir l'écriture en cours, pas celui
            # du fichier entier. Les fils sont daemon, un fil récalcitrant
            # n'empêchera pas la fermeture.
            fil.join(timeout=5)

    def quit_application(self):
        self.quitting = True
        self._arreter_proprement()
        QtWidgets.QApplication.quit()

    def closeEvent(self, event):
        self.quitting = True
        self._arreter_proprement()
        event.accept()
        QtWidgets.QApplication.quit()

    def reject(self):
        self.quit_application()


class ErrorDialog(QtWidgets.QMessageBox):
    def __init__(self, message):
        super(ErrorDialog, self).__init__()
        self.setIcon(QtWidgets.QMessageBox.Critical)
        self.setWindowTitle("Erreur")
        self.setText("Une erreur s'est produite")
        self.setInformativeText(message)


class Startup(QtWidgets.QDialog):
    def __init__(self, parent=None, args=None):
        super(Startup, self).__init__()
        self.ui = Ui_Startup()
        self.ui.setupUi(self)
        self.args = args
        self.parent = parent
        self.skipclosing = False

        # Les selecteurs affichent l'heure LOCALE (etaient en UTC a l'origine)
        self.ui.start_date.setTimeSpec(QtCore.Qt.LocalTime)
        self.ui.end_date.setTimeSpec(QtCore.Qt.LocalTime)
        self.ui.start_date.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.ui.end_date.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.ui.start_date.setCalendarPopup(True)
        self.ui.end_date.setCalendarPopup(True)
        self._relabel_dates()
        self._syncing = False
        self.start_dateedit, self.start_timeedit = \
            self._split_datetime_widget(self.ui.start_date)
        self.end_dateedit, self.end_timeedit = \
            self._split_datetime_widget(self.ui.end_date)
        self._add_date_presets()

        # Réglages de la session précédente. La ligne de commande reste
        # prioritaire : appliquer() ne comble que les champs vides ou restés
        # à la valeur que le parseur pose faute de mieux.
        args, self._mot_de_passe_memorise = config.appliquer(
            args, defauts=config.defauts_parseur())
        self.args = args
        self._add_password_checkbox()

        self.populate_with_args(args)

        self.ui.downloads_folder_button.clicked.connect(
            self.select_download_folder)
        self.ui.test_connection_button.clicked.connect(self.test_connection)
        self.ui.start_downloading_button.clicked.connect(
            self.start_search)

        self.ui.start_downloading_button.setText("Rechercher")
        self.ui.start_downloading_button.setToolTip(
            "Recherche les enregistrements sur la période choisie. "
            "Le téléchargement se lance ensuite depuis la liste.")
        self.ui.start_downloading_button.setEnabled(False)
        self._restore_channels()

    # ------------------------------------------------------------------
    # Dates : libelles, raccourcis, restauration des canaux
    # ------------------------------------------------------------------
    def _relabel_dates(self):
        """Precise que les champs sont en heure locale."""
        try:
            self.ui.label_7.setText("Début (heure locale)")
            self.ui.label_8.setText("Fin (heure locale)")
        except AttributeError:
            pass

    def _split_datetime_widget(self, dtedit):
        """Remplace un champ date+heure unique par deux champs distincts.

        Le QDateTimeEdit d'origine reste vivant mais masque : il sert de
        source de verite, ce qui evite de modifier populate_with_args(),
        get_args() et les raccourcis de periode.
        """
        container = QtWidgets.QWidget(self)
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        dateedit = QtWidgets.QDateEdit(container)
        dateedit.setCalendarPopup(True)
        dateedit.setDisplayFormat("dd/MM/yyyy")

        timeedit = QtWidgets.QTimeEdit(container)
        timeedit.setDisplayFormat("HH:mm:ss")

        layout.addWidget(dateedit, 3)
        layout.addWidget(timeedit, 2)

        try:
            old_item = self.ui.formLayout.replaceWidget(dtedit, container)
            if old_item is not None:
                del old_item
        except AttributeError:
            return None, None

        dtedit.setParent(container)
        dtedit.hide()

        def parts_to_master():
            if self._syncing:
                return
            self._syncing = True
            dtedit.setDateTime(
                QtCore.QDateTime(dateedit.date(), timeedit.time()))
            self._syncing = False

        def master_to_parts():
            if self._syncing:
                return
            self._syncing = True
            current = dtedit.dateTime()
            dateedit.setDate(current.date())
            timeedit.setTime(current.time())
            self._syncing = False

        dateedit.dateChanged.connect(parts_to_master)
        timeedit.timeChanged.connect(parts_to_master)
        dtedit.dateTimeChanged.connect(master_to_parts)
        master_to_parts()

        return dateedit, timeedit

    def _add_date_presets(self):
        """Ajoute des raccourcis de periode sous les champs de date."""
        container = QtWidgets.QWidget(self)
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        presets = [
            ("Aujourd'hui", self._preset_today),
            ("Hier", self._preset_yesterday),
            ("7 jours", self._preset_week),
            ("Dernière heure", self._preset_lasthour),
        ]
        for label, slot in presets:
            btn = QtWidgets.QPushButton(label, container)
            btn.setMaximumWidth(120)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
        layout.addStretch(1)

        try:
            self.ui.formLayout.addRow(QtWidgets.QLabel("Periode"), container)
        except AttributeError:
            pass

    def _set_range(self, start, end):
        self.ui.start_date.setDateTime(start)
        self.ui.end_date.setDateTime(end)

    def _preset_today(self):
        now = datetime.now()
        self._set_range(now.replace(hour=0, minute=0, second=0, microsecond=0),
                        now.replace(hour=23, minute=59, second=59, microsecond=0))

    def _preset_yesterday(self):
        d = datetime.now() - timedelta(days=1)
        self._set_range(d.replace(hour=0, minute=0, second=0, microsecond=0),
                        d.replace(hour=23, minute=59, second=59, microsecond=0))

    def _preset_week(self):
        now = datetime.now()
        start = (now - timedelta(days=6)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        self._set_range(start, now)

    def _preset_lasthour(self):
        now = datetime.now()
        self._set_range(now - timedelta(hours=1), now)

    def _restore_channels(self):
        """Reaffiche les canaux connus sans redemander un test de connexion."""
        if self.parent is None:
            return
        cached = getattr(self.parent, "channel_cache", None)
        key = getattr(self.parent, "channel_cache_key", None)
        current_key = (self.ui.server_ip.text(), self.ui.username.text())
        if not cached or key != current_key:
            return

        self.ui.cameras.clear()
        for i, (identifiant, libelle) in enumerate(cached):
            item = QtWidgets.QTreeWidgetItem([libelle])
            item.setData(0, QtCore.Qt.UserRole, identifiant)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(0, QtCore.Qt.Checked)
            self.ui.cameras.insertTopLevelItems(i, [item])
        self._apply_camera_preselection()
        self.ui.start_downloading_button.setEnabled(True)

    def _add_password_checkbox(self):
        """Case « Enregistrer le mot de passe », sous le champ du mot de passe.

        Décochée par défaut : le mot de passe serait écrit en clair dans le
        fichier de configuration, l'utilisateur doit le choisir sciemment.
        """
        self.save_password = QtWidgets.QCheckBox(
            "Enregistrer le mot de passe", self)
        self.save_password.setToolTip(
            "Le mot de passe sera conservé en clair dans "
            "~/.config/hikvideos/config.json, lisible par vous seul.")
        # La sélection des flux se fait par cases à cocher : la surbrillance
        # multiple héritée du formulaire ferait croire à un second mode de
        # sélection, sans effet.
        self.ui.cameras.setSelectionMode(
            QtWidgets.QAbstractItemView.NoSelection)
        self.save_password.setChecked(self._mot_de_passe_memorise)
        # La case se place sous le champ du mot de passe (rangée 3), donc
        # au-dessus du dossier de téléchargement (rangée 4) : celui-ci et son
        # libellé descendent d'une rangée pour lui laisser la place.
        grille = self.ui.gridLayout
        # Le formulaire d'origine laisse la rangée 2 vide entre l'identifiant
        # et le mot de passe : on remonte tout d'un cran pour la supprimer,
        # puis on insère la case avant le dossier de téléchargement.
        libelle_mdp, champ_mdp = self.ui.label_3, self.ui.password
        libelle_dossier, champ_dossier = self.ui.label_6, self.ui.horizontalLayout_2
        for widget in (libelle_mdp, champ_mdp, libelle_dossier):
            grille.removeWidget(widget)
        grille.removeItem(champ_dossier)
        grille.addWidget(libelle_mdp, 2, 0, 1, 1)
        grille.addWidget(champ_mdp, 2, 2, 1, 1)
        grille.addWidget(self.save_password, 3, 2, 1, 1)
        grille.addWidget(libelle_dossier, 4, 0, 1, 1)
        grille.addLayout(champ_dossier, 4, 2, 1, 1)

        # Le libellé de la case reste court ; le détail technique va en
        # infobulle, pour qui veut savoir ce qui se passe réellement.
        self.ui.ffmpeg.setToolTip(
            "Change la façon de récupérer la vidéo.\n"
            "\n"
            "Normalement, HikVideos demande le fichier à la caméra, qui "
            "l'envoie\nd'un bloc — quelques secondes suffisent.\n"
            "\n"
            "Avec cette option, ffmpeg se connecte au flux RTSP de la caméra "
            "et\nl'enregistre au fil de l'eau : récupérer dix minutes de "
            "vidéo prend\ndix minutes.\n"
            "\n"
            "Utile uniquement si la caméra refuse d'envoyer ses fichiers "
            "(certains\nmodèles ne gèrent pas le téléchargement par nom ou "
            "par date).")
        self.ui.forcetranscoding.setToolTip(
            "Change la façon de traiter la vidéo après téléchargement.\n"
            "\n"
            "Normalement, l'image est recopiée telle quelle d'un format à "
            "l'autre :\naucune perte, quelques secondes même sur un gros "
            "fichier.\n"
            "\n"
            "Avec cette option, ffmpeg décode chaque image puis la "
            "réencode\nentièrement. Comptez plusieurs minutes, et une légère "
            "perte de qualité.\n"
            "\n"
            "À réserver aux fichiers abîmés qu'aucun lecteur n'ouvre : le "
            "réencodage\nrépare souvent ce que la simple recopie ne corrige "
            "pas.")
        self.ui.video_format.setToolTip(
            "La caméra livre ses enregistrements dans son propre format, "
            "souvent\nun conteneur ancien que les logiciels récents "
            "acceptent mal.\n"
            "\n"
            "HikVideos transvase la vidéo dans le format choisi. L'image "
            "n'est pas\nretouchée : elle est recopiée telle quelle, sans "
            "perte de qualité.\n"
            "\n"
            "mp4 — le plus compatible, à garder en cas de doute\n"
            "mkv — accepte tous les types de vidéo et de son\n"
            "avi — format ancien, incompatible avec les vidéos H.265\n"
            "Format d'origine — le fichier exact de la caméra, sans "
            "transformation\n"
            "\n"
            "Si la caméra livre déjà le format demandé, rien n'est converti.")
        self.ui.force.setToolTip(
            "Sans effet sur le téléchargement direct : les fichiers existants "
            "sont\ndans tous les cas remplacés.\n"
            "\n"
            "N'agit que si « Méthode de secours » est également cochée.")

    def populate_with_args(self, args=None):
        self.ui.server_ip.setText(args.server)
        self.ui.downloads_folder.setText(args.downloads)
        self.ui.username.setText(args.username)
        self.ui.password.setText(args.password)
        self.ui.folder_behavior.setCurrentIndex(list.index(
            [None, 'onepercamera', 'oneperday', 'onepermonth', 'oneperyear'], args.folders))
        # Un format inconnu (fichier de configuration d'une version
        # ultérieure, par exemple) ne doit pas empêcher le démarrage.
        try:
            self.ui.video_format.setCurrentIndex(
                FORMATS_VIDEO.index(args.videoformat))
        except ValueError:
            self.ui.video_format.setCurrentIndex(FORMATS_VIDEO.index('mp4'))
        # ui_starttime/ui_endtime = valeurs locales memorisees d'une session
        # a l'autre. Au 1er lancement, args.starttime vient de la ligne de
        # commande et est deja exprime en heure locale.
        self.ui.start_date.setDateTime(
            getattr(args, 'ui_starttime', None) or args.starttime)
        self.ui.end_date.setDateTime(
            getattr(args, 'ui_endtime', None) or args.endtime)
        self.ui.debug.setChecked(bool(args.debug))
        self.ui.force.setChecked(bool(args.force))
        self.ui.localtime.setChecked(bool(args.localtimefilenames))
        self.ui.ffmpeg.setChecked(bool(args.ffmpeg))
        self.ui.forcetranscoding.setChecked(bool(args.forcetranscoding))

    def _lire_formulaire(self):
        """Reporte les champs sur self.args, sans rien enregistrer.

        Séparé de get_args() pour que la fermeture de la fenêtre puisse
        mémoriser les réglages sans déclencher la validation.
        """
        self.args.server = self.ui.server_ip.text()
        self.args.downloads = self.ui.downloads_folder.text()
        self.args.username = self.ui.username.text()
        self.args.password = self.ui.password.text()
        # Le mot de passe vient d'être saisi ou modifié : le masquage du
        # journal doit suivre, sans quoi il porterait sur l'ancienne valeur.
        config.proteger_journal(self.args.password)
        self.args.folders = [None, 'onepercamera', 'oneperday',
                             'onepermonth', 'oneperyear'][self.ui.folder_behavior.currentIndex()]
        self.args.videoformat = FORMATS_VIDEO[
            self.ui.video_format.currentIndex()]
        # L'utilisateur saisit de l'heure locale ; download.py suffixe la
        # valeur par "Z" donc la camera l'interprete comme de l'UTC.
        local_start = self.ui.start_date.dateTime().toPyDateTime()
        local_end = self.ui.end_date.dateTime().toPyDateTime()
        self.args.ui_starttime = local_start
        self.args.ui_endtime = local_end
        self.args.starttime = local_to_utc(local_start)
        self.args.endtime = local_to_utc(local_end)
        # Flux cochés : repris tels quels pour être mémorisés d'une session
        # à l'autre. Une liste vide serait ambiguë (rien coché, ou liste pas
        # encore remplie ?) : on ne l'écrit que si elle a du contenu.
        coches = self._canaux_coches()
        if coches:
            self.args.cameras = coches
        self.args.debug = self.ui.debug.isChecked()
        self.args.force = self.ui.force.isChecked()
        self.args.localtimefilenames = self.ui.localtime.isChecked()
        self.args.ffmpeg = self.ui.ffmpeg.isChecked()
        self.args.forcetranscoding = self.ui.forcetranscoding.isChecked()
        # Les flux sont cochés, plus sélectionnés par surbrillance : on lit
        # l'identifiant mis en réserve, pas le libellé affiché.
        cameras = []
        for idx in range(self.ui.cameras.topLevelItemCount()):
            item = self.ui.cameras.topLevelItem(idx)
            if item.checkState(0) == QtCore.Qt.Checked:
                identifiant = self._channel_id(item)
                if identifiant:
                    cameras.append(identifiant)
        self.args.cameras = cameras
        return self.args

    def get_args(self):
        """Valide le formulaire et enregistre les réglages."""
        args = self._lire_formulaire()
        # Réglages conservés pour le prochain lancement. Les dates ne le sont
        # pas : on veut la période du jour, pas celle de la dernière session.
        config.sauvegarder(
            args, enregistrer_mot_de_passe=self.save_password.isChecked())
        return args

    def select_download_folder(self):
        file = str(QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Directory"))
        if file:
            self.ui.downloads_folder.setText(file)

    def _apply_camera_preselection(self):
        """Coche les flux : ceux demandés, ou le principal à défaut.

        `--cameras` et le choix mémorisé de la session précédente passent par
        le même chemin. Sans indication, on ne coche que le flux principal :
        les canaux secondaires enregistrent la même scène, tout cocher
        téléchargerait chaque séquence en double.
        """
        wanted = [str(c) for c in (getattr(self.args, 'cameras', None) or [])]
        matched = False
        if wanted:
            for idx in range(self.ui.cameras.topLevelItemCount()):
                item = self.ui.cameras.topLevelItem(idx)
                if self._channel_id(item) in wanted:
                    item.setCheckState(0, QtCore.Qt.Checked)
                    matched = True
                else:
                    item.setCheckState(0, QtCore.Qt.Unchecked)
        if not wanted or not matched:
            self._cocher_flux_principaux()

    def _cocher_flux_principaux(self):
        """Coche le flux principal de chaque caméra, décoche les autres.

        Les identifiants Hikvision se lisent « CCS » : le numéro de caméra
        suivi du numéro de flux. 101 est le flux principal de la caméra 1,
        102 et 103 ses déclinaisons plus légères. Sur une caméra autonome il
        n'y a qu'une entrée utile, mais la règle vaut aussi sur enregistreur.

        Repli : si aucun identifiant ne suit cette forme, on coche la
        première ligne plutôt que de laisser une liste vide, qui bloquerait
        la recherche sans explication.
        """
        total = self.ui.cameras.topLevelItemCount()
        coche = False
        for idx in range(total):
            item = self.ui.cameras.topLevelItem(idx)
            identifiant = str(self._channel_id(item) or "")
            principal = identifiant.endswith("1") and len(identifiant) >= 3
            item.setCheckState(
                0, QtCore.Qt.Checked if principal else QtCore.Qt.Unchecked)
            coche = coche or principal
        if not coche and total:
            self.ui.cameras.topLevelItem(0).setCheckState(0, QtCore.Qt.Checked)

    def _canaux_coches(self):
        """Identifiants des flux actuellement cochés dans la liste."""
        coches = []
        for idx in range(self.ui.cameras.topLevelItemCount()):
            item = self.ui.cameras.topLevelItem(idx)
            if item.checkState(0) == QtCore.Qt.Checked:
                identifiant = self._channel_id(item)
                if identifiant:
                    coches.append(str(identifiant))
        return coches

    @staticmethod
    def _channel_id(item):
        """Identifiant technique du flux, conservé à part de l'affichage."""
        return item.data(0, QtCore.Qt.UserRole)

    def _ajouter_flux(self, position, identifiant, nom=None,
                      largeur=None, hauteur=None):
        """Insère un flux cochable, libellé lisible et identifiant en réserve."""
        item = QtWidgets.QTreeWidgetItem(
            [self._libelle_flux(identifiant, nom, largeur, hauteur)])
        # L'identifiant reste attaché à la ligne : c'est lui qu'attend
        # --cameras, pas le libellé affiché.
        item.setData(0, QtCore.Qt.UserRole, str(identifiant))
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setCheckState(0, QtCore.Qt.Checked)
        self.ui.cameras.insertTopLevelItems(position, [item])
        return item

    @staticmethod
    def _libelle_flux(identifiant, nom=None, largeur=None, hauteur=None):
        """« ENTREE — flux principal (101) ».

        L'identifiant Hikvision code la caméra et le flux : les deux
        derniers chiffres donnent le rang du flux (01 principal,
        02 secondaire, 03 tertiaire), ce qui précède est le numéro de la
        caméra. Seul l'identifiant brut parlait à l'utilisateur
        jusqu'ici.
        """
        identifiant = str(identifiant)
        libelle = (nom or "").strip() or "Caméra"

        rangs = {"01": "flux principal", "02": "flux secondaire",
                 "03": "flux tertiaire"}
        rang = rangs.get(identifiant[-2:])
        if rang:
            libelle += " — " + rang

        if largeur and hauteur:
            libelle += " %sx%s" % (largeur, hauteur)

        return "%s (%s)" % (libelle, identifiant)

    def _cache_channels(self):
        """Memorise les canaux pour eviter un nouveau test de connexion."""
        if self.parent is None:
            return
        # Identifiant et libellé : le premier sert à --cameras, le second
        # à réafficher la liste sans réinterroger la caméra.
        channels = []
        for idx in range(self.ui.cameras.topLevelItemCount()):
            item = self.ui.cameras.topLevelItem(idx)
            channels.append((self._channel_id(item), item.text(0)))
        self.parent.channel_cache = channels
        self.parent.channel_cache_key = (
            self.ui.server_ip.text(), self.ui.username.text())

    def start_search(self):
        """Valide les parametres et lance la recherche (pas le telechargement)."""
        self.skipclosing = True
        self.parent.args = self.get_args()
        self.close()

    # Ancien nom conserve pour compatibilite
    start_downloading = start_search

    def test_connection(self):
        if not self.args.mock:
            # Premier échange avec la caméra, souvent avant tout appel à
            # get_args() : le masquage doit déjà connaître le mot de passe,
            # une erreur de connexion journalisant l'URL complète.
            config.proteger_journal(self.ui.password.text())
            try:
                server = HikvisionServer(self.ui.server_ip.text(
                ), self.ui.username.text(), self.ui.password.text())
                server.test_connection()
                channelList = server.Streaming.getChannels()
                self.ui.cameras.clear()
                channels = channelList['StreamingChannelList']['StreamingChannel']
                # Une caméra à flux unique renvoie un dict, pas une liste.
                if isinstance(channels, dict):
                    channels = [channels]
                for i, channel in enumerate(channels):
                    video = channel.get('Video') or {}
                    self._ajouter_flux(
                        i, channel.get('id'),
                        nom=channel.get('channelName'),
                        largeur=video.get('videoResolutionWidth'),
                        hauteur=video.get('videoResolutionHeight'))
                self._cache_channels()
                self._apply_camera_preselection()
            except Exception as exc:
                ErrorDialog(
                    f"Impossible de se connecter à la caméra.\n{exc}").exec_()
                logging.error(exc)
                return
        else:
            self.ui.cameras.clear()
            for i, channel in enumerate(["101", "102", "201"]):
                self._ajouter_flux(i, channel, nom="Caméra simulée")
            self._cache_channels()
            self._apply_camera_preselection()
        QtWidgets.QMessageBox.information(
            self, "Connexion réussie", "La caméra répond correctement.")
        self.ui.start_downloading_button.setEnabled(True)

    def _memoriser_reglages(self):
        """Enregistre les réglages saisis, sans valider le formulaire.

        Appelée aussi à la fermeture : sans cela, seul un clic sur
        « Rechercher » conservait les réglages, et refermer la fenêtre après
        avoir simplement testé la connexion faisait tout perdre.
        """
        try:
            config.sauvegarder(
                self._lire_formulaire(),
                enregistrer_mot_de_passe=self.save_password.isChecked())
        except Exception as exc:
            # La mémorisation est un confort : elle ne doit jamais empêcher
            # la fermeture de la fenêtre.
            logging.getLogger('hikvideos').debug(
                "Réglages non enregistrés : %s", exc)

    def closeEvent(self, event):
        event.accept()
        if self.skipclosing:
            return
        self._memoriser_reglages()
        if self.parent is not None:
            self.parent.args = None

    def reject(self):
        self._memoriser_reglages()
        if self.parent is not None:
            self.parent.args = None
        self.close()


def main(args=None):
    # Le nom de la fonction appelante ([run], [_populate_results]...) n'a
    # d'interet qu'en diagnostic : on ne l'affiche qu'en mode debogage.
    if args.debug:
        FORMAT = "%(asctime)s [%(funcName)s] %(message)s"
    else:
        FORMAT = "%(asctime)s  %(message)s"
    logger = logging.getLogger('hikvideos')
    logging.basicConfig(stream=log_stream, format=FORMAT,
                        datefmt="%H:%M:%S")
    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # Le journal est destiné à être copié dans un rapport d'anomalie : le
    # mot de passe n'a rien à y faire, même en mode diagnostic.
    config.proteger_journal(getattr(args, 'password', ''))

    # L'exécutable autonome crée déjà une QApplication avant d'arriver ici
    # (packaging/point-entree.py, pour pouvoir afficher un message au premier
    # lancement). En créer une seconde invalide la première et fait planter Qt
    # à l'ouverture de la fenêtre : on réutilise celle qui existe.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # Les menus contextuels des champs de saisie et du journal (Annuler,
    # Copier, Coller...) sont fournis par Qt, pas par l'application : ils
    # restent en anglais tant que la traduction de Qt n'est pas chargée.
    # Le fichier est embarqué dans PyQt5, donc présent aussi dans
    # l'exécutable autonome. Conservé dans une variable liée à app : un
    # traducteur détruit par le ramasse-miettes cesse d'agir.
    app._traducteur_qt = QtCore.QTranslator()
    if app._traducteur_qt.load(
            "qtbase_fr",
            QtCore.QLibraryInfo.location(QtCore.QLibraryInfo.TranslationsPath)):
        app.installTranslator(app._traducteur_qt)

    window = MainWindow(args)
    if not window.quitting:
        app.exec_()


if __name__ == '__main__':
    main()
