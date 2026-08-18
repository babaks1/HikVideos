import argparse
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List
from io import StringIO
import sys

import ffmpeg
import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

import hikvideos.hikvisionapi as hikvisionapi
from hikvideos.hikvisionapi.classes import HikvisionException
from hikvideos import config, conteneur


class Recording():
    def __init__(self, cid, cname, url, startTime):
        self.cid = cid
        self.cname = cname
        self.url = url
        self.startTime = startTime

    def __str__(self) -> str:
        return "{}-{}".format(self.cname, self.startTime)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Download Recordings from a HikVision server, from a range interval')
    parser.add_argument('--server', type=str, dest="server",
                        help='the hikvision server\'s address')
    parser.add_argument('--username', type=str, dest="username",
                        help='the username')
    parser.add_argument('--password', type=str, dest="password",
                        help='the password')
    parser.add_argument('--starttime', type=lambda s: datetime.fromisoformat(s),
                        default=datetime.now().replace(
                            hour=0, minute=0, second=0, microsecond=0).isoformat(),
                        help='the start time in ISO format (default: today at 00:00:00, local time)')
    parser.add_argument('--endtime', type=lambda s: datetime.fromisoformat(s),
                        default=datetime.now().replace(
                            hour=23, minute=59, second=59, microsecond=0).isoformat(),
                        help='the start time in ISO format (default: today at 23:59:59, local time)')
    parser.add_argument('--folders', type=str, dest="folders", choices=['onepercamera', 'oneperday', 'onepermonth', 'oneperyear'],
                        help='create a separate folder per camera/duration (default: disabled)')
    parser.add_argument('--debug', action=argparse.BooleanOptionalAction, dest="debug",
                        help='enable debug mode (default: false)')
    parser.add_argument('--videoformat', dest="videoformat", default="mp4",
                        choices=['mkv', 'mp4', 'avi', 'original'],
                        help="specify video format; 'original' keeps the "
                             "camera's own container without conversion "
                             "(default: mp4)")
    parser.add_argument('--downloads', dest="downloads", default=os.path.join(os.getcwd(), "Downloads"),
                        help='the downloads folder (default: "Downloads")')
    parser.add_argument('--frames', dest="frames", type=int,
                        help='save a frame for every X frames in the video (default: false)')
    parser.add_argument('--force', dest="force", action=argparse.BooleanOptionalAction,
                        help='force saving of files (default: false)')
    parser.add_argument('--skipseconds', dest="skipseconds", type=int,
                        help='skip first X seconds for each video (default: 0)')
    parser.add_argument('--seconds', dest="seconds", type=int,
                        help='save only X seconds for each video (default: inf)')
    parser.add_argument('--days', dest="days", type=int,
                        help='download videos for the last X days (ignores --endtime and --starttime)')
    parser.add_argument('--skipdownload', dest="skipdownload", action=argparse.BooleanOptionalAction,
                        help='do not download anything')
    parser.add_argument('--allrecordings', dest="allrecordings", action=argparse.BooleanOptionalAction,
                        help='download all recordings saved')
    parser.add_argument('--cameras', dest="cameras", type=lambda s: s.split(","),
                        help='camera IDs to search (example: --cameras=201,301)')
    # Activé par défaut : un fichier nommé « 20260815113652 » pour une vidéo
    # de 13h36 en heure d'été française est déroutant. --no-localtimefilenames
    # rétablit l'horodatage UTC.
    parser.add_argument('--localtimefilenames', dest="localtimefilenames", action=argparse.BooleanOptionalAction,
                        default=True,
                        help='save filenames using date in local time instead of UTC (default: enabled)')
    parser.add_argument('--yesterday', dest="yesterday", action=argparse.BooleanOptionalAction,
                        help='download yesterday\'s videos')
    parser.add_argument('--ffmpeg', dest="ffmpeg", action=argparse.BooleanOptionalAction,
                        help='enable ffmpeg and disable downloading directly from server')
    parser.add_argument('--forcetranscoding', dest="forcetranscoding", action=argparse.BooleanOptionalAction,
                        help='force transcoding if downloading directly from server')
    parser.add_argument('--mock', dest="mock", action=argparse.BooleanOptionalAction,
                        help='enable mock mode  WARNING! This will not download anything from the server')
    parser.add_argument('--ui', dest="ui", action=argparse.BooleanOptionalAction,
                        # If running under PyInstaller, use the UI
                        default=bool(getattr(sys, 'frozen', False)),
                        help='enable UI interface WARNING! Requires Qt5 to be installed')
    args = parser.parse_args()
    return args


def create_folder_and_chdir(dir):
    path = str(dir)
    if not os.path.exists(path):
        os.makedirs(os.path.normpath(path))
        logging.debug("Created folder %s" % path)
    else:
        logging.debug("Folder %s already exists" % path)
    if os.environ.get('RUNNING_IN_DOCKER') == 'TRUE':
        os.chmod(os.path.normpath(path), 0o777)
    os.chdir(os.path.normpath(path))


def finaliser_fichier(temporaire, filename, cid, args):
    """Donne au fichier téléchargé son conteneur et son extension définitifs.

    La caméra livre son propre format — les modèles testés renvoient du
    MPEG-PS, d'autres livrent peut-être déjà du MP4. On analyse ce qui a
    été reçu au lieu de le supposer, et on ne convertit que si le conteneur
    ne correspond pas à ce qui est demandé.

    Le fichier téléchargé n'est supprimé qu'une fois le converti écrit et
    relu : une conversion qui échoue laisse la vidéo intacte, sous son
    format d'origine, plutôt que de la perdre.

    Renvoie le nom du fichier finalement obtenu.
    """
    infos = conteneur.analyser(temporaire)
    if infos is None:
        logging.warning(
            "Format du fichier non reconnu : conservé tel quel (%s)", temporaire)

    format_demande = getattr(args, 'videoformat', 'mp4')

    # Découpe et réencodage imposent de faire travailler ffmpeg, quel que
    # soit le conteneur reçu.
    debut = getattr(args, 'skipseconds', None) or None
    duree = getattr(args, 'seconds', None)
    if duree in (0, 9999999):
        duree = None
    reencoder = bool(getattr(args, 'forcetranscoding', False))
    traitement_demande = bool(debut or duree or reencoder)

    # « original » : aucune conversion, mais une extension qui correspond
    # enfin au contenu réel du fichier.
    if format_demande == 'original' and not traitement_demande:
        extension = conteneur.extension_pour(infos)
        return _renommer(temporaire, filename, cid, extension, args)

    if format_demande == 'original':
        # Découper impose de réécrire le fichier : on garde le conteneur
        # d'origine comme cible.
        format_demande = conteneur.extension_pour(infos)
        if format_demande not in conteneur.FORMATS_FFMPEG:
            format_demande = 'mkv'

    if (infos is not None and not traitement_demande
            and not conteneur.conversion_necessaire(infos, format_demande)):
        logging.debug(
            "Le fichier est déjà au format %s : aucune conversion",
            format_demande)
        return _renommer(temporaire, filename, cid, format_demande, args)

    # Certains conteneurs ne savent pas transporter le codec de la caméra :
    # l'AVI, par exemple, ignore le H.265. Plutôt que d'écrire un fichier
    # que ffmpeg accepte mais qu'aucun lecteur n'ouvre, on conserve la
    # vidéo dans son format d'origine et on le dit.
    codec = infos.get('codec_video') if infos else None
    if not reencoder and not conteneur.conteneur_supporte_video(
            format_demande, codec):
        extension = conteneur.extension_pour(infos)
        garde = _renommer(temporaire, filename, cid, extension, args)
        logging.warning(
            "Le format %s ne peut pas contenir de vidéo %s : le fichier est "
            "conservé au format d'origine (%s). Choisissez mp4 ou mkv pour "
            "ce type d'enregistrement.",
            format_demande, codec, os.path.basename(garde))
        return garde

    destination = _nom_final(filename, cid, format_demande, args)
    provisoire = destination + '.encours'

    logging.debug("Conversion vers %s", format_demande)
    if not conteneur.convertir(temporaire, provisoire, format_demande, infos,
                               debut=debut, duree=duree, reencoder=reencoder):
        # Échec : on garde la vidéo telle qu'elle est arrivée plutôt que de
        # la perdre. L'extension reflète son contenu réel.
        _supprimer_si_present(provisoire)
        extension = conteneur.extension_pour(infos)
        garde = _renommer(temporaire, filename, cid, extension, args)
        logging.error(
            "Conversion impossible : le fichier est conservé au format "
            "d'origine (%s)", garde)
        return garde

    _supprimer_si_present(destination)
    os.replace(provisoire, destination)
    _supprimer_si_present(temporaire)
    return destination


def _nom_final(filename, cid, extension, args):
    """Nom définitif, selon que les vidéos sont rangées par dossier ou non."""
    if getattr(args, 'folders', None):
        return "%s.%s" % (filename, extension)
    return "%s-%s.%s" % (filename, cid, extension)


def _renommer(temporaire, filename, cid, extension, args):
    """Renomme le fichier téléchargé sans toucher à son contenu."""
    destination = _nom_final(filename, cid, extension, args)
    if os.path.abspath(destination) != os.path.abspath(temporaire):
        _supprimer_si_present(destination)
        os.replace(temporaire, destination)
    return destination


def _supprimer_si_present(chemin):
    """Supprime un fichier sans échouer s'il n'existe pas."""
    try:
        os.remove(chemin)
    except OSError:
        pass


def video_download_from_channel(server: hikvisionapi.HikvisionServer, args, url, filename, cid,
                                progress_callback=None):
    start_time = time.perf_counter()
    # Nom provisoire : avec « original », comme lorsque la caméra livre un
    # format inattendu, l'extension définitive n'est connue qu'après analyse
    # du fichier reçu.
    extension_probable = ('mp4' if args.videoformat == 'original'
                          else args.videoformat)
    if args.folders:
        name = "%s.%s" % (filename, extension_probable)
    else:
        name = "%s-%s.%s" % (filename, cid, extension_probable)
    logging.debug("Started downloading %s" % name)
    logging.debug(
        "Files to download: (url: %r, name: %r)" % (url, name))
    if args.frames:
        try:
            url = url.replace(server.host, server.address(
                protocol=False, credentials=True))
            hikvisionapi.downloadRTSPOnlyFrames(
                url, name, debug=args.debug, force=args.force, modulo=args.frames, skipSeconds=args.skipseconds, seconds=args.seconds)
        except ffmpeg.Error as e:
            logging.error(
                "Could not download %s. Try to remove --frames." % name)
            logging.error(e)
    if args.ffmpeg:
        try:
            url = url.replace(server.host, server.address(
                protocol=False, credentials=True))
            hikvisionapi.downloadRTSP(
                url, name, debug=args.debug, force=args.force, skipSeconds=args.skipseconds, seconds=args.seconds)
        except ffmpeg.Error as e:
            logging.error(
                "Could not download %s. Try to remove --fmpeg." % name)
            logging.error(e)
    else:
        # Extension neutre : le format réel n'est connu qu'une fois le
        # fichier reçu. L'ancienne version le nommait « .mp4 » d'emblée,
        # ce qui produisait des fichiers dont l'extension mentait sur le
        # contenu quand la caméra livrait autre chose.
        if args.folders:
            temporaryname = "%s.part" % filename
        else:
            temporaryname = "%s-%s.part" % (filename, cid)
        try:
            r = server.ContentMgmt.search.downloadURI(url)
        except hikvisionapi.HikvisionError as e:
            try:
                supports = server.ContentMgmt.search.get_download_capabilities()
                logging.debug(f'Device capabilities: {supports}')
                if supports['DownloadAbility']['isSupportDownloadbyFileName'] == 'false':
                    logging.error(
                        "Downloading by file name is not supported for this device.")
                    logging.error(
                        "Try to add --ffmpeg to force recording the videos.")
                    logging.error(e)
                    return
                if supports['DownloadAbility']['isSupportDownloadbyTime'] == 'false':
                    logging.error(
                        "Downloading by time is not supported for this device.")
                    logging.error(
                        "Try to add --ffmpeg to force recording the videos.")
                    logging.error(e)
                    return
            except (hikvisionapi.HikvisionError, TypeError) as e:
                logging.error(
                    "Could not get download capabilities. The device dosen't seem to support getting capabilities.")
                logging.error(
                    "Try to add --ffmpeg to force recording the videos.")
                logging.error(e)
                return
            logging.error(
                "Could not download %s. Try to add --ffmpeg." % name)
            logging.error(e)
            return
        # Écriture par morceaux : permet de suivre l'avancement pendant le
        # transfert, au lieu de bloquer sur r.content jusqu'au dernier octet.
        recu = 0
        interrompu = False
        try:
            with open(temporaryname, 'wb') as fichier:
                for morceau in r.iter_content(chunk_size=262144):
                    if not morceau:
                        continue
                    fichier.write(morceau)
                    recu += len(morceau)
                    if progress_callback is not None:
                        # L'appelant décide quoi faire d'un arrêt demandé.
                        if progress_callback(recu) is False:
                            interrompu = True
                            break
        finally:
            # En mode flux, la connexion reste ouverte tant qu'on n'a pas
            # tout lu : la refermer explicitement évite d'épuiser le pool
            # au fil des téléchargements.
            r.close()
        if interrompu:
            logging.info("Téléchargement interrompu : %s" % name)
            return
        # Les paramètres n'ont d'intérêt qu'en diagnostic : le mot de passe
        # y est masqué par le filtre installé au démarrage.
        logging.debug(args)
        try:
            name = finaliser_fichier(temporaryname, filename, cid, args)
        except conteneur.OutilManquant as e:
            logging.error("%s", e)
            logging.error(
                "Le fichier a été téléchargé mais n'a pas pu être converti : %s",
                temporaryname)
            return
    if os.environ.get('RUNNING_IN_DOCKER') == 'TRUE':
        os.chmod(name, 0o777)
    end_time = time.perf_counter()
    run_time = end_time - start_time
    logging.info(f"{name} téléchargé en {run_time:.2f} s")


def search_for_recordings(server: hikvisionapi.HikvisionServer, args) -> List[Recording]:
    start_time = time.perf_counter()
    channelids = []
    channels = []
    if args.cameras:
        for cid in args.cameras:
            channelids.append(cid)
            channels.append({
                'id': str(cid),
                'channelName': str(cid),
            })
    else:
        try:
            channelList = server.Streaming.getChannels()
            for channel in channelList['StreamingChannelList']['StreamingChannel']:
                if (int(channel['id']) % 10 == 1):
                    channelids.append(channel['id'])
                    channels.append(channel)
                logging.info("Flux détectés : %s" % channelids)
        except HikvisionException as e:
            logging.error(
                "Could not get channel list. If you still want to continue, add the argument --cameras with the channel ids you want to download.")
            raise e

    downloadQueue = []
    for channel in channels:
        cname = channel['channelName']
        cid = channel['id']
        if args.days:
            endtime = datetime.now().replace(
                hour=23, minute=59, second=59, microsecond=0)
            starttime = endtime - timedelta(days=args.days)
        elif args.yesterday:
            endtime = datetime.now().replace(
                hour=23, minute=59, second=59, microsecond=0) - timedelta(days=1)
            starttime = endtime - timedelta(days=1)
        else:
            starttime = args.starttime
            endtime = args.endtime

        logging.debug("Using %s and %s as start and end times" %
                      (starttime.isoformat() + "Z", endtime.isoformat() + "Z"))

        try:
            if args.allrecordings:
                recordings = server.ContentMgmt.search.getAllRecordingsForID(
                    cid)
                logging.info("%s enregistrement(s) au total pour le flux %s" %
                             (recordings['CMSearchResult']['numOfMatches'], cid))
            else:
                recordings = server.ContentMgmt.search.getPastRecordingsForID(
                    cid, starttime.isoformat() + "Z", endtime.isoformat() + "Z")
                logging.info("%s enregistrement(s) trouvé(s) pour le flux %s" %
                             (recordings['CMSearchResult']['numOfMatches'], cid))
        except hikvisionapi.classes.HikvisionException as e:
            logging.error("Could not get recordings for channel %s" % cid)
            logging.error(e)
            continue

        # This loops from every recording
        if recordings['CMSearchResult']['numOfMatches'] != "0":
            recordinglist = recordings['CMSearchResult']['matchList']['searchMatchItem']
        else:
            recordinglist = []
        # In case there is only one recording, we need to make it a list
        if type(recordinglist) is not list:
            recordinglist = [recordinglist]
        result = []
        for i in recordinglist:
            result.append(Recording(
                cid=cid,
                cname=cname,
                url=i['mediaSegmentDescriptor']['playbackURI'],
                startTime=i['timeSpan']['startTime']
            ))
            logging.debug("Found recording type %s on channel %s" % (
                i['mediaSegmentDescriptor']['contentType'], cid
            ))
            if i['mediaSegmentDescriptor']['contentType'] != 'video':
                # This recording is not a video, skip it
                continue
        downloadQueue.extend(result)
    end_time = time.perf_counter()
    run_time = end_time - start_time
    logging.info(
        f"{len(downloadQueue)} enregistrement(s) trouvé(s) en {run_time:.2f} s")
    return downloadQueue


def search_for_recordings_mock(args) -> List[Recording]:
    logger = logging.getLogger('hikvideos')
    logger.debug(f"{args=}")
    return [
        Recording(cid=1, cname="Channel 1",
                  startTime="2021-12-19T09:04:46Z", url="https://tedyst.ro"),
        Recording(cid=1, cname="Channel 1",
                  startTime="2021-12-19T09:04:47Z", url="https://tedyst.ro"),
        Recording(cid=1, cname="Channel 1",
                  startTime="2021-12-19T09:04:48Z", url="https://tedyst.ro"),
        Recording(cid=1, cname="Channel 1",
                  startTime="2021-12-19T09:04:49Z", url="https://tedyst.ro"),
        Recording(cid=1, cname="Channel 1",
                  startTime="2021-12-19T09:04:50Z", url="https://tedyst.ro"),
        Recording(cid=1, cname="Channel 1",
                  startTime="2021-12-19T09:04:51Z", url="https://tedyst.ro"),
    ]


def download_recording(server: hikvisionapi.HikvisionServer, args, recordingobj: Recording, original_path,
                       progress_callback=None):
    try:
        logger = logging.getLogger('hikvideos')
        if args.mock:
            logger.info("Mocking download of %s" % recordingobj.url)
            time.sleep(1)
            return
        os.chdir(original_path)
        recording_time = datetime.strptime(
            recordingobj.startTime, "%Y-%m-%dT%H:%M:%SZ")
        if args.folders:
            create_folder_and_chdir(recordingobj.cname)
            if args.folders in ["oneperyear", "onepermonth", "oneperday"]:
                create_folder_and_chdir(recording_time.year)
                if args.folders in ["onepermonth", "oneperday"]:
                    create_folder_and_chdir(recording_time.month)
                    if args.folders in ["oneperday"]:
                        create_folder_and_chdir(recording_time.day)

        # You can choose your own filename, this is just an example
        if args.localtimefilenames:
            date = datetime.strptime(
                recordingobj.startTime, "%Y-%m-%dT%H:%M:%SZ")
            delta = datetime.now(
                timezone.utc).astimezone().tzinfo.utcoffset(datetime.now(timezone.utc).astimezone())
            date = date + delta
            name = re.sub(r'[-T\:Z]', '', date.isoformat())
        else:
            name = re.sub(r'[-T\:Z]', '', recordingobj.startTime)

        if not args.skipdownload:
            video_download_from_channel(
                server, args, recordingobj.url, name, recordingobj.cid,
                progress_callback=progress_callback)
        else:
            logging.debug("Skipping download of %s" % recordingobj.url)

        if args.folders:
            os.chdir(original_path)
    except TypeError as e:
        logging.error(
            "HikVision dosen't apparently like to return correct XML data...")
        logging.error(repr(e))
        logging.error(recordingobj)


def download_recordings(server: hikvisionapi.HikvisionServer, args, downloadQueue: List[Recording]):
    if args.downloads:
        create_folder_and_chdir(args.downloads)
    original_path = os.path.abspath(os.getcwd())
    for recordingobj in tqdm.tqdm(downloadQueue):
        download_recording(server, args, recordingobj, original_path)


def run(args):
    if args.server == "" or args.server == None:
        raise HikvisionException(
            "No server specified! You need to specify a server with --server")
    if args.username == "" or args.username == None:
        raise HikvisionException(
            "No username specified! You need to specify a username with --username")
    if args.password == "" or args.password == None:
        raise HikvisionException(
            "No password specified! You need to specify a password with --password")

    server = hikvisionapi.HikvisionServer(
        args.server, args.username, args.password)

    FORMAT = "[%(name)s - %(funcName)20s() ] %(message)s"
    logging.basicConfig(format=FORMAT)
    logger = logging.getLogger('hikvideos')
    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # Le mode diagnostic journalise les paramètres et les URL, mot de passe
    # compris : on le masque avant que quoi que ce soit ne soit écrit.
    config.proteger_journal(args.password)

    with logging_redirect_tqdm():
        server.test_connection()
        if args.mock:
            downloadQueue = search_for_recordings_mock(args)
            args.skipdownload = True
        else:
            downloadQueue = search_for_recordings(server, args)
        download_recordings(server, args, downloadQueue)
