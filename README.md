# HikVideos

Récupérer les enregistrements d'une caméra Hikvision **sans passer par un
enregistreur**, depuis Linux.

## Installation

**[⬇️ Télécharger HikVideos 1.4.1](https://github.com/babaks1/HikVideos/releases/download/v1.4.1/hikvideos_1.4.1_amd64.deb)**

Double-cliquez sur le fichier téléchargé : le logiciel d'installation d'Ubuntu
s'ouvre, cliquez sur *Installer*.

C'est tout — rien d'autre à installer, HikVideos apparaît ensuite dans votre
menu des applications. Pour Ubuntu, Debian et dérivés, en 64 bits.

Pour le désinstaller : `sudo apt remove hikvideos`.

*Vous voulez l'utiliser en ligne de commande, ou modifier le code ? Il existe
une [autre méthode d'installation](#installation-depuis-les-sources).*

## Mettre à jour

HikVideos ne vous prévient pas quand une nouvelle version sort, et ne se met
pas à jour tout seul. Pour vérifier, rendez-vous sur la
**[page des versions](https://github.com/babaks1/HikVideos/releases/latest)** :
elle affiche toujours la plus récente.

Si elle est plus récente que la vôtre, téléchargez son fichier `.deb` et
double-cliquez dessus, exactement comme pour l'installation. La nouvelle
version remplace l'ancienne, vos réglages sont conservés. Rien à désinstaller
au préalable.

Pour connaître votre version : `apt show hikvideos | grep Version`.

## À qui ça s'adresse

Vous avez une caméra Hikvision autonome — une caméra seule, branchée au
réseau, qui enregistre sur sa propre carte microSD — et vous voulez récupérer
ses vidéos sur votre ordinateur.

Le problème : l'interface web de ces caméras ne propose **pas d'onglet
Lecture**. On voit le direct, on règle les paramètres, mais rien pour relire
ou télécharger ce qui a été enregistré. Le logiciel officiel de Hikvision pour
Linux, iVMS-4200, est resté en version bêta de 2014 et n'est plus utilisable.

HikVideos comble ce manque : il interroge la caméra, affiche la liste des
enregistrements sur la période demandée, et télécharge ceux que vous
sélectionnez.

Vous pouvez aussi **prévisualiser un enregistrement avant de le télécharger** :
cliquez sur une ligne de la liste, puis sur *Lire*. La vidéo s'affiche dans
l'application, sans rien enregistrer sur votre disque — de quoi reconnaître
une scène et ne récupérer que ce qui vous intéresse.

## Ce que ça ne fait pas

- Pas de visionnage en direct — utilisez l'interface web de la caméra ou VLC.
  La prévisualisation ne concerne que les enregistrements déjà sur la carte.
- Pas d'avance rapide ni de retour arrière pendant la prévisualisation : la
  caméra ne permet pas de se déplacer dans un enregistrement à distance.
- Pas d'enregistrement continu : c'est la caméra qui enregistre, ce logiciel
  ne fait que récupérer. Pour un enregistrement permanent sur ordinateur,
  regardez plutôt du côté de [Frigate](https://frigate.video/).
- Testé sur caméra autonome. Le fonctionnement sur enregistreur (NVR/DVR) est
  hérité du projet d'origine mais n'est pas vérifié ici.

## Installation depuis les sources

L'installation par le `.deb` décrite plus haut suffit pour utiliser
HikVideos. Cette méthode-ci est nécessaire pour l'utiliser en ligne de
commande, ou pour modifier le code :

```bash
git clone https://github.com/babaks1/HikVideos.git
cd HikVideos
./installer.sh
```

Le script installe ce qu'il faut, crée un environnement Python isolé, et
propose d'ajouter HikVideos au menu des applications. Il demandera le mot de
passe administrateur pour les paquets système. Le script
`packaging/desinstaller.sh` défait cette installation.

Testé sous Ubuntu 24.04 avec Python 3.12.

## Utilisation

Lancez HikVideos depuis le menu des applications, ou en ligne de commande :

```bash
source venv/bin/activate
hikvideos-qt
```

Au démarrage, renseignez l'adresse de la caméra, l'identifiant et le mot de
passe, puis **Connexion** pour vérifier que la caméra répond.

Choisissez ensuite la période — les raccourcis *Aujourd'hui*, *Hier*,
*7 jours* et *Dernière heure* évitent de saisir les dates à la main — puis
**Rechercher**.

La liste affiche les enregistrements trouvés avec leur heure de début, leur
durée et leur taille. Cochez ceux qui vous intéressent : le bandeau indique
combien sont sélectionnés et le volume total. Puis lancez le téléchargement.

Le bouton **Arrêter** interrompt un téléchargement en cours ; le fichier en
cours se termine proprement pour ne pas laisser de vidéo tronquée.

### En ligne de commande

Disponible avec l'installation depuis les sources. Le paquet `.deb` fournit
l'application graphique seule : il ouvre la fenêtre quels que soient les
arguments passés.

Pour un usage automatisé, sans interface :

```bash
hikvideos --server X.X.X.X --username admin \
        --downloads ~/Videos --localtimefilenames --yesterday
```

`hikvideos --help` liste toutes les options.

### Pour aller plus loin

La [notice d'utilisation](docs/notice.md) détaille chaque écran, chaque option
et les problèmes courants.

Le [journal des versions](CHANGELOG.md) récapitule ce qui a changé d'une
version à l'autre.

## Différences avec le projet d'origine

Ce dépôt est un fork de [Tedyst/HikLoad](https://github.com/Tedyst/HikLoad),
dont le développement s'est arrêté en novembre 2023. Le travail original est
de Stoica Tedy, sous licence MIT, conservée à l'identique.
Ce fork est distribué sous GPL v3 (voir [Licence](#licence)).

Il part de la version 1.1.4 publiée sur PyPI — celle qu'installe `pip` — et
non de la branche principale du dépôt d'origine, dont elle avait divergé.

L'interface graphique a été retravaillée pour l'usage sur caméra autonome :

- **Recherche et téléchargement dissociés** : on voit d'abord ce qui existe,
  on choisit ensuite. L'original téléchargeait tout ce qu'il trouvait.
- **Sélection par cases à cocher**, avec heure de début, durée, taille et
  canal pour chaque enregistrement, et un compteur du volume sélectionné.
- **Bouton Arrêter** réellement fonctionnel.
- **Nouvelle recherche** sans avoir à relancer le programme.
- **Heures locales** : les sélecteurs de date étaient en UTC alors que la
  caméra reçoit un horodatage suffixé « Z ». En heure d'été française,
  demander 00:00–23:59 cherchait en réalité de 02:00 à 01:59. Corrigé.
- **Date et heure séparées**, avec des raccourcis de période.
- **Correction de `--cameras`**, que la sélection automatique écrasait.
- **Fichiers réellement convertis** : demander du `mp4` produisait un fichier
  au format brut de la caméra, simplement renommé — l'extension mentait sur
  son contenu, et les logiciels de montage le refusaient. Le conteneur reçu
  est désormais analysé, puis converti si nécessaire, sans jamais retoucher
  l'image. Un choix **Format d'origine** conserve le fichier tel quel, avec
  l'extension qui lui correspond.
- **Journal épuré** et horodaté.
- **Suppression de la fonction « photos »**, expérimentale et inutilisée,
  corrigée dans le fichier d'interface source pour ne pas réapparaître.
- **Installation** : dépendances non figées, compatibles Python 3.12.
- **Raccourci et icône** pour le menu des applications.

## Licence

**GPL v3** — voir [LICENSE](LICENSE). Copyright © 2026 Benjamin TABAKIAN.

Vous pouvez utiliser, modifier et redistribuer ce logiciel librement, y
compris commercialement, à condition de publier le code source de toute
version modifiée sous la même licence.

Le travail d'origine est de Stoica Tedy, 2019
— [Tedyst/HikLoad](https://github.com/Tedyst/HikLoad) — sous licence MIT,
conservée dans [LICENSE-MIT-HikLoad](LICENSE-MIT-HikLoad). Le détail des deux
licences est expliqué dans [LICENSES.md](LICENSES.md).

Projet indépendant, sans lien avec Hangzhou Hikvision Digital Technology.
« Hikvision » est une marque de son propriétaire et n'est mentionnée ici que
pour indiquer le matériel compatible.
