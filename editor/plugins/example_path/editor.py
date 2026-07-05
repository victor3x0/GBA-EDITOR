"""
Plugin exemple : PathComponent — waypoint-based movement.

Décommentez pour l'activer.
"""
# import dataclasses
# from PyQt6.QtWidgets import QSpinBox, QCheckBox
# from core.project import COMPONENT_REGISTRY
# from ui.scene_manager.inspectors.component_editors import register, BaseComponentEditor
#
#
# @dataclasses.dataclass
# class PathComponent:
#     id:     str  = "path"
#     active: bool = True
#     speed:  int  = 60
#     loop:   bool = False
#
# COMPONENT_REGISTRY["path"] = PathComponent
#
#
# @register("path")
# class PathEditor(BaseComponentEditor):
#
#     def build(self, comp, row, layout):
#         sp = QSpinBox(); sp.setRange(1, 500); sp.setValue(comp.speed)
#         sp.valueChanged.connect(lambda v: self.set_field(comp, "speed", v))
#         row("Speed", sp)
#
#         chk = QCheckBox("Loop"); chk.setChecked(comp.loop)
#         chk.toggled.connect(lambda v: self.set_field(comp, "loop", v))
#         layout.addWidget(chk)
#

