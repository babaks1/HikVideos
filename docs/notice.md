# Notice d'utilisation

Cette notice décrit HikVideos écran par écran. Pour une présentation courte du
projet et son installation, voir le [README](../README.md).

## Sommaire

- [Avant de commencer](#avant-de-commencer)
- [Fenêtre de démarrage](#fenêtre-de-démarrage)
- [Fenêtre de téléchargement](#fenêtre-de-téléchargement)
- [Où vont les fichiers](#où-vont-les-fichiers)
- [Réglages mémorisés](#réglages-mémorisés)
- [En ligne de commande](#en-ligne-de-commande)
- [Problèmes courants](#problèmes-courants)

---

## Avant de commencer

Il vous faut trois informations, les mêmes que pour ouvrir l'interface web de
la caméra :

- **l'adresse IP** de la caméra sur votre réseau, de la forme `X.X.X.X` ;
- **un identifiant**, généralement `admin` ;
- **le mot de passe** correspondant.

Vérifiez d'abord que la caméra répond, en ouvrant `http://ADRESSE-IP` dans un
navigateur. Si cette page ne s'affiche pas, HikVideos ne pourra rien faire non
plus : le problème est réseau, pas logiciel.

L'appareil doit avoir de quoi enregistrer : une carte microSD sur une caméra
autonome, ses disques sur un enregistreur. Sans support d'enregistrement, ou
si aucun enregistrement n'a été déclenché, les recherches ne renverront rien —
sans que ce soit une panne.

---

## Fenêtre de démarrage

C'est l'écran des réglages. Rien n'est envoyé à la caméra tant que vous n'avez
pas appuyé sur **Connexion**.

### Connexion à la caméra

| Champ | Rôle |
|---|---|
| **Adresse IP de la caméra** | L'adresse sur le réseau local. Sans `http://`. |
| **Identifiant** | Le compte utilisé sur l'interface web, souvent `admin`. |
| **Mot de passe** | Celui du même compte. |
| **Dossier de téléchargement des vidéos** | Où seront écrites les vidéos. Le bouton `...` ouvre un sélecteur de dossier. |

Sous le mot de passe, la case **Enregistrer le mot de passe** est décochée par
défaut, volontairement : si vous la cochez, le mot de passe est écrit **en
clair** dans le fichier de configuration. Ce fichier n'est lisible que par
votre compte utilisateur, mais il reste en clair sur le disque. À vous de
juger — sur un ordinateur personnel c'est généralement acceptable, sur une
machine partagée, non.

### Le bouton Connexion

Il interroge la caméra et remplit la liste **Flux disponibles**. Tant qu'il
n'a pas réussi, le bouton **Rechercher** demeure grisé : c'est normal, cet
ordre garantit qu'on ne cherche pas dans le vide.

En cas d'échec, le message d'erreur indique la cause : adresse injoignable,
identifiants refusés, ou caméra qui ne répond pas au protocole attendu.

### Flux disponibles

Une fois la connexion établie, la liste montre les flux que la caméra propose,
avec leur définition et leur numéro de canal. Chaque ligne suit cette forme :

```
<nom du canal> — <rang du flux> <définition> (<identifiant>)
```

Par exemple, sur une caméra dont le canal a été nommé « ENTREE » :

```
ENTREE — flux principal 3840x2160 (101)
ENTREE — flux secondaire 640x360 (102)
```

Chez vous, l'affichage sera différent : le nom en tête de ligne est celui
**configuré dans la caméra** (« ENTREE », « Jardin », « Camera 01 »…), et la
définition est celle de vos réglages. Si la caméra ne renvoie aucun nom,
HikVideos affiche simplement « Caméra ». De même, le nombre de lignes dépend
de l'appareil : certaines caméras ne proposent qu'un seul flux, d'autres deux
ou trois.

Ce qui ne change pas, en revanche, c'est la structure : le **flux principal**
est la vidéo en pleine définition, le **flux secondaire** une version allégée
que certaines caméras enregistrent en parallèle.

L'identifiant entre parenthèses n'est pas arbitraire non plus : les deux
derniers chiffres donnent le rang du flux (01 principal, 02 secondaire,
03 tertiaire), et ce qui précède est le numéro de la caméra. `101` est donc le
flux principal de la caméra 1, `202` le flux secondaire de la caméra 2.

Les cases cochées déterminent les flux interrogés lors de la recherche. Elles
sont cochées d'office.

### Caméra autonome ou enregistreur

Ce que cette liste contient dépend de l'appareil interrogé :

- **Sur une caméra autonome** — le cas testé — l'appareil est à lui seul la
  caméra 1. La liste montre donc les différents flux d'une seule et même
  caméra (`101`, `102`…), et un seul est généralement utile.
- **Sur un enregistreur (NVR/DVR)**, chaque caméra raccordée porte son propre
  numéro : `101` pour la première, `201` pour la deuxième, `301` pour la
  troisième, et ainsi de suite. La liste énumère alors bien **plusieurs
  caméras**, et cocher plusieurs lignes a tout son sens.

> **Non vérifié.** HikVideos n'a été testé que sur caméra autonome. La prise en
> charge des enregistreurs est héritée du projet d'origine : la numérotation
> ci-dessus est celle de Hikvision et le code la gère, mais aucun essai sur
> NVR ou DVR n'a été mené ici. Si vous en utilisez un, les retours sont
> bienvenus.

Le libellé « caméras » hérité du projet d'origine est donc juste sur
enregistreur, mais trompeur sur caméra autonome, où il ne s'agit que des
canaux d'un seul appareil. HikVideos n'interroge de toute façon qu'une adresse
IP à la fois.

### Période

Deux champs, **Début** et **Fin**, chacun scindé en une date (`jj/mm/aaaa`) et
une heure (`hh:mm:ss`). L'icône de calendrier ouvre un sélecteur.

Ces champs sont en **heure locale**, celle de votre montre. C'est explicitement
indiqué dans les libellés, parce que la caméra, elle, raisonne en UTC — la
conversion est faite pour vous.

Quatre raccourcis évitent la saisie manuelle :

| Raccourci | Période couverte |
|---|---|
| **Aujourd'hui** | de 00:00:00 à 23:59:59 aujourd'hui |
| **Hier** | de 00:00:00 à 23:59:59 hier |
| **7 jours** | des 6 jours précédents 00:00 jusqu'à maintenant |
| **Dernière heure** | les 60 dernières minutes |

### Options

| Option | Effet |
|---|---|
| **Classement des vidéos** | Tout dans le même dossier, ou un sous-dossier par caméra, par jour, par mois ou par an. |
| **Format vidéo** | `mp4` (conseillé), `mkv` ou `avi`. L'extension du fichier suit réellement le choix. |
| **Nommer les fichiers à l'heure locale** | Cochée par défaut : les noms de fichiers portent votre heure et non l'heure UTC. |
| **Remplacer les fichiers déjà téléchargés** | Retélécharge par-dessus un fichier existant. Voir la réserve ci-dessous. |
| **Mode diagnostic** | Journal détaillé, utile pour signaler une anomalie. Le mot de passe y est masqué, mais il contient votre adresse IP. |
| **Utiliser ffmpeg au lieu du téléchargement direct** | Chemin alternatif passant par ffmpeg. Le téléchargement direct est plus rapide et suffit dans la plupart des cas. |
| **Reconvertir la vidéo (fichier endommagé)** | Force une reconversion par ffmpeg, à essayer si une vidéo obtenue est illisible. |

> **Réserve connue.** *Remplacer les fichiers déjà téléchargés* n'agit que sur
> le chemin ffmpeg. En téléchargement direct — celui utilisé par défaut — la
> case n'a aujourd'hui aucun effet. Correctif prévu.

Le bouton **Rechercher** interroge la caméra et ouvre la fenêtre suivante. Il
ne télécharge rien : rechercher et télécharger sont deux étapes distinctes,
pour que vous voyiez d'abord ce qui existe.

---

## Fenêtre de téléchargement

### La liste

Un enregistrement par ligne, avec quatre colonnes :

| Colonne | Contenu |
|---|---|
| **Début (heure locale)** | Heure de démarrage de l'enregistrement. |
| **Durée** | Longueur de la séquence. |
| **Taille** | Poids du fichier. |
| **Canal** | Le flux d'origine (101, 102…). |

Une liste vide signifie qu'aucun enregistrement n'existe sur la période — et
non que le téléchargement a échoué. Élargissez la période, ou vérifiez que la
caméra enregistre bien.

### Sélection

Chaque ligne porte une case à cocher. Le bouton **Tout sélectionner** coche ou
décoche l'ensemble, et le bandeau affiche en permanence le nombre
d'enregistrements retenus et le volume total correspondant.

Lisez ce volume avant de lancer : une journée en 4K se compte facilement en
dizaines de gigaoctets. Au-delà de **5 Go**, HikVideos demande confirmation et
rappelle l'espace disponible sur le disque de destination. L'avertissement ne
bloque jamais — l'espace libre annoncé par le système est peu fiable sur un
disque réseau ou une clé USB, et refuser un téléchargement réalisable serait
pire que le laisser tenter sa chance.

### Téléchargement

Le bouton de téléchargement traite les enregistrements cochés, un par un.

La **barre de progression** compte les octets réellement transférés, pas les
fichiers : elle avance de façon continue pendant chaque transfert. Le
**journal**, horodaté, indique le fichier en cours et signale les erreurs. En
mot de passe est masqué, y compris en mode diagnostic.

**Arrêter** interrompt la série. Le fichier en cours va jusqu'à son terme
avant l'arrêt, pour ne pas laisser de vidéo tronquée sur le disque — comptez
donc quelques secondes de délai.

**Retour** ramène à la fenêtre de démarrage en conservant vos réglages, pour
enchaîner une autre période sans tout ressaisir. Après un téléchargement
terminé, vous pouvez aussi relancer directement une nouvelle sélection depuis
cette même fenêtre.

---

## Où vont les fichiers

Dans le dossier choisi à l'écran de démarrage, éventuellement réparti en
sous-dossiers selon l'option *Classement des vidéos*.

Les noms de fichiers reprennent l'horodatage de l'enregistrement — à votre
heure locale si l'option correspondante est cochée, ce qui est le cas par
défaut — et l'extension suit le format choisi.

---

## Réglages mémorisés

À la fermeture, HikVideos enregistre vos réglages dans :

```
~/.config/hikvideos/config.json
```

Sont mémorisés : l'adresse, l'identifiant, le dossier de téléchargement, le
classement, le format vidéo et les cases à cocher. Le **mot de passe ne l'est
que si vous avez coché la case prévue**.

Le fichier est écrit avec des permissions restreintes (lecture réservée à
votre compte) et remplacé de façon atomique : une coupure en cours d'écriture
ne détruit pas les réglages précédents.

Pour repartir de zéro, supprimez ce fichier — l'application le recréera au
prochain lancement.

Un paramètre passé en ligne de commande reste toujours prioritaire sur la
valeur mémorisée.

---

## En ligne de commande

> **Réservé à l'installation depuis les sources.** Le paquet `.deb` fournit
> l'application graphique uniquement : il ouvre la fenêtre quels que soient les
> arguments passés. Pour piloter HikVideos en ligne de commande, installez-le
> depuis les sources avec `installer.sh` (voir le [README](../README.md)).

Pour un usage automatisé, sans interface graphique. Exemple, à adapter à votre
adresse et à vos dossiers :

```bash
hikvideos --server X.X.X.X --username admin \
          --downloads ~/Videos --localtimefilenames --yesterday
```

Options les plus utiles :

| Option | Rôle |
|---|---|
| `--server` | Adresse IP de la caméra. |
| `--username`, `--password` | Identifiants. |
| `--downloads` | Dossier de destination. |
| `--starttime`, `--endtime` | Période, au format ISO (`2026-08-16T14:30:00`). |
| `--yesterday` | Raccourci pour la journée d'hier. |
| `--days` | Nombre de jours en arrière. |
| `--videoformat` | `mp4`, `mkv` ou `avi`. |
| `--folders` | `onepercamera`, `oneperday`, `onepermonth`, `oneperyear`. |
| `--localtimefilenames` | Nomme les fichiers à l'heure locale. |
| `--cameras` | Canaux à interroger, séparés par des virgules. |
| `--debug` | Journal détaillé. |

`hikvideos --help` donne la liste complète.

> **Attention aux caractères spéciaux.** Si le mot de passe contient `@`, `!`
> ou `$`, entourez-le d'apostrophes simples : `--password 'mot@passe'`. Sans
> quoi le shell l'interprète et la connexion échoue.

---

## Problèmes courants

**La caméra ne répond pas.**
Ouvrez `http://ADRESSE-IP` dans un navigateur. Si la page n'apparaît pas, le
problème est réseau : vérifiez l'adresse, le câble, et que l'ordinateur est
bien sur le même réseau que la caméra.

**Identifiants refusés alors qu'ils sont bons.**
Vérifiez le mot de passe caractère par caractère. En ligne de commande, un `@`
non protégé par des apostrophes suffit à le tronquer.

**La recherche ne renvoie rien.**
La période ne contient probablement aucun enregistrement. Essayez *7 jours*
pour élargir. Vérifiez aussi que le support d'enregistrement est présent
(carte microSD ou disques de l'enregistreur) et que l'appareil est configuré
pour enregistrer. Sur enregistreur, contrôlez que les bons canaux sont cochés.

**Une vidéo téléchargée est illisible.**
Cochez *Reconvertir la vidéo (fichier endommagé)* et retéléchargez-la. Certains
flux exigent un ré-encodage par ffmpeg.

**Le téléchargement s'arrête en cours de route.**
Consultez le journal, qui indique le fichier fautif. Un disque plein ou une
coupure réseau en sont les causes habituelles. Les fichiers déjà obtenus
restent valides ; relancez la sélection pour les suivants.

**L'application ne se lance pas depuis le menu.**
Le raccourci doit être exécutable et marqué comme fiable. Voir le
[README](../README.md) pour l'installation.

**Aucun enregistrement récent n'apparaît, mais les anciens oui.**
La caméra écrit son enregistrement en cours ; il n'est listé qu'une fois la
séquence close. Attendez quelques minutes.

---

## Ce que HikVideos ne fait pas

- **Pas de visionnage en direct.** Utilisez l'interface web de la caméra ou
  VLC. Notez que le RTSP ne donne accès qu'au direct, jamais aux archives —
  d'où le passage par HTTP pour les enregistrements.
- **Pas d'enregistrement continu.** C'est la caméra qui enregistre ; HikVideos
  ne fait que récupérer. Pour un enregistrement permanent sur ordinateur,
  regardez du côté de [Frigate](https://frigate.video/).
- **Un seul appareil à la fois.** Une seule adresse IP est interrogée par
  session — étant entendu qu'un enregistreur donne accès à toutes les caméras
  qui lui sont raccordées.
- **Testé sur caméra autonome uniquement.** Le fonctionnement sur enregistreur
  (NVR/DVR) est hérité du projet d'origine et n'a pas été vérifié ici.
