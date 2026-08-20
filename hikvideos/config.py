"""Mémorisation des paramètres entre deux lancements.

Les réglages sont écrits dans ~/.config/hikvideos/config.json — l'emplacement
standard sous Linux, respecté par la variable XDG_CONFIG_HOME.

Le mot de passe n'est enregistré que si l'utilisateur le demande
explicitement : le fichier est en clair, seulement protégé par les
permissions du système (lecture réservée au propriétaire).
"""
import json
import logging
import os
from urllib.parse import quote

logger = logging.getLogger('hikvideos')

REMPLACEMENT = '***'

# Réglages mémorisés. Le mot de passe est traité à part, voir sauvegarder().
CHAMPS = (
    'server',
    'username',
    'downloads',
    'folders',
    'videoformat',
    'localtimefilenames',
    'debug',
    'force',
    'ffmpeg',
    'forcetranscoding',
    # Flux cochés dans la liste. Mémorisé comme les autres réglages : sur une
    # caméra autonome, on interroge presque toujours le même.
    'cameras',
)


def _dossier():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'hikvideos')


def chemin():
    return os.path.join(_dossier(), 'config.json')


def charger():
    """Renvoie les réglages enregistrés, ou un dictionnaire vide."""
    try:
        with open(chemin(), encoding='utf-8') as f:
            donnees = json.load(f)
        if not isinstance(donnees, dict):
            return {}
        return donnees
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        # Fichier illisible ou corrompu : on repart des valeurs par défaut
        # plutôt que d'empêcher le démarrage.
        logger.debug("Configuration illisible (%s), valeurs par défaut", e)
        return {}


def sauvegarder(args, enregistrer_mot_de_passe=False):
    """Écrit les réglages courants. Échoue en silence : ce n'est qu'un confort."""
    donnees = {}
    for champ in CHAMPS:
        valeur = getattr(args, champ, None)
        if valeur is not None:
            donnees[champ] = valeur

    if enregistrer_mot_de_passe:
        donnees['password'] = getattr(args, 'password', '') or ''
    donnees['enregistrer_mot_de_passe'] = bool(enregistrer_mot_de_passe)

    try:
        os.makedirs(_dossier(), exist_ok=True)
        cible = chemin()
        # Écriture en deux temps : une coupure en cours d'écriture ne laisse
        # pas un fichier tronqué à la place des réglages précédents.
        temporaire = cible + '.tmp'
        with open(temporaire, 'w', encoding='utf-8') as f:
            json.dump(donnees, f, indent=2, ensure_ascii=False)
        os.replace(temporaire, cible)
        # Le fichier peut contenir un mot de passe : lisible par son
        # propriétaire uniquement.
        os.chmod(cible, 0o600)
        return True
    except OSError as e:
        logger.debug("Configuration non enregistrée (%s)", e)
        return False


def defauts_parseur():
    """Valeurs que le parseur pose quand l'utilisateur ne passe rien.

    Interrogées auprès d'argparse plutôt que recopiées : une valeur par
    défaut qui changerait dans download.py resterait ainsi reconnue.
    """
    try:
        from .download import parse_args
        import argparse
        import sys

        # parse_args() lit sys.argv ; on l'appelle sur une ligne vide pour
        # n'obtenir que les valeurs par défaut.
        sauvegarde = sys.argv
        sys.argv = [sauvegarde[0] if sauvegarde else 'hikvideos']
        try:
            vierge = parse_args()
        finally:
            sys.argv = sauvegarde
        return {champ: getattr(vierge, champ, None) for champ in CHAMPS}
    except (ImportError, SystemExit, argparse.ArgumentError):
        return {}


def appliquer(args, defauts=None):
    """Reporte les réglages enregistrés sur args, sans écraser la ligne de
    commande : un paramètre passé explicitement reste prioritaire.

    `defauts` donne, pour chaque champ, la valeur que le parseur pose quand
    l'utilisateur n'a rien passé. Sans elle, un champ comme --downloads —
    qui a toujours une valeur par défaut — paraîtrait renseigné et le
    réglage mémorisé serait ignoré.
    """
    donnees = charger()
    if not donnees:
        return args, False

    defauts = defauts or {}
    for champ in CHAMPS:
        if champ not in donnees:
            continue
        actuelle = getattr(args, champ, None)
        # Champ vide, ou laissé à la valeur par défaut du parseur : dans les
        # deux cas l'utilisateur n'a rien demandé, le réglage mémorisé prime.
        if actuelle in (None, '', False) or (
                champ in defauts and actuelle == defauts[champ]):
            setattr(args, champ, donnees[champ])

    memorise = bool(donnees.get('enregistrer_mot_de_passe'))
    if memorise and not getattr(args, 'password', ''):
        args.password = donnees.get('password', '')

    return args, memorise


# ----------------------------------------------------------------------
# Masquage du mot de passe dans le journal
# ----------------------------------------------------------------------
class FiltreMotDePasse(logging.Filter):
    """Remplace le mot de passe par « *** » dans tout ce qui est journalisé.

    Le mode diagnostic journalise les paramètres d'exécution (`logging.debug(args)`
    dans download.py) et les URL du serveur, qui contiennent les identifiants.
    Or c'est précisément ce journal qu'on demande de joindre à un rapport
    d'anomalie : sans masquage, le mot de passe de la caméra se retrouve
    publié.

    Le filtre est posé sur le logger plutôt que corrigé à chaque appel : il
    couvre ainsi les messages à venir, y compris ceux du code hérité de
    l'amont.
    """

    def __init__(self, mot_de_passe=''):
        super().__init__()
        self.mot_de_passe = mot_de_passe or ''

    def _masquer(self, texte):
        if not self.mot_de_passe:
            return texte
        # Le mot de passe apparaît tel quel (Namespace(password='x')) ou
        # encodé dans une URL (http://user:x@hote) : les deux formes sont
        # remplacées.
        texte = texte.replace(self.mot_de_passe, REMPLACEMENT)
        encode = quote(self.mot_de_passe, safe='')
        if encode != self.mot_de_passe:
            texte = texte.replace(encode, REMPLACEMENT)
        return texte

    def filter(self, record):
        if not self.mot_de_passe:
            return True

        # record.msg peut être un objet (Namespace, exception...) : on ne le
        # convertit en texte que s'il contient effectivement le mot de passe,
        # pour ne pas casser le formatage différé des autres messages.
        if isinstance(record.msg, str):
            record.msg = self._masquer(record.msg)
        else:
            rendu = str(record.msg)
            if self.mot_de_passe in rendu:
                record.msg = self._masquer(rendu)
                record.args = ()

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    cle: self._masquer(valeur) if isinstance(valeur, str)
                    else valeur
                    for cle, valeur in record.args.items()}
            else:
                record.args = tuple(
                    self._masquer(valeur) if isinstance(valeur, str) else valeur
                    for valeur in record.args)
        return True


def proteger_journal(mot_de_passe):
    """Installe le masquage du mot de passe sur tout ce qui est journalisé.

    Le filtre est posé sur les *handlers*, pas sur un logger : une bonne
    partie du code hérité appelle `logging.debug(...)` directement, ce qui
    passe par le logger racine et non par « hikvideos ». Un filtre de logger
    ne verrait pas ces messages, alors que tout finit par traverser un
    handler.

    À rappeler si le mot de passe change en cours de session.
    """
    cibles = [logging.getLogger(), logging.getLogger('hikvideos')]
    for cible in cibles:
        for handler in cible.handlers:
            for existant in list(handler.filters):
                if isinstance(existant, FiltreMotDePasse):
                    handler.removeFilter(existant)
            if mot_de_passe:
                handler.addFilter(FiltreMotDePasse(mot_de_passe))
