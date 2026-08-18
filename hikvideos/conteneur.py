"""Analyse et conversion du conteneur des fichiers téléchargés.

Les caméras Hikvision ne livrent pas toutes le même format. Celles testées
renvoient du MPEG-PS — un conteneur des années 1990, celui des DVD — alors
que le fichier était nommé « .mp4 » sans conversion : l'extension mentait
sur le contenu, et les logiciels stricts (montage, lecteurs mobiles)
refusaient le fichier.

Rien ne garantit que ce soit le cas de tous les modèles : d'autres caméras
livrent peut-être déjà du MP4. On analyse donc ce qui a été reçu au lieu de
le supposer, et on ne convertit que si c'est nécessaire.

La conversion recopie le flux vidéo sans le réencoder : l'image n'est pas
retouchée, la qualité est identique et l'opération est limitée par le
disque, pas par le processeur (de l'ordre de 350 Mo/s).
"""
import json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger('hikvideos')

# Extension à donner à un fichier selon le conteneur détecté, quand
# l'utilisateur demande à conserver le format d'origine. ffprobe renvoie une
# liste de noms séparés par des virgules ("mov,mp4,m4a,..."), d'où la
# recherche par appartenance plutôt que par égalité.
EXTENSIONS_CONNUES = (
    ('matroska', 'mkv'),
    ('mp4', 'mp4'),
    ('mpegts', 'ts'),
    ('mpeg', 'mpg'),
    ('avi', 'avi'),
    ('asf', 'asf'),
    ('flv', 'flv'),
)

# Conteneurs que le format demandé accepte déjà : inutile de convertir.
EQUIVALENCES = {
    'mp4': ('mp4', 'mov', 'm4a'),
    'mkv': ('matroska',),
    'avi': ('avi',),
}

# Nom du conteneur attendu par ffmpeg pour chaque format proposé : il ne
# coïncide pas toujours avec l'extension (mkv → matroska).
FORMATS_FFMPEG = {
    'mp4': 'mp4',
    'mkv': 'matroska',
    'avi': 'avi',
}

# Codecs vidéo que chaque conteneur sait transporter sans réencodage.
# AVI est un format de 1992 : il ignore le H.265 et, plus gênant, ffmpeg
# accepte d'écrire le fichier en marquant le flux « rawvideo » — le résultat
# est illisible sans qu'aucune erreur ne soit signalée.
VIDEO_ACCEPTEE = {
    'mp4': ('h264', 'hevc', 'mpeg4', 'av1'),
    'mkv': None,          # Matroska accepte tout.
    'avi': ('mpeg4', 'mjpeg', 'msmpeg4v3'),
}

# Codecs audio que le conteneur MP4 refuse. La caméra testée produit du
# G.711 (pcm_mulaw) — une piste muette, mais qui empêche l'écriture du MP4.
AUDIO_REFUSE_PAR_MP4 = ('pcm_mulaw', 'pcm_alaw', 'pcm_s16le', 'pcm_u8')

# En dessous de ce niveau, une piste est considérée muette. Une caméra sans
# micro écrit tout de même une piste audio, remplie de silence numérique
# (mesuré à -91 dB, valeur constante).
SEUIL_SILENCE_DB = -80.0


class OutilManquant(Exception):
    """ffmpeg ou ffprobe est introuvable sur le système."""


def outils_presents():
    """Renvoie (ffmpeg, ffprobe) : chemins trouvés, ou None."""
    return shutil.which('ffmpeg'), shutil.which('ffprobe')


def verifier_outils():
    """Lève OutilManquant si ffmpeg n'est pas utilisable.

    Appelé avant toute conversion : sans cette vérification, l'absence de
    ffmpeg remonte sous forme de FileNotFoundError, illisible pour
    l'utilisateur.
    """
    chemin_ffmpeg, chemin_ffprobe = outils_presents()
    manquants = [nom for nom, chemin in
                 (('ffmpeg', chemin_ffmpeg), ('ffprobe', chemin_ffprobe))
                 if not chemin]
    if manquants:
        raise OutilManquant(
            "%s %s. Installez le paquet ffmpeg :  sudo apt install ffmpeg"
            % (" et ".join(manquants),
               "sont introuvables" if len(manquants) > 1 else "est introuvable"))


def _lancer(commande, delai=300):
    """Exécute une commande externe et renvoie (succès, sortie standard)."""
    try:
        resultat = subprocess.run(
            commande, capture_output=True, timeout=delai, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Échec de %s : %s", commande[0], e)
        return False, ''
    if resultat.returncode != 0:
        logger.debug("%s a échoué : %s", commande[0],
                     resultat.stderr.decode('utf-8', 'replace')[:400])
        return False, resultat.stdout.decode('utf-8', 'replace')
    return True, resultat.stdout.decode('utf-8', 'replace')


def analyser(chemin):
    """Décrit le fichier : conteneur, codecs, présence d'une piste audio.

    Renvoie un dictionnaire, ou None si le fichier est illisible. L'analyse
    ne lit que les en-têtes : elle coûte quelques dizaines de millisecondes,
    quelle que soit la taille du fichier.
    """
    _, chemin_ffprobe = outils_presents()
    if not chemin_ffprobe:
        return None

    ok, sortie = _lancer([
        chemin_ffprobe, '-v', 'error',
        '-show_entries', 'format=format_name',
        '-show_entries', 'stream=codec_type,codec_name',
        '-of', 'json', chemin], delai=60)
    if not ok or not sortie.strip():
        return None

    try:
        donnees = json.loads(sortie)
    except ValueError:
        return None

    conteneurs = (donnees.get('format', {}).get('format_name') or '').split(',')
    flux = donnees.get('streams') or []
    audio = [f for f in flux if f.get('codec_type') == 'audio']
    video = [f for f in flux if f.get('codec_type') == 'video']

    return {
        'conteneurs': [c.strip() for c in conteneurs if c.strip()],
        'codec_video': video[0].get('codec_name') if video else None,
        'codec_audio': audio[0].get('codec_name') if audio else None,
        'a_du_son': bool(audio),
    }


def extension_pour(infos):
    """Extension correspondant au conteneur réellement détecté.

    Un fichier illisible ne reçoit pas d'extension vidéo : la nommer
    « .mpg » laisserait croire à un enregistrement exploitable.
    « .brut » signale qu'il faut l'examiner.
    """
    if not infos:
        return 'brut'
    for motif, extension in EXTENSIONS_CONNUES:
        if motif in infos['conteneurs']:
            return extension
    return 'brut'


def conversion_necessaire(infos, format_demande):
    """Le fichier reçu correspond-il déjà au format demandé ?

    Évite de faire travailler ffmpeg pour rien sur les caméras qui livrent
    déjà le bon conteneur.
    """
    if not infos:
        # Analyse impossible : on convertit, c'est le choix prudent.
        return True
    acceptes = EQUIVALENCES.get(format_demande)
    if not acceptes:
        return True
    return not any(c in infos['conteneurs'] for c in acceptes)


def piste_audio_muette(chemin):
    """Détecte une piste audio entièrement silencieuse.

    Les caméras sans micro écrivent malgré tout une piste, remplie de
    silence. La mesure ne porte que sur l'audio (64 kbit/s) : elle reste
    de l'ordre de 50 ms même sur une vidéo longue.
    """
    chemin_ffmpeg, _ = outils_presents()
    if not chemin_ffmpeg:
        return False

    # volumedetect écrit son résultat sur la sortie d'erreur, pas sur la
    # sortie standard : on lance directement plutôt que de passer par
    # _lancer(), qui ne renvoie que cette dernière.
    try:
        resultat = subprocess.run(
            [chemin_ffmpeg, '-hide_banner', '-y', '-i', chemin,
             '-vn', '-af', 'volumedetect', '-f', 'null', os.devnull],
            capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Analyse audio impossible : %s", e)
        return False

    for ligne in resultat.stderr.decode('utf-8', 'replace').splitlines():
        if 'max_volume:' in ligne:
            try:
                niveau = float(ligne.split('max_volume:')[1].split('dB')[0])
            except (IndexError, ValueError):
                return False
            logger.debug("Niveau audio maximal : %.1f dB", niveau)
            return niveau <= SEUIL_SILENCE_DB
    return False


def _options_audio(chemin, infos, format_cible):
    """Décide du sort de la piste audio.

    Une caméra sans micro écrit malgré tout une piste, remplie de silence :
    on la retire plutôt que de la convertir pour rien. Une piste réellement
    sonore est conservée — convertie en AAC si le conteneur cible refuse son
    codec, copiée telle quelle sinon.
    """
    if not infos or not infos.get('a_du_son'):
        return ['-an']

    if piste_audio_muette(chemin):
        logger.debug("Piste audio muette : retirée du fichier converti")
        return ['-an']

    codec = infos.get('codec_audio')
    if format_cible == 'mp4' and codec in AUDIO_REFUSE_PAR_MP4:
        # Le conteneur MP4 n'accepte pas le G.711 des caméras : sans
        # réencodage, l'écriture du fichier échoue.
        logger.debug("Audio %s réencodé en AAC pour le conteneur MP4", codec)
        return ['-c:a', 'aac', '-b:a', '128k']
    return ['-c:a', 'copy']


def conteneur_supporte_video(format_cible, codec_video):
    """Le conteneur visé sait-il transporter ce codec sans réencodage ?"""
    acceptes = VIDEO_ACCEPTEE.get(format_cible, ())
    if acceptes is None:      # Matroska : aucune restriction.
        return True
    if not codec_video:
        return True
    return codec_video in acceptes


def convertir(source, destination, format_cible, infos=None,
              debut=None, duree=None, reencoder=False):
    """Réécrit le fichier dans le conteneur demandé.

    Par défaut le flux vidéo est copié tel quel : aucune perte de qualité,
    et une durée limitée par le disque plutôt que par le processeur.

    `debut` et `duree` découpent l'enregistrement (en secondes).
    `reencoder` refabrique l'image au lieu de la copier — lent et
    destructeur, mais seule issue pour un fichier abîmé.

    La source n'est jamais supprimée ici : l'appelant ne le fait qu'après
    avoir constaté que la destination est valide. Une conversion interrompue
    laisse donc le fichier téléchargé intact.

    Renvoie True si la destination a été écrite et est lisible.
    """
    verifier_outils()
    chemin_ffmpeg, _ = outils_presents()

    if infos is None:
        infos = analyser(source)

    commande = [chemin_ffmpeg, '-hide_banner', '-y', '-v', 'error']
    # -ss avant -i : ffmpeg se place directement au bon endroit au lieu de
    # décoder depuis le début.
    if debut:
        commande += ['-ss', str(debut)]
    commande += ['-i', source]
    if duree:
        commande += ['-t', str(duree)]
    commande += ['-c:v', 'libx265' if reencoder else 'copy']
    commande += _options_audio(source, infos, format_cible)
    # Le conteneur est imposé explicitement : la destination est un fichier
    # provisoire dont l'extension ne renseigne pas ffmpeg sur le format
    # attendu.
    commande += ['-f', FORMATS_FFMPEG.get(format_cible, format_cible)]
    if format_cible == 'mp4':
        # Place l'index en tête : la lecture peut commencer avant que tout
        # le fichier soit disponible (utile en lecture réseau).
        commande += ['-movflags', '+faststart']
    commande.append(destination)

    ok, _ = _lancer(commande, delai=1800)
    if not ok:
        return False

    # Un code de retour nul ne garantit pas un fichier exploitable :
    # on vérifie que la destination existe et se laisse relire.
    if not os.path.isfile(destination) or os.path.getsize(destination) == 0:
        logger.debug("Conversion : fichier de destination vide ou absent")
        return False
    controle = analyser(destination)
    if controle is None:
        logger.debug("Conversion : fichier de destination illisible")
        return False

    # Le flux vidéo doit avoir traversé la conversion intact. Un conteneur
    # qui ne sait pas transporter le codec produit un fichier que ffmpeg
    # écrit sans broncher mais qu'aucun lecteur n'ouvre.
    if infos and infos.get('codec_video') and not reencoder:
        if controle.get('codec_video') != infos['codec_video']:
            logger.debug(
                "Conversion : le codec vidéo a changé (%s -> %s), "
                "le conteneur %s ne le supporte pas",
                infos['codec_video'], controle.get('codec_video'),
                format_cible)
            return False
    return True
