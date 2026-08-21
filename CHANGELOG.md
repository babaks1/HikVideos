# Journal des versions

Les versions publiées sont téléchargeables depuis la
[page des releases](../../releases).

## 1.4.2 — 21 août 2026

### Corrigé

- **Les boutons « réduire » et « agrandir » de la première fenêtre ne
  faisaient rien.** Ils étaient bien dessinés par le système, mais restaient
  sans effet : la fenêtre de départ était déclarée comme une boîte de
  dialogue, et l'environnement de bureau refuse ces deux actions aux
  dialogues. Elle est désormais une fenêtre ordinaire.

  Le défaut n'apparaissait que sous Wayland, la session par défaut d'Ubuntu
  depuis plusieurs versions. Sous X11, le gestionnaire de fenêtres accordait
  ces boutons de lui-même.

- **La première fenêtre s'ouvrait dans le coin de l'écran.** Elle s'affiche
  maintenant au centre, comme la seconde.

- **Le plein écran était perdu en passant d'une fenêtre à l'autre.** Il est
  désormais conservé dans les deux sens, sans redimensionnement visible.

### Ajouté

- **La taille des fenêtres est mémorisée d'une session à l'autre.** Les deux
  fenêtres partagent le même réglage : plus besoin de les redimensionner à
  chaque lancement. Si l'application est quittée en plein écran, elle rouvre
  en plein écran — et la taille normale précédente reste conservée pour le
  retour en mode fenêtré.

  Seule la taille est retenue, pas la position : une fenêtre pourrait sinon
  rouvrir hors de l'écran après un changement de moniteur.

### Modifié

- **La touche Échap ne ferme plus la fenêtre de départ.** Elle le faisait
  tant que cette fenêtre était une boîte de dialogue. Sur une fenêtre
  principale, la convention est de l'ignorer — et Échap fermait ici
  l'application entière, ce qui est brutal pour une touche pressée par
  réflexe. Les boutons de la barre de titre restent disponibles.

## 1.4.1 — 21 août 2026

### Corrigé

- **Messages trompeurs à l'arrêt d'un téléchargement.** Interrompre un
  téléchargement affichait « Tous les enregistrements ont été téléchargés »,
  et le fichier interrompu était compté comme récupéré. Le journal indique
  désormais ce qui a réellement été obtenu :
  « Arrêt : 1 fichier(s) récupéré(s) sur 2, 1 interrompu(s) ».

  Le message affiché au clic sur *Arrêter* annonçait par ailleurs que le
  fichier en cours allait se terminer, alors qu'il est interrompu.

- **Fichiers partiels laissés sur le disque.** Le morceau de vidéo
  téléchargé avant un arrêt (fichier `.part`) n'était jamais effacé et
  s'accumulait silencieusement dans le dossier de téléchargement. Il est
  maintenant supprimé. Les fichiers complets du même lot sont conservés.

- **Menus du clic droit en anglais.** Le menu contextuel du journal et des
  champs de saisie affichait « Undo / Copy / Paste… ». Il est désormais en
  français, comme le reste de l'interface.

## 1.4.0 — 20 août 2026

### Ajouté

- **Prévisualiser un enregistrement avant de le télécharger.** Cliquez sur
  une ligne de la liste puis sur *Lire* : la vidéo s'affiche dans une zone
  ajustable sous le journal, sans rien enregistrer sur le disque. De quoi
  reconnaître une scène et choisir quoi télécharger.

  Commandes *Lire*, *Pause* et *Arrêter*. La barre de progression est
  indicative : la caméra ne permet pas de se déplacer dans un enregistrement.

  La prévisualisation et le téléchargement ne peuvent pas avoir lieu en même
  temps — la caméra n'accepte qu'un flux à la fois.

  Rien de nouveau à installer : la lecture utilise ffmpeg, déjà nécessaire
  depuis la version 1.3.0.

### Modifié

- **Seul le flux principal est coché au départ.** Les autres flux de la caméra
  filment la même scène en plus léger : tout cocher téléchargeait chaque
  séquence en double. Cochez ceux que vous voulez, votre choix est retenu pour
  les fois suivantes.

### Corrigé

- Une adresse de caméra saisie avec `http://` est désormais acceptée partout,
  et plus seulement à la connexion.
- **Le raccourci du bureau ne change plus d'une version à l'autre.** Quand le
  paquet est installé, l'exécutable autonome ne redirige plus les raccourcis
  vers sa propre copie : les deux installations se les disputaient, et le
  dernier lancé l'emportait. Le paquet fait désormais autorité.

## 1.3.2 — 19 août 2026

### Corrigé

- **Le raccourci du bureau est mis à jour à l'installation.** Installer le
  paquet par-dessus une installation antérieure de l'exécutable autonome
  laissait le raccourci pointer vers l'ancienne copie : le bureau et le menu
  ouvraient alors des versions différentes, sans aucun signe visible. Le
  script d'installation répare désormais les raccourcis concernés, en
  respectant ceux que l'utilisateur a écrits ou personnalisés.

  Sans effet sur l'installation depuis les sources, dont le raccourci désigne
  une commande et non un chemin.

## 1.3.1 — 18 août 2026

### Corrigé

- **L'adresse de la caméra accepte toutes les formes de saisie.** Écrire
  `http://192.168.1.24` au lieu de `192.168.1.24` faisait échouer la
  connexion sur un message incompréhensible. Le préfixe de protocole, la
  barre oblique finale, les espaces et un chemin collé à l'adresse sont
  désormais ignorés ; `https://` bascule le protocole et un port éventuel
  est conservé. Signalé en amont
  ([HikLoad#40](https://github.com/Tedyst/HikLoad/issues/40)), jamais
  corrigé.
- **Le filtre des enregistrements filtre réellement.** Son `continue` était
  placé après l'ajout à la liste : les éléments non vidéo (photos,
  métadonnées) se retrouvaient dans la sélection.

## 1.3.0 — 18 août 2026

### Corrigé

- **Les fichiers sont réellement convertis dans le format demandé.** La
  caméra livre ses enregistrements dans son propre conteneur — les modèles
  testés renvoient du MPEG-PS. Demander du `mp4` ne convertissait rien : le
  fichier brut était simplement renommé, et son extension mentait sur son
  contenu. VLC s'en accommodait, les logiciels de montage le refusaient.

  Le fichier reçu est maintenant analysé, puis converti seulement si son
  conteneur ne correspond pas à la demande. Le flux vidéo est copié sans
  réencodage : **l'image n'est pas retouchée**, et l'opération prend quelques
  secondes même sur un gros fichier.
- **Une conversion qui échoue ne détruit plus la vidéo.** Le fichier
  téléchargé n'est supprimé qu'une fois le converti écrit et relu.
- **Les combinaisons impossibles sont refusées.** L'AVI ne transporte pas le
  H.265 : ffmpeg écrivait pourtant un fichier illisible sans signaler
  d'erreur. Le fichier est désormais conservé au format d'origine, et
  l'utilisateur prévenu.
- **`--skipseconds`, `--seconds` et `--forcetranscoding` fonctionnent à
  nouveau** en téléchargement direct.
- **Le raccourci du bureau ne lance plus une version antérieure** lorsque le
  paquet a été installé par-dessus l'exécutable autonome.

### Ajouté

- **Format d'origine (sans conversion)** — quatrième choix, qui conserve le
  fichier exact envoyé par la caméra avec l'extension correspondant à son
  contenu réel. Utile pour l'archivage strict.
- **Vérification de ffmpeg au démarrage**, avec un message explicite s'il
  manque.
- **Infobulles détaillées** sur le sélecteur de format et les options
  techniques.

### Modifié

- Libellés clarifiés : « Méthode de secours, plus lente » et « Réparer une
  vidéo illisible (très lent) » remplacent des intitulés qui décrivaient le
  moyen plutôt que l'usage.

## 1.2.1 — 16 août 2026

Première version publique de ce fork.

### Corrigé

- **Le mot de passe n'apparaît plus dans le journal**, y compris en mode
  diagnostic — c'est pourtant ce journal qu'on demande de joindre à un
  rapport d'anomalie.
- **Plantage au démarrage de l'exécutable autonome** : une seconde
  `QApplication` était créée par-dessus la première.
- **Format vidéo** : demander du `mkv` produisait un fichier nommé `.mp4`,
  qui écrasait silencieusement le précédent.
- **Barre de progression** : elle comptait les fichiers et non les octets, et
  débordait au-delà de 2,1 Go.
- **Heures locales** : les sélecteurs étaient en UTC alors que la caméra
  attend un horodatage suffixé « Z ».
- **Fermeture de l'application** : le minuteur n'était jamais arrêté.
- **Correction de `--cameras`**, que la sélection automatique écrasait.

### Ajouté

- **Interface entièrement en français.**
- **Recherche et téléchargement dissociés** : on voit d'abord ce qui existe,
  on choisit ensuite.
- **Sélection par cases à cocher**, avec heure de début, durée, taille et
  canal, et un compteur du volume sélectionné.
- **Mémorisation des réglages** dans `~/.config/hikvideos/`, avec une case
  « Enregistrer le mot de passe » optionnelle.
- **Avertissement au-delà de 5 Go**, avec rappel de l'espace disponible.
- **Paquet `.deb` et exécutable autonome**, icône et raccourci.

### Retiré

- **La fonction « photos »**, expérimentale et inutilisée.
- **Les cases « Concatenate » et « Trim »**, sans effet.

---

Ce projet dérive de [HikLoad](https://github.com/Tedyst/HikLoad) de Stoica
Tedy, dont le développement s'est arrêté en novembre 2023. Il part de la
version 1.1.4 publiée sur PyPI.
