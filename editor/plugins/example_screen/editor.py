"""
Plugin exemple : un ÉCRAN entier ajouté à la barre de navigation.

Décommentez pour l'activer.

À retenir : ce fichier est importé AVANT la QApplication (cf. main.py), donc
il ne construit aucun widget — il enregistre une FABRIQUE, que la fenêtre
appellera au bon moment. Le widget rendu doit avoir `load_project(project)`
(contrat `ProjectScreen`, ui/screens.py) ; sinon l'écran s'affiche mais ne
reçoit jamais le projet, et le démarrage le signale.
"""
# from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
#
# from ui.screens import register_screen
# from ui.common.theme import C, T
#
#
# class MetricsScreen(QWidget):
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.setStyleSheet(f"background:{C.BG_BASE};")
#         self._lbl = QLabel("No project")
#         self._lbl.setStyleSheet(f"color:{C.TEXT_NORM};font-size:{T.MD}px;")
#         layout = QVBoxLayout(self)
#         layout.addWidget(self._lbl)
#
#     def load_project(self, project):
#         self._lbl.setText(f"{len(project.scenes)} scenes, "
#                           f"{len(project.sprites)} sprites")
#
#
# register_screen("Metrics", MetricsScreen)
