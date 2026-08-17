# Contribuer

Merci de l'intérêt porté à HikVideos. Ce projet est développé sur temps libre
par une seule personne : les réponses peuvent prendre quelques jours.

Les échanges se font en **français ou en anglais**, au choix.

## Signaler un problème

Ouvrez une [issue](../../issues) en indiquant :

- **le modèle de caméra** et sa version de micrologiciel, visibles dans son
  interface web ;
- **s'il s'agit d'une caméra autonome ou d'un enregistreur** (NVR/DVR) — seul
  le premier cas a été testé, l'information est précieuse ;
- **comment reproduire** : les valeurs saisies dans l'interface, ou la ligne de
  commande utilisée ;
- **le journal**, en ayant coché *Mode diagnostic* dans l'interface ou ajouté
  `--debug` en ligne de commande.

> ⚠️ **Relisez le journal avant de le publier.** Le mot de passe y est
> automatiquement masqué, mais il contient votre adresse IP et vos noms de
> fichiers. Remplacez-les par `xxx` si vous préférez ne pas les rendre
> publics.

## Proposer une amélioration

Ouvrez une issue décrivant l'usage visé avant d'écrire du code — cela évite un
travail qui ne serait pas retenu. Jetez d'abord un œil aux issues existantes :
la piste y est peut-être déjà notée.

## Proposer du code

1. Créez une branche à partir de `master`.
2. Faites une modification par branche : une correction ou une fonctionnalité,
   pas les deux.
3. Vérifiez que l'application démarre et qu'un téléchargement aboutit — il n'y
   a pas de tests automatisés.
4. Ouvrez la pull request en décrivant ce qui a été testé, et sur quel matériel.

### Conventions

**Messages de commit en français**, à l'impératif, décrivant l'effet obtenu
plutôt que la manipulation : *« Corrige le format vidéo : le fichier gardait
l'extension .mp4 »* plutôt que *« modif ui.py »*. Voir `git log` pour le ton.

**Interface en français**, accents compris.

**Commentaires expliquant le pourquoi**, pas le comment — en particulier
lorsqu'un contournement répond à un comportement inattendu de la caméra.

### Modifier l'interface graphique

Les fichiers `hikvideos/uifiles/*.py` sont **générés** : les modifier
directement ne sert à rien, la génération suivante les écrase.

Modifiez les fichiers `.ui` correspondants, puis régénérez :

```bash
cd hikvideos/uifiles && ./generate-ui.sh
```

Les deux fichiers, source et généré, sont à inclure dans le commit.

## Installation pour le développement

```bash
git clone https://github.com/babaks1/HikVideos.git
cd HikVideos
./installer.sh
```

Sans caméra sous la main, l'option `--mock` fait fonctionner l'interface avec
des données fictives.

## Portée du projet

HikVideos récupère les enregistrements d'une caméra Hikvision, rien de plus.
Le visionnage en direct, l'enregistrement continu et la détection de mouvement
sortent de son périmètre — d'autres projets, comme
[Frigate](https://frigate.video/), le font mieux.

Les corrections restant compatibles avec la version PyPI d'origine sont
privilégiées ; celles qui imposeraient une réécriture le sont moins.

## Savoir-vivre

Restons courtois et constructifs. Les échanges désobligeants seront clos sans
discussion.

## Licence

Toute contribution est publiée sous licence GPL v3, comme le reste du projet
(voir [LICENSE](LICENSE) et [LICENSES.md](LICENSES.md)).
