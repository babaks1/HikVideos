"""Lecteur intégré : prévisualiser un enregistrement avant de le télécharger.

Sert d'aide à la sélection, rien d'autre. Une fois la vidéo sur le disque,
n'importe quel lecteur la lira mieux que celui-ci : le visionnage après
téléchargement est délibérément hors sujet.

**Pourquoi ffmpeg et non QtMultimedia.** La première version passait par
QtMultimedia, donc par GStreamer. Mesuré le 20/08/2026 sur la caméra
DS-2CD2687G2HT : le décodage matériel VA-API fait tomber le processus entier
(SIGSEGV, hors de portée d'un try/except), et une fois VA-API neutralisé le
décodage logiciel de GStreamer ne suit plus le flux 4K.

ffmpeg, lui, décode ce même flux à 25 images par seconde sans en perdre une
seule, pour 185 % d'un cœur — redimensionnement compris. Il était déjà
indispensable au projet depuis la 1.3.0 (conversion des conteneurs), donc ce
choix n'ajoute aucune dépendance, retire celles de GStreamer, et règle le cas
de l'exécutable autonome où rien ne garantissait leur présence.

Le flux vient de la caméra en RTSP, ce qui impose deux limites :

- **on ne peut pas s'y déplacer** : la barre de progression est indicative et
  non cliquable, pour ne pas promettre ce que l'appareil ne sait pas faire ;
- **la durée n'est pas annoncée** : elle est calculée depuis `starttime` /
  `endtime` de l'URL, comme le fait déjà `recording_details()`.
"""

import logging
import re
import shutil
import subprocess
import threading

from PyQt5 import QtCore, QtGui, QtWidgets

from hikvideos.hikvisionapi.classes import nettoyer_adresse

logger = logging.getLogger('hikvideos')


# Largeur de décodage. La zone d'affichage fait moins de 1000 px : décoder la
# pleine définition pour la réduire ensuite coûterait du temps processeur sans
# rien apporter à l'image. La hauteur suit le rapport d'origine (-2 garde un
# nombre pair, qu'exigent les formats de pixels).
LARGEUR_APERCU = 960

# La caméra n'accepte qu'un nombre limité de flux simultanés et répond
# « 453 Not Enough Bandwidth » au-delà.
MESSAGE_SATURATION = (
    "La caméra a refusé une connexion supplémentaire.\n\n"
    "Elle n'accepte qu'un nombre limité de flux à la fois : patientez "
    "quelques secondes avant de relancer la lecture."
)

# Au-delà, on considère que la caméra ne livrera pas d'images. Large : une
# connexion RTSP lente met plusieurs secondes à s'établir.
DELAI_PREMIERE_IMAGE_MS = 15000

MESSAGE_SANS_IMAGE = (
    "La caméra n'a envoyé aucune image pour cet enregistrement.\n\n"
    "Cela arrive sur les séquences très courtes, que la caméra référence "
    "sans pouvoir les rejouer. Le téléchargement, lui, reste possible."
)

MESSAGE_FFMPEG_ABSENT = (
    "La prévisualisation nécessite ffmpeg, qui est introuvable sur ce "
    "système.\n\nSur Ubuntu et dérivés :\n    sudo apt install ffmpeg"
)


def disponible():
    """Vrai si ffmpeg est utilisable."""
    return shutil.which("ffmpeg") is not None


def raison_indisponible():
    """Message technique, pour le journal."""
    return "ffmpeg introuvable dans le PATH"


def url_de_lecture(recordingobj, adresse, identifiant, mot_de_passe):
    """Construit l'URL RTSP d'un enregistrement, identifiants compris.

    Les identifiants ne sont jamais concaténés à la main : le mot de passe de
    la caméra peut contenir « @ » ou « & », qui ont tous deux un sens dans une
    URL. QUrl.setUserName/setPassword encode ce qu'il faut.

    Renvoie None si l'enregistrement ne porte pas d'URL exploitable.
    """
    brute = getattr(recordingobj, "url", "") or ""
    if not brute:
        return None

    url = QtCore.QUrl(brute)
    if not url.isValid():
        return None

    # La caméra renvoie son adresse de lecture SANS hôte (« rtsp:///Streaming/
    # tracks/101?… ») : telle quelle, elle ne mène nulle part. C'est d'ailleurs
    # pourquoi download.py remplace l'hôte avant de la passer à ffmpeg.
    #
    # Le nettoyage n'est pas facultatif : le formulaire accepte « http://… »
    # depuis la 1.3.1, et setHost() rejette alors l'adresse en silence,
    # laissant l'hôte vide sans lever la moindre erreur.
    adresse, _ = nettoyer_adresse(adresse)
    if not adresse:
        return None

    url.setScheme(url.scheme() or "rtsp")
    url.setHost(adresse)
    if identifiant:
        url.setUserName(identifiant)
    if mot_de_passe:
        url.setPassword(mot_de_passe)

    if not url.host():
        return None
    return url


def url_affichable(url):
    """Version de l'URL sans mot de passe, pour le journal."""
    if url is None:
        return ""
    return url.toString(QtCore.QUrl.RemovePassword)


def _duree_ms(recordingobj):
    """Durée de l'enregistrement en millisecondes, 0 si inconnue.

    Le flux RTSP annonce « duration=N/A » : la seule source fiable est le
    couple starttime/endtime porté par l'URL.
    """
    from urllib.parse import parse_qs, urlparse

    from hikvideos.ui import _parse_hik_time

    try:
        params = parse_qs(urlparse(getattr(recordingobj, "url", "") or "").query)
        debut = _parse_hik_time(params.get("starttime", [None])[0])
        fin = _parse_hik_time(params.get("endtime", [None])[0])
        if debut is not None and fin is not None:
            secondes = (fin - debut).total_seconds()
            if secondes > 0:
                return int(secondes * 1000)
    except Exception:
        pass
    return 0


def _horodatage(ms):
    """Millisecondes en m:ss ou h:mm:ss."""
    secondes = max(0, int(ms // 1000))
    minutes, sec = divmod(secondes, 60)
    heures, minutes = divmod(minutes, 60)
    if heures:
        return "%d:%02d:%02d" % (heures, minutes, sec)
    return "%d:%02d" % (minutes, sec)


def _message_erreur(detail):
    """Traduit le bavardage de ffmpeg en une phrase utile."""
    texte = (detail or "").strip()
    bas = texte.lower()
    if "453" in bas or "bandwidth" in bas:
        return MESSAGE_SATURATION
    if "401" in bas or "unauthorized" in bas:
        return ("Identifiants refusés par la caméra.\n\n"
                "Vérifiez le nom d'utilisateur et le mot de passe.")
    if "timed out" in bas or "timeout" in bas or "no route" in bas:
        return ("La caméra n'a pas répondu.\n\n"
                "Vérifiez qu'elle est allumée et joignable sur le réseau.")
    return ("La prévisualisation a échoué.\n\n"
            "Le téléchargement de l'enregistrement reste possible."
            + (("\n\nDétail : %s" % texte[:300]) if texte else ""))


def _mourir_avec_le_parent():
    """Demande au noyau de tuer ce processus si son parent disparaît.

    Exécuté dans le processus fils, juste avant le lancement de ffmpeg.
    Silencieux hors Linux : c'est un garde-fou, pas une fonctionnalité.
    """
    try:
        import ctypes
        import signal as _signal
        PR_SET_PDEATHSIG = 1
        ctypes.CDLL("libc.so.6").prctl(PR_SET_PDEATHSIG, _signal.SIGKILL)
    except Exception:
        pass


class _FilDecodage(QtCore.QThread):
    """Décode le flux dans un fil séparé et livre les images à l'interface.

    ffmpeg écrit des images brutes sur sa sortie standard ; on les lit par
    blocs de taille fixe. Un fil est indispensable : cette lecture bloque, et
    la faire dans le fil graphique figerait toute la fenêtre.

    Les signaux Qt sont le seul canal vers l'interface — un widget ne se
    touche jamais depuis un autre fil.
    """

    image_prete = QtCore.pyqtSignal(QtGui.QImage)
    position = QtCore.pyqtSignal(int)
    echec = QtCore.pyqtSignal(str)
    fini = QtCore.pyqtSignal()

    def __init__(self, url, parent=None):
        super(_FilDecodage, self).__init__(parent)
        self._url = url
        self._processus = None
        self._arret = threading.Event()
        self._pause = threading.Event()
        self._sans_image_declenche = False
        # Remplacée par la valeur réelle dès que ffmpeg annonce le flux ;
        # 25 i/s n'est qu'un repli si la ligne d'en-tête change de forme.
        self.cadence = 25.0

    def demander_arret(self):
        """Interrompt le décodage ; le processus est tué sans attendre."""
        self._arret.set()
        self._pause.clear()
        processus = self._processus
        if processus is not None and processus.poll() is None:
            try:
                processus.kill()
            except Exception:
                pass

    def _sans_image(self):
        """Chien de garde : la caméra n'a rien livré, on coupe court.

        Tuer ffmpeg ferme son tuyau, ce qui débloque le read() de run() et
        laisse la suite du code produire un message explicite.
        """
        processus = self._processus
        if processus is not None and processus.poll() is None:
            self._sans_image_declenche = True
            logger.info(
                "Aucune image reçue après %d s, lecture interrompue.",
                DELAI_PREMIERE_IMAGE_MS // 1000)
            try:
                processus.kill()
            except Exception:
                pass

    def basculer_pause(self):
        """Suspend ou reprend la livraison des images. Renvoie l'état de pause.

        Le flux RTSP se déroule en temps réel et ne se met pas en pause : on
        continue de le lire mais on cesse d'afficher, ce qui fige l'image sans
        décaler la suite ni faire enfler un tampon.
        """
        if self._pause.is_set():
            self._pause.clear()
        else:
            self._pause.set()
        return self._pause.is_set()

    def _lire_dimensions(self):
        """Lit la taille des images dans ce que ffmpeg annonce au démarrage.

        La sortie brute de ffmpeg n'a aucun en-tête : il faut savoir combien
        d'octets forment une image avant de commencer à lire.

        ⚠️ Surtout PAS un appel à ffprobe au préalable : la caméra n'accepte
        qu'un flux à la fois et ne libère pas le précédent assez vite. Un
        ffprobe suivi d'un ffmpeg se solde systématiquement par un
        « 453 Not Enough Bandwidth » (constaté le 20/08/2026). On lit donc les
        dimensions dans le compte rendu du seul et unique ffmpeg lancé, sur sa
        ligne « Stream #0:0 … rawvideo … 960x540 ».

        Renvoie (largeur, hauteur), ou (0, 0, message) en cas d'échec.
        """
        sortie = ""
        while not self._arret.is_set():
            ligne = self._processus.stderr.readline()
            if not ligne:
                break
            ligne = ligne.decode(errors="replace")
            sortie += ligne
            # La cadence est annoncée sur la ligne du flux d'ENTRÉE, avant
            # celle de sortie : on la relève au passage plutôt que de la
            # supposer. Toutes les caméras ne filment pas à 25 i/s, et une
            # valeur codée en dur ferait dériver la progression.
            if "Stream #" in ligne and "Video:" in ligne and " fps" in ligne:
                fps = re.search(r"([\d.]+) fps", ligne)
                if fps:
                    try:
                        valeur = float(fps.group(1))
                        if 1.0 <= valeur <= 240.0:
                            self.cadence = valeur
                    except ValueError:
                        pass

            if "rawvideo" in ligne and "Stream #" in ligne:
                trouve = re.search(r"(\d{2,5})x(\d{2,5})", ligne)
                if trouve:
                    return int(trouve.group(1)), int(trouve.group(2)), ""
            # ffmpeg signale ses erreurs avant d'avoir rien produit.
            if "Error opening input" in ligne or "failed" in ligne.lower():
                sortie += (self._processus.stderr.read() or b"").decode(
                    errors="replace")
                break
        return 0, 0, sortie

    def run(self):
        commande = [
            # -loglevel info : ffmpeg n'annonce la taille des images qu'à ce
            # niveau, et _lire_dimensions() en dépend.
            # -nostats : sans cela il répète une ligne de progression tout au
            # long de la lecture (8 Ko pour 35 s, mesuré). Personne ne la lit
            # une fois les dimensions connues, le tampon du tuyau (64 Ko) se
            # remplirait et ffmpeg se bloquerait en pleine vidéo.
            "ffmpeg", "-hide_banner", "-loglevel", "info", "-nostats",
            "-rtsp_transport", "tcp",
            "-i", self._url,
            "-vf", "scale=%d:-2" % LARGEUR_APERCU,
            "-pix_fmt", "rgb24",
            "-f", "rawvideo", "-",
        ]
        try:
            self._processus = subprocess.Popen(
                commande, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                # ffmpeg meurt avec nous. Sans cela, une application tuée
                # brutalement (kill, plantage, fermeture de session) laisse
                # derrière elle un ffmpeg qui garde la caméra occupée : les
                # lectures suivantes se heurtent alors à un « 453 Not Enough
                # Bandwidth » venu d'un processus fantôme. Constaté le
                # 20/08/2026. PR_SET_PDEATHSIG vaut 1 sous Linux ; ailleurs
                # preexec_fn est simplement sans effet.
                preexec_fn=_mourir_avec_le_parent)
        except Exception as e:
            self.echec.emit(str(e))
            return

        # Le chien de garde couvre TOUTE la phase d'ouverture, dimensions
        # comprises : une caméra qui accepte la connexion sans jamais rien
        # livrer bloque dès la lecture de stderr, avant même la boucle
        # d'images. L'armer plus tard ne servirait à rien.
        chien = threading.Timer(
            DELAI_PREMIERE_IMAGE_MS / 1000.0, self._sans_image)
        chien.daemon = True
        chien.start()

        largeur, hauteur, erreur_demarrage = self._lire_dimensions()
        if self._arret.is_set():
            chien.cancel()
            return
        if not largeur or not hauteur:
            chien.cancel()
            if self._sans_image_declenche:
                self.echec.emit(MESSAGE_SANS_IMAGE)
            else:
                self.echec.emit(_message_erreur(erreur_demarrage))
            return

        octets_par_image = largeur * hauteur * 3
        images = 0

        # Cadence relevée dans l'en-tête du flux par _lire_dimensions().
        cadence = self.cadence

        while not self._arret.is_set():
            donnees = self._processus.stdout.read(octets_par_image)
            if not donnees or len(donnees) < octets_par_image:
                break
            if self._pause.is_set():
                # En pause, l'image reste figée ET la progression s'arrête :
                # l'émettre quand même ferait défiler la barre sous une image
                # immobile. Les images continuent d'être consommées — le flux
                # RTSP se déroule en temps réel et ne se met pas en pause —
                # mais elles ne sont ni comptées ni affichées.
                continue

            if images == 0:
                chien.cancel()
            images += 1
            self.position.emit(int(images / cadence * 1000))
            # copy() : le tampon Python est réutilisé au tour suivant, sans
            # copie l'image affichée se déformerait sous nos yeux.
            image = QtGui.QImage(
                donnees, largeur, hauteur, largeur * 3,
                QtGui.QImage.Format_RGB888).copy()
            self.image_prete.emit(image)

        chien.cancel()

        erreur = b""
        try:
            if self._processus.poll() is None:
                self._processus.kill()
            erreur = self._processus.stderr.read() or b""
        except Exception:
            pass

        if self._arret.is_set():
            return
        if images == 0:
            texte = erreur.decode(errors="replace")
            if self._sans_image_declenche:
                self.echec.emit(MESSAGE_SANS_IMAGE)
                return
            if "no packets" in texte.lower() or "nothing was written" in texte.lower():
                self.echec.emit(MESSAGE_SANS_IMAGE)
            else:
                self.echec.emit(_message_erreur(texte))
        else:
            self.fini.emit()


class Lecteur(QtWidgets.QWidget):
    """Zone de prévisualisation : image, commandes, progression.

    Le widget s'affiche et se manipule même quand ffmpeg manque : les
    commandes restent grisées et un message explique pourquoi, plutôt que de
    faire disparaître une fonction sans raison visible.
    """

    def __init__(self, parent=None):
        super(Lecteur, self).__init__(parent)

        self._enregistrement = None
        self._duree_connue = 0
        self._joue = False
        self._adresse = ""
        self._identifiant = ""
        self._mot_de_passe = ""
        self._fil = None
        self._derniere_image = None

        disposition = QtWidgets.QVBoxLayout(self)
        disposition.setContentsMargins(0, 4, 0, 0)
        disposition.setSpacing(4)

        disposition.addWidget(self._construire_image(), 1)
        disposition.addLayout(self._construire_commandes())

        self._rafraichir_boutons()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _construire_image(self):
        """Zone d'image, ou message d'explication si la lecture est hors jeu."""
        self.pile = QtWidgets.QStackedWidget(self)
        self.pile.setMinimumHeight(180)

        # Page 0 : le message d'attente ou d'erreur, sur fond sombre pour
        # que la bascule vers l'image ne fasse pas clignoter la fenêtre.
        self.message = QtWidgets.QLabel("", self.pile)
        self.message.setAlignment(QtCore.Qt.AlignCenter)
        self.message.setWordWrap(True)
        self.message.setMargin(12)
        self.message.setStyleSheet("background: #202020; color: #d0d0d0;")
        self.pile.addWidget(self.message)

        # Page 1 : l'image. Surtout PAS setScaledContents(True), qui étire
        # l'image jusqu'aux bords sans égard pour ses proportions : la vidéo
        # apparaissait déformée en largeur. Le redimensionnement se fait à
        # chaque image dans _sur_image(), en préservant le rapport d'origine.
        self.video = QtWidgets.QLabel(self.pile)
        self.video.setAlignment(QtCore.Qt.AlignCenter)
        self.video.setStyleSheet("background: #000000;")
        self.video.setMinimumSize(1, 1)
        self.pile.addWidget(self.video)

        self._afficher_message(
            "Sélectionnez un enregistrement, puis cliquez sur « Lire »."
            if disponible() else MESSAGE_FFMPEG_ABSENT)
        return self.pile

    def _construire_commandes(self):
        """Boutons et barre de progression."""
        barre = QtWidgets.QHBoxLayout()
        barre.setContentsMargins(0, 0, 0, 0)
        barre.setSpacing(6)

        self.bouton_lire = QtWidgets.QPushButton("Lire", self)
        self.bouton_pause = QtWidgets.QPushButton("Pause", self)
        self.bouton_arreter = QtWidgets.QPushButton("Arrêter", self)

        self.bouton_lire.setToolTip(
            "Prévisualiser l'enregistrement sélectionné avant de le "
            "télécharger")
        self.bouton_lire.clicked.connect(self.lire)
        self.bouton_pause.clicked.connect(self.basculer_pause)
        self.bouton_arreter.clicked.connect(self.arreter)

        # Indicative seulement : la caméra ne permet pas de se déplacer dans
        # le flux, une barre cliquable laisserait croire le contraire.
        self.progression = QtWidgets.QProgressBar(self)
        self.progression.setTextVisible(False)
        self.progression.setMaximum(1)
        self.progression.setValue(0)
        self.progression.setFixedHeight(6)

        self.horloge = QtWidgets.QLabel("", self)
        self.horloge.setMinimumWidth(90)
        self.horloge.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        barre.addWidget(self.bouton_lire)
        barre.addWidget(self.bouton_pause)
        barre.addWidget(self.bouton_arreter)
        barre.addWidget(self.progression, 1)
        barre.addWidget(self.horloge)
        return barre

    # ------------------------------------------------------------------
    # Affichage
    # ------------------------------------------------------------------
    def _afficher_message(self, texte):
        self.message.setText(texte)
        self.pile.setCurrentWidget(self.message)

    def _afficher_image(self):
        self.pile.setCurrentWidget(self.video)

    def _rafraichir_boutons(self):
        """Active les commandes selon l'état réel de la lecture."""
        pret = disponible() and self._enregistrement is not None
        self.bouton_lire.setEnabled(pret and not self._joue)
        self.bouton_pause.setEnabled(self._joue)
        self.bouton_arreter.setEnabled(self._joue)

    def _rafraichir_horloge(self, position_ms):
        if self._duree_connue > 0:
            # Le total affiché suit la même échelle que la barre : sans cela
            # on lirait « 0:21 / 0:20 », qui ferait douter des deux.
            total = max(self._duree_connue, self.progression.maximum())
            self.horloge.setText("%s / %s" % (
                _horodatage(position_ms), _horodatage(total)))
        elif position_ms:
            self.horloge.setText(_horodatage(position_ms))
        else:
            self.horloge.setText("")

    # ------------------------------------------------------------------
    # Sélection
    # ------------------------------------------------------------------
    def definir_camera(self, adresse, identifiant, mot_de_passe):
        """Mémorise de quoi joindre la caméra, après validation du formulaire."""
        self._adresse = adresse or ""
        self._identifiant = identifiant or ""
        self._mot_de_passe = mot_de_passe or ""

    def selectionner(self, recordingobj):
        """Désigne l'enregistrement que « Lire » doit ouvrir.

        Si une lecture est déjà en cours, elle bascule aussitôt sur le
        nouvel enregistrement : pendant la lecture, parcourir la liste sert
        justement à comparer. À froid, en revanche, un simple clic ne
        déclenche rien — sans quoi parcourir vingt lignes ouvrirait vingt
        connexions vers la caméra.
        """
        self._enregistrement = recordingobj
        if self._joue:
            self.lire()
        else:
            self._rafraichir_boutons()

    # ------------------------------------------------------------------
    # Commandes
    # ------------------------------------------------------------------
    def lire(self):
        """Lance la lecture de l'enregistrement sélectionné."""
        if not disponible():
            self._afficher_message(MESSAGE_FFMPEG_ABSENT)
            return
        if self._enregistrement is None:
            return

        url = url_de_lecture(
            self._enregistrement, self._adresse,
            self._identifiant, self._mot_de_passe)
        if url is None:
            self._afficher_message(
                "Cet enregistrement ne peut pas être prévisualisé : la "
                "caméra n'a pas fourni d'adresse de lecture.")
            return

        # Libère le flux précédent avant d'en demander un autre : la caméra
        # refuse au-delà de sa limite (« 453 Not Enough Bandwidth »), et
        # enchaîner deux lectures suffit à l'atteindre.
        self._arreter_fil()

        self._duree_connue = _duree_ms(self._enregistrement)
        self.progression.setMaximum(max(self._duree_connue, 1))
        self.progression.setValue(0)
        self._rafraichir_horloge(0)
        self.bouton_pause.setText("Pause")

        logger.info("Prévisualisation : %s", url_affichable(url))
        self._afficher_message("Connexion à la caméra…")

        # FullyEncoded : ffmpeg reçoit l'URL telle quelle, le « @ » et le
        # « & » du mot de passe doivent donc y être encodés.
        self._fil = _FilDecodage(url.toString(QtCore.QUrl.FullyEncoded), self)
        self._fil.image_prete.connect(self._sur_image)
        self._fil.position.connect(self._sur_position)
        self._fil.echec.connect(self._sur_erreur)
        self._fil.fini.connect(self._sur_fin)
        self._fil.start()

        self._joue = True
        self._rafraichir_boutons()

    def basculer_pause(self):
        """Met en pause, ou reprend si déjà en pause."""
        if self._fil is None:
            return
        self.bouton_pause.setText(
            "Reprendre" if self._fil.basculer_pause() else "Pause")

    def arreter(self):
        """Arrête la lecture et vide l'image."""
        self._arreter_fil()
        self._joue = False
        self.bouton_pause.setText("Pause")
        self.progression.setValue(0)
        self.horloge.setText("")
        self._derniere_image = None
        self.video.clear()
        if disponible():
            self._afficher_message(
                "Sélectionnez un enregistrement, puis cliquez sur « Lire ».")
        self._rafraichir_boutons()

    def _arreter_fil(self):
        """Interrompt le décodage en cours et attend sa fin.

        L'attente est bornée : un ffmpeg qui ne rendrait pas la main ne doit
        pas figer la fenêtre. Le processus a de toute façon reçu un kill().
        """
        fil, self._fil = self._fil, None
        if fil is None:
            return
        try:
            fil.image_prete.disconnect()
            fil.position.disconnect()
            fil.echec.disconnect()
            fil.fini.disconnect()
        except TypeError:
            pass
        fil.demander_arret()
        fil.wait(3000)

    def closeEvent(self, event):
        """Ne laisse jamais un ffmpeg derrière soi à la fermeture."""
        self._arreter_fil()
        super(Lecteur, self).closeEvent(event)

    # ------------------------------------------------------------------
    # Retours du fil de décodage
    # ------------------------------------------------------------------
    def _sur_image(self, image):
        if self.pile.currentWidget() is not self.video:
            self._afficher_image()
        # KeepAspectRatio : l'image occupe la place disponible sans jamais
        # être déformée ; le fond noir du widget comble ce qui reste.
        self._derniere_image = image
        self.video.setPixmap(QtGui.QPixmap.fromImage(image).scaled(
            self.video.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation))

    def resizeEvent(self, event):
        """Réajuste l'image figée quand la fenêtre change de taille.

        Sans cela, une image en pause ou la dernière image affichée garderait
        l'échelle calculée pour l'ancienne taille du widget.
        """
        super(Lecteur, self).resizeEvent(event)
        image = getattr(self, "_derniere_image", None)
        if image is not None and self.pile.currentWidget() is self.video:
            self.video.setPixmap(QtGui.QPixmap.fromImage(image).scaled(
                self.video.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation))

    def _sur_position(self, position_ms):
        """Avance la barre, purement indicative.

        La durée annoncée par la caméra est arrondie à la seconde et dépasse
        régulièrement la durée réelle du flux : 8 s annoncées pour 7,4 s
        livrées (mesuré le 20/08/2026). La barre restait donc visiblement
        incomplète à chaque fin de lecture.

        Plutôt que de la compléter après coup, on recale l'échelle dès que le
        flux dépasse ce qui était prévu : la barre reste honnête pendant la
        lecture, et arrive au bout quand la vidéo se termine.
        """
        if position_ms > self.progression.maximum():
            self.progression.setMaximum(position_ms)
        self.progression.setValue(position_ms)
        self._rafraichir_horloge(position_ms)

    def _sur_fin(self):
        """Fin de l'enregistrement : la barre est menée au bout.

        La durée annoncée par la caméra est un arrondi à la seconde des
        horodatages, pas une mesure du flux : 8 s annoncées pour 7,4 s
        réellement livrées (185 images à 25 i/s, mesuré le 20/08/2026). Sans
        ce recalage, la barre s'arrêtait à 92 % à chaque lecture — c'est ce
        qui donnait « 0:07 » sur un enregistrement de « 0:08 ».

        On ramène donc l'échelle sur ce qui a vraiment été lu : la barre
        arrive au bout, et l'horloge affiche la durée réelle plutôt qu'une
        annonce qui ne correspondait à rien.
        """
        reel = self.progression.value()
        if reel > 0:
            self._duree_connue = reel
            self.progression.setMaximum(reel)
            self._rafraichir_horloge(reel)
        self.progression.setValue(self.progression.maximum())
        self.arreter()

    def _sur_erreur(self, message):
        """Échec de lecture : message clair, application intacte."""
        logger.warning("Prévisualisation impossible : %s",
                       message.replace("\n", " ")[:200])
        self._arreter_fil()
        self._joue = False
        self.bouton_pause.setText("Pause")
        self.progression.setValue(0)
        self.horloge.setText("")
        self._afficher_message(message)
        self._rafraichir_boutons()
