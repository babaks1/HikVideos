# -*- mode: python ; coding: utf-8 -*-
#
# Produit un exécutable autonome : un seul fichier, qui embarque Python,
# PyQt5 et les dépendances. L'utilisateur télécharge et double-clique.
#
# Construction :  pyinstaller hikvideos.spec

a = Analysis(
    ['packaging/point-entree.py'],
    # '.' met la racine du projet dans le chemin de recherche : sans elle,
    # le paquet hikvideos n'est trouvé qu'à la construction, via le dossier
    # courant, et l'exécutable plante dès qu'il est lancé d'ailleurs.
    pathex=['.', 'packaging'],
    binaries=[],
    datas=[('packaging/hikvideos-256.png', 'packaging')],
    # Imports indirects que l'analyse statique ne voit pas. Les sous-modules
    # de hikvideos sont atteints par des imports différés dans __main__.
    hiddenimports=[
        'xmler', 'lxml._elementpath', 'premier_lancement',
        'hikvideos', 'hikvideos.ui', 'hikvideos.download', 'hikvideos.__main__',
        'hikvideos.config', 'hikvideos.conteneur',
        'hikvideos.uifiles', 'hikvideos.uifiles.Startup',
        'hikvideos.uifiles.MainWindow',
        'hikvideos.hikvisionapi', 'hikvideos.hikvisionapi.classes',
        'hikvideos.hikvisionapi.utils', 'hikvideos.hikvisionapi.RTSPutils',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Modules Qt inutilisés ici : les exclure allège nettement le fichier.
    excludes=[
        'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngineCore', 'PyQt5.QtWebEngine',
        'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtQuick3D', 'PyQt5.QtBluetooth',
        'PyQt5.QtNfc', 'PyQt5.QtPositioning', 'PyQt5.QtLocation',
        'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets', 'PyQt5.QtSensors',
        'PyQt5.QtSerialPort', 'PyQt5.QtTest', 'PyQt5.QtHelp', 'PyQt5.QtSql',
        'PyQt5.QtDesigner', 'PyQt5.QtXmlPatterns',
        'tkinter', 'matplotlib', 'numpy', 'PIL', 'pytest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HikVideos',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='packaging/hikvideos-256.png',
)
