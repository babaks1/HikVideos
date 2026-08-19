# Journal des versions

Les versions publiées sont téléchargeables depuis la
[page des releases](../../releases).

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
