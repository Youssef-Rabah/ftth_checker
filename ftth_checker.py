import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from .ftth_checker_dialog import FtthCheckerDialog


class FtthChecker:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dialog = None

    def initGui(self):
        """Crée le bouton dans la barre d'outils QGIS."""
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action = QAction(
            QIcon(icon_path),
            "FTTH Geometry Checker",
            self.iface.mainWindow()
        )
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("FTTH Tools", self.action)

    def unload(self):
        """Supprime le bouton quand le plugin est désactivé."""
        self.iface.removePluginMenu("FTTH Tools", self.action)
        self.iface.removeToolBarIcon(self.action)

    import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtCore import Qt
from .ftth_checker_dialog import FtthCheckerDialog


class FtthChecker:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action = QAction(
            QIcon(icon_path),
            "FTTH Geometry Checker",
            self.iface.mainWindow()
        )
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("FTTH Tools", self.action)

    def unload(self):
        self.iface.removePluginMenu("FTTH Tools", self.action)
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        if not self.dialog:
            # Qt.Window → fenêtre indépendante avec barre des tâches
            self.dialog = FtthCheckerDialog(None)
            self.dialog.setWindowFlags(
                Qt.Window |
                Qt.WindowMinimizeButtonHint |
                Qt.WindowMaximizeButtonHint |
                Qt.WindowCloseButtonHint
            )
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()