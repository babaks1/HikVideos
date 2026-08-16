from operator import mod
import ffmpeg
import os
import logging

logger = logging.getLogger('hikvideos')


def downloadRTSP(url: str, videoName: str, seconds: int = 9999999, debug: bool = False, force: bool = False, skipSeconds: bool = 0):
    """Downloads an RTSP livestream from url to videoName.

    Parameters:
        url (str): the RTSP link to a stream
        videoName (str): the filename of the downloaded stream
        seconds (int): the maximum number of seconds that should be recorded (default is 999999)
        debug (bool): Enables debug logging (default is False)
        force (bool): Forces saving of file (default is False)
        skipSeconds (int): the number of seconds that should be skipped when downloading (default is 0)
    """
    logger.debug("Starting download from: %s" % url)
    try:
        if seconds:
            stream = ffmpeg.input(
                url,
                rtsp_transport="tcp",
                timeout=1,
                t=seconds,
            )
        else:
            stream = ffmpeg.input(
                url,
                rtsp_transport="tcp",
                timeout=1,
            )
        if skipSeconds:
            stream = ffmpeg.output(
                stream,
                videoName,
                ss=skipSeconds
            )
        else:
            stream = ffmpeg.output(
                stream,
                videoName
            )
    except AttributeError:
        raise Exception(
            "The version of ffmpeg used is wrong! Be sure to uninstall ffmpeg using pip and install ffmpeg-python or use a virtualenv! For more information see the README!")
    if os.path.exists(videoName):
        logger.debug(
            "The file %s exists, should have been downloaded from %s" % (videoName, url))
        if force is False:
            logger.warning("%s already exists" % videoName)
            return
        os.remove(videoName)
    try:
        return ffmpeg.run(stream, capture_stdout=debug, capture_stderr=debug)
    except ffmpeg.Error as e:
        logging.error('stdout:', e.stdout.decode('utf8'))
        logging.error('stderr:', e.stderr.decode('utf8'))
        raise e


def processSavedVideo(videoName: str, seconds: int = 9999999, debug: bool = False, skipSeconds: int = 0, fileFormat: str = "mp4", forceTranscode: bool = False):
    """Downloads an RTSP livestream from url to videoName.

    Parameters:
        videoName (str): the filename of the downloaded stream
        seconds (int): the maximum number of seconds that should be recorded (default is 999999)
        debug (bool): Enables debug logging (default is False)
        force (bool): Forces saving of file (default is False)
        skipSeconds (int): the number of seconds that should be skipped when downloading (default is 0)
        forceTranscode (bool): force the transcoding, even if it is not needed (default is False)

    Returns:
        str: le nom du fichier finalement obtenu. Il porte l'extension de
        fileFormat : le fichier téléchargé arrive toujours en .mp4, mais
        une conversion en mkv ou avi doit produire un nom cohérent avec
        son contenu.
    """
    if forceTranscode == False or forceTranscode == None:
        if fileFormat == "mp4":
            if skipSeconds == None and seconds == None:
                logger.debug(
                    "Skipping processing %s since it is not needed" % videoName)
                return videoName
            if skipSeconds == 0 and seconds == 9999999:
                logger.debug(
                    "Skipping processing %s since it is not needed" % videoName)
                return videoName
    logger.debug("Starting processing %s" % videoName)
    try:
        if seconds:
            stream = ffmpeg.input(
                videoName,
                t=seconds,
            )
        else:
            stream = ffmpeg.input(videoName)
        newname = "%s-edited.%s" % (videoName.replace('.mp4', ''), fileFormat)
        if skipSeconds:
            stream = ffmpeg.output(
                stream,
                newname,
                ss=skipSeconds
            )
        else:
            stream = ffmpeg.output(
                stream,
                newname,
            )
    except AttributeError:
        raise Exception(
            "The version of ffmpeg used is wrong! Be sure to uninstall ffmpeg using pip and install ffmpeg-python or use a virtualenv! For more information see the README!")
    try:
        ffmpeg.run(stream, capture_stdout=debug,
                   capture_stderr=debug, overwrite_output=True)
    except ffmpeg.Error as e:
        logging.error('stdout:', e.stdout.decode('utf8'))
        logging.error('stderr:', e.stderr.decode('utf8'))
        raise e

    # Le fichier converti prend le nom d'origine, mais avec l'extension du
    # format demandé. L'amont renommait le résultat en .mp4 quel que soit le
    # format : demander du mkv produisait un fichier mkv nommé .mp4, qui
    # écrasait silencieusement le mp4 précédent puisque les noms
    # coïncidaient.
    finalName = "%s.%s" % (os.path.splitext(videoName)[0], fileFormat)
    os.remove(videoName)
    if os.path.exists(finalName) and os.path.abspath(finalName) != os.path.abspath(newname):
        os.remove(finalName)
    os.rename(newname, finalName)
    return finalName


def downloadRTSPOnlyFrames(url: str, videoName: str, modulo: int, seconds: int = 9999999, debug: bool = False, force: bool = False, skipSeconds: int = 0):
    """Downloads an image for every `modulo` frame from an url and saves it to videoName.

    Parameters:
        url (str): The RTSP link to a stream
        videoName (str): The filename of the downloaded stream
                         should be in the format `{name}_%06d.jpg`
        modulo (int): 
        seconds (int): The maximum number of seconds that should be recorded (default is 9999999)
        debug (bool): Enables debug logging (default is False)
        force (bool): Forces saving of file (default is False)
        skipSeconds (int): The number of seconds that should be skipped when downloading (default is 0)
    """
    if videoName % 1 == videoName % 2:
        raise Exception("videoName cannot be formatted correctly")
    if modulo <= 0:
        raise Exception("modulo is not valid")
    logger.debug("Starting download from: %s" % url)
    try:
        stream = ffmpeg.input(
            url,
            rtsp_transport="tcp",
            timeout=1,
            t=seconds,
        )
        stream = ffmpeg.output(
            stream,
            videoName,
            vf="select=not(mod(n\,%s))" % (modulo),
            vsync="vfr",
            ss=skipSeconds
        )
    except AttributeError:
        raise Exception(
            "The version of ffmpeg used is wrong! Be sure to uninstall ffmpeg using pip and install ffmpeg-python or use a virtualenv! For more information see the README!")
    if os.path.exists(videoName):
        logger.debug(
            "The file %s exists, should have been downloaded from %s" % (videoName, url))
        if force is False:
            logger.warning("%s already exists" % videoName)
            return
        os.remove(videoName)
    try:
        return ffmpeg.run(stream, capture_stdout=debug, capture_stderr=debug)
    except ffmpeg.Error as e:
        logging.error('stdout:', e.stdout.decode('utf8'))
        logging.error('stderr:', e.stderr.decode('utf8'))
        raise e
