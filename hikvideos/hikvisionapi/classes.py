from hikvideos.hikvisionapi._System import _System
from hikvideos.hikvisionapi._Streaming import _Streaming
from hikvideos.hikvisionapi._ContentMgmt import _ContentMgmt
from requests.exceptions import ConnectionError


class HikvisionException(Exception):
    pass


def nettoyer_adresse(host, protocol="http"):
    """Ramène une adresse saisie à un hôte nu, sans protocole ni chemin.

    Saisir « http://192.168.1.24 » produisait une URL
    « http://user:pass@http://192.168.1.24/ISAPI », rejetée par requests avec
    un message incompréhensible. On nettoie plutôt que de laisser échouer.

    Le lecteur intégré en dépend aussi : QUrl.setHost() rejette
    silencieusement une adresse contenant un protocole, un chemin ou des
    espaces, et laisse l'hôte vide au lieu de signaler l'erreur.

    Renvoie le couple (hôte, protocole) — saisir « https:// » impose ce
    protocole.
    """
    host = (host or "").strip()
    for prefixe in ("https://", "http://"):
        if host.lower().startswith(prefixe):
            if prefixe == "https://":
                protocol = "https"
            host = host[len(prefixe):]
            break
    # Une barre oblique finale, ou un chemin collé à l'adresse, casse
    # la construction de l'URL de la même manière.
    return host.rstrip("/").split("/")[0], protocol


class HikvisionServer:
    """This is a class for storing basic info about a DVR/NVR.

    Parameters:
        host (str): The host address, without `http` or `https`
        user (str): The username for the DVR
        password (str): The password
        protocol (str): The intended protocol
                        Should be `http`(default) or `https`
    """

    def __init__(self, host, user, password, protocol="http"):
        host, protocol = nettoyer_adresse(host, protocol)

        self.host = host
        self.protocol = protocol
        self.user = user
        self.password = password
        self.System = _System(self)
        self.Streaming = _Streaming(self)
        self.ContentMgmt = _ContentMgmt(self)

    def __repr__(self) -> str:
        return "%s(host=%s, protocol=%s, user=%s)" % (self.__class__.__name__, self.host, self.protocol, self.user)

    def __eq__(self, o: object) -> bool:
        if o.__class__ is self.__class__:
            return (self.host, self.protocol, self.user, self.password) == (o.host, o.protocol, o.user, o.password)
        else:
            return NotImplemented

    def __ne__(self, o: object) -> bool:
        result = self.__eq__(o)
        if result is NotImplemented:
            return NotImplemented
        else:
            return not result

    def address(self, protocol: bool = True, credentials: bool = True):
        """This returns the formatted address of the DVR

        Parameters:
            protocol (bool): Includes the `http`/`https` part in URL (default is True)
            credentials (bool): Includes the credentials in URL (default is True)
        """
        string = ""
        if protocol:
            string += self.protocol + "://"
        if credentials:
            string += "%s:%s@" % (self.user, self.password)
        string += self.host + "/ISAPI"
        return string

    def test_connection(self):
        """This method tests the connection to the DVR"""
        try:
            self.System.getDeviceInfo()
        except HikvisionException as e:
            raise HikvisionException("Error while testing connection: %s" % e)
        except ConnectionError as e:
            raise HikvisionException("Error while testing connection: %s" % e)


class Hasher(dict):
    # https://stackoverflow.com/a/3405143/190597
    def __missing__(self, key):
        value = self[key] = type(self)()
        return value
