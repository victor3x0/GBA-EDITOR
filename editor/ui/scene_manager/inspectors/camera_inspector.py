"""CameraInspector — la caméra de la scène sélectionnée, en tant qu'ASSET.

Reçoit une scène (le canvas sélectionne le rectangle de caméra, cf.
`CameraSelection`) et édite la caméra sur laquelle cette scène démarre. Deux
états, et c'est tout ce qu'il y a à comprendre :

- **la scène emploie la caméra par défaut** — fixe à l'origine, sans bornes ni
  suivi, sans fichier sur le disque. Les réglages sont visibles mais éteints ;
- **la scène désigne une caméra** — tout est éditable, et la même caméra peut
  servir à d'autres scènes (c'est un asset, pas un bien de la scène).

Le passage du premier au second n'est pas un bouton « créer » : il se produit au
premier réglage, y compris le déplacement du cadre dans le canvas
(`Project.ensure_scene_camera`). Personne ne crée une caméra d'avance.

Ce que l'inspecteur ne propose pas : rotation, zoom, projection, viewport. Un
calque régulier ne sait ni tourner ni se mettre à l'échelle (ce sont les calques
affines, v2.0), et découper l'écran est une window matérielle — la scène en
authore déjà. Les proposer promettrait un rendu que le matériel ne produit pas.
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QScrollArea,
    QSpinBox, QPushButton, QMessageBox, QLineEdit, QInputDialog,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from core.models.camera import Camera, CAM_FIXED, CAM_FOLLOW, CAM_SCRIPT
from core.models.scene import Scene
from core.project import Project
from ui.common.theme import C, T, QSS
from ui.common.widgets import ScriptSlot, ScriptPickerPopup

_MODES = [
    (CAM_FIXED,  "Fixed"),
    (CAM_FOLLOW, "Follow an Actor"),
    (CAM_SCRIPT, "Script-driven"),
]

_NO_TARGET = "(none)"
_DEFAULT_CAMERA = "(default)"


class CameraInspector(QWidget):
    """Édite la caméra de démarrage de la scène sélectionnée."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene: Optional[Scene] = None
        self._project: Optional[Project] = None
        self._blocking = False
        self._script_open_fn = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        scroll.setWidget(inner)

        f = QFont(T.UI, T.SM)
        fs = f"color:{C.TEXT_DIM};"

        def _section_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(f)
            lbl.setStyleSheet(fs)
            return lbl

        def _separator():
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color:{C.BORDER};")
            layout.addWidget(sep)

        # ── Quelle caméra cette scène emploie ─────────────────────
        layout.addWidget(_section_label("Camera used by this scene:"))
        pick_row = QHBoxLayout()
        pick_row.setSpacing(6)
        self._combo_camera = QComboBox()
        self._combo_camera.setFont(QFont(T.UI, T.MD))
        self._combo_camera.setStyleSheet(QSS.combobox)
        self._combo_camera.setToolTip(
            "<b>Starting camera of this scene</b><br><br>"
            "A camera is a project asset: the same one can serve several "
            "scenes.<br>A script switches to another with "
            "<code>camera.switch</code>.<br><br>"
            "<b>(default)</b>: fixed at the origin, no bounds, no target — "
            "no file<br>on disk. Changing any setting below turns it into a "
            "real camera."
        )
        self._combo_camera.currentIndexChanged.connect(self._on_camera_picked)
        pick_row.addWidget(self._combo_camera, 1)
        self._ed_name = QLineEdit()
        self._ed_name.setFont(QFont(T.MONO, T.SM))
        self._ed_name.setStyleSheet(QSS.lineedit)
        self._ed_name.setMaximumWidth(120)
        self._ed_name.setPlaceholderText("rename")
        self._ed_name.setToolTip("Rename this camera — scripts citing it are rewritten.")
        self._ed_name.editingFinished.connect(self._on_rename)
        pick_row.addWidget(self._ed_name)
        layout.addLayout(pick_row)

        self._lbl_users = QLabel("")
        self._lbl_users.setFont(QFont(T.UI, T.XS))
        self._lbl_users.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._lbl_users.setWordWrap(True)
        layout.addWidget(self._lbl_users)

        _separator()

        # ── Mode ──────────────────────────────────────────────────
        layout.addWidget(_section_label("Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.setFont(QFont(T.UI, T.MD))
        self._mode_combo.setStyleSheet(QSS.combobox)
        for _, label in _MODES:
            self._mode_combo.addItem(label)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self._mode_combo)

        mode_info = QLabel(
            "Fixed: stays where activation put it.\n"
            "Follow: keeps the chosen Actor inside a deadzone.\n"
            "Script: the engine computes nothing, the script decides."
        )
        mode_info.setFont(QFont(T.UI, T.XS))
        mode_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        mode_info.setWordWrap(True)
        layout.addWidget(mode_info)

        _separator()

        # ── Cadrage de départ (déplacé dans le canvas) ────────────
        layout.addWidget(_section_label("Framing on activation:"))
        row = QHBoxLayout()
        self._x_lbl = QLabel("X: 0")
        self._y_lbl = QLabel("Y: 0")
        for l in (self._x_lbl, self._y_lbl):
            l.setFont(QFont(T.MONO, T.MD))
            l.setStyleSheet(f"color:{C.TEXT_NORM};")
            row.addWidget(l)
        row.addStretch()
        layout.addLayout(row)

        info = QLabel(
            "(Move the yellow rectangle in the canvas.) Applied every time the "
            "camera is activated — scene start, or camera.switch."
        )
        info.setFont(QFont(T.UI, T.XS))
        info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        info.setWordWrap(True)
        layout.addWidget(info)

        _separator()

        # ── Suivi (visible en mode follow) ────────────────────────
        self._follow_group = QWidget()
        fg = QVBoxLayout(self._follow_group)
        fg.setContentsMargins(0, 0, 0, 0)
        fg.setSpacing(8)

        fg.addWidget(_section_label("Follow an Actor:"))
        self._follow_combo = QComboBox()
        self._follow_combo.setFont(QFont(T.UI, T.MD))
        self._follow_combo.setStyleSheet(QSS.combobox)
        self._follow_combo.setToolTip(
            "The actor is named, and actor names are LOCAL to a scene: a camera "
            "reused in a scene without that actor simply stays still there.")
        self._follow_combo.currentTextChanged.connect(self._on_follow_changed)
        fg.addWidget(self._follow_combo)

        margin_row = QHBoxLayout()
        margin_row.setSpacing(10)
        for label, attr in (("Margin X:", "_margin_x"), ("Margin Y:", "_margin_y")):
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont(T.UI, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
            col.addWidget(lbl)
            spin = QSpinBox()
            spin.setFont(QFont(T.MONO, T.MD))
            spin.setStyleSheet(QSS.spinbox)
            spin.setRange(0, 120)
            setattr(self, attr, spin)
            col.addWidget(spin)
            margin_row.addLayout(col)
        margin_row.addStretch()
        fg.addLayout(margin_row)
        self._margin_x.valueChanged.connect(self._on_margins_changed)
        self._margin_y.valueChanged.connect(self._on_margins_changed)

        follow_info = QLabel(
            "Deadzone: the camera only moves once the Actor\n"
            "gets further than Margin X/Y from the screen edge."
        )
        follow_info.setFont(QFont(T.UI, T.XS))
        follow_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        follow_info.setWordWrap(True)
        fg.addWidget(follow_info)

        layout.addWidget(self._follow_group)

        # ── Bornes du monde (rect : origine + taille) ──────────────
        layout.addWidget(_section_label("World bounds (0 = unlimited):"))
        bounds_row = QHBoxLayout()
        bounds_row.setSpacing(10)
        for label, attr in (("Width:", "_bounds_w"), ("Height:", "_bounds_h")):
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont(T.UI, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
            col.addWidget(lbl)
            spin = QSpinBox()
            spin.setFont(QFont(T.MONO, T.MD))
            spin.setStyleSheet(QSS.spinbox)
            # Bornes monde jusqu'à 32767 (s16) → scroll caméra max = 32767 -
            # screen.width (32527 en X, 32607 en Y).
            spin.setRange(0, 32767)
            spin.setSingleStep(8)
            setattr(self, attr, spin)
            col.addWidget(spin)
            bounds_row.addLayout(col)
        bounds_row.addStretch()
        layout.addLayout(bounds_row)
        origin_row = QHBoxLayout()
        origin_row.setSpacing(10)
        for label, attr in (("Origin X:", "_bounds_x"), ("Origin Y:", "_bounds_y")):
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont(T.UI, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
            col.addWidget(lbl)
            spin = QSpinBox()
            spin.setFont(QFont(T.MONO, T.MD))
            spin.setStyleSheet(QSS.spinbox)
            # Origine de la zone scrollable — 0 = le monde commence au bord de
            # l'écran. Presque toujours 0, exposé pour rester cohérent avec le
            # rect camera.bound du script.
            spin.setRange(0, 32767)
            spin.setSingleStep(8)
            setattr(self, attr, spin)
            col.addWidget(spin)
            origin_row.addLayout(col)
        origin_row.addStretch()
        layout.addLayout(origin_row)
        self._bounds_w.valueChanged.connect(self._on_bounds_changed)
        self._bounds_h.valueChanged.connect(self._on_bounds_changed)
        self._bounds_x.valueChanged.connect(self._on_bounds_changed)
        self._bounds_y.valueChanged.connect(self._on_bounds_changed)

        self._btn_recalc = QPushButton("Recompute from backgrounds")
        self._btn_recalc.setFont(QFont(T.UI, T.SM))
        self._btn_recalc.setStyleSheet(QSS.button_ghost)
        self._btn_recalc.setToolTip(
            "Prefills width/height from the background of the SELECTED scene\n"
            "closest to a parallax speed of 1.0 — stays editable afterwards."
        )
        self._btn_recalc.clicked.connect(self._recalc_bounds)
        layout.addWidget(self._btn_recalc)

        bounds_info = QLabel(
            "Applied when the camera is activated. A script can redefine them "
            "afterwards with camera.bound = rect(x, y, w, h)."
        )
        bounds_info.setFont(QFont(T.UI, T.XS))
        bounds_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        bounds_info.setWordWrap(True)
        layout.addWidget(bounds_info)

        _separator()

        # ── Script de caméra ──────────────────────────────────────
        layout.addWidget(_section_label("Camera script:"))
        self._script_slot = ScriptSlot(
            add_label    = "Add a camera script",
            accent_color = C.ACCENT_ORG,
            hint         = "on_start · on_update",
        )
        self._script_slot.set_callbacks(
            on_add   = self._script_new,
            on_open  = self._script_open,
            on_clear = self._script_clear,
        )
        layout.addWidget(self._script_slot)

        script_info = QLabel(
            "Runs AFTER the declarative settings above and BEFORE world bounds "
            "are applied — so it adjusts the framing instead of fighting it."
        )
        script_info.setFont(QFont(T.UI, T.XS))
        script_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        script_info.setWordWrap(True)
        layout.addWidget(script_info)

        layout.addStretch()

        # Tout ce qui n'a de sens qu'avec une caméra RÉELLE.
        self._editors = (
            self._mode_combo, self._follow_group, self._margin_x, self._margin_y,
            self._bounds_w, self._bounds_h, self._bounds_x, self._bounds_y,
            self._btn_recalc, self._script_slot,
            self._ed_name,
        )

    def set_script_open_fn(self, fn):
        self._script_open_fn = fn

    # ── Chargement ────────────────────────────────────────────────

    @property
    def _camera(self) -> Optional[Camera]:
        if not self._scene or not self._project:
            return None
        return self._project.scene_camera(self._scene)

    def load(self, scene: Scene, project: Project):
        self._scene = scene
        self._project = project
        self._refresh()

    def _refresh(self):
        self._blocking = True
        try:
            cam = self._camera
            p = self._project

            self._combo_camera.clear()
            self._combo_camera.addItem(_DEFAULT_CAMERA, "")
            for c in (p.cameras if p else []):
                self._combo_camera.addItem(c.name, c.name)
            idx = self._combo_camera.findData(cam.name if cam else "")
            self._combo_camera.setCurrentIndex(max(0, idx))

            for w in self._editors:
                w.setEnabled(cam is not None)
            self._ed_name.setText(cam.name if cam else "")

            if cam is not None and p is not None:
                users = [s.name for s in p.camera_users(cam.name)]
                others = [n for n in users if not self._scene or n != self._scene.name]
                self._lbl_users.setText(
                    f"Also used by: {', '.join(others)}" if others
                    else "Used by this scene only."
                )
            else:
                self._lbl_users.setText(
                    "No file on disk. Any change below creates a real camera.")

            mode = cam.mode if cam else CAM_FIXED
            self._mode_combo.setCurrentIndex(
                next((i for i, (m, _) in enumerate(_MODES) if m == mode), 0))
            self._follow_group.setVisible(mode == CAM_FOLLOW)

            self._follow_combo.clear()
            self._follow_combo.addItem(_NO_TARGET)
            for actor in (self._scene.actors if self._scene else []):
                self._follow_combo.addItem(actor.name)
            target = cam.follow_target if cam else ""
            if target and self._follow_combo.findText(target) < 0:
                # Cible absente de CETTE scène : la garder visible plutôt que de
                # la réécrire en silence — la caméra sert peut-être ailleurs.
                self._follow_combo.addItem(f"{target}  (not in this scene)")
                self._follow_combo.setCurrentIndex(self._follow_combo.count() - 1)
            else:
                self._follow_combo.setCurrentIndex(
                    max(0, self._follow_combo.findText(target)))

            self._margin_x.setValue(cam.margin_x if cam else 40)
            self._margin_y.setValue(cam.margin_y if cam else 20)
            self._bounds_w.setValue((cam.bounds_w if cam else 0) or 0)
            self._bounds_h.setValue((cam.bounds_h if cam else 0) or 0)
            self._bounds_x.setValue((cam.bounds_x if cam else 0) or 0)
            self._bounds_y.setValue((cam.bounds_y if cam else 0) or 0)
            self._update_position_labels()

            script = (cam.script if cam else "") or ""
            if script:
                self._script_slot.set_script(script.rsplit("/", 1)[-1])
            else:
                self._script_slot.clear_script()
        finally:
            self._blocking = False

    def _update_position_labels(self):
        cam = self._camera
        self._x_lbl.setText(f"X: {cam.x if cam else 0}")
        self._y_lbl.setText(f"Y: {cam.y if cam else 0}")

    # ── Mutations ─────────────────────────────────────────────────

    def _mutable(self) -> Optional[Camera]:
        """La caméra à éditer, matérialisée si la scène est encore au défaut."""
        if not self._scene or not self._project:
            return None
        return self._project.ensure_scene_camera(self._scene)

    def _commit(self, refresh: bool = True):
        """Persiste les DEUX côtés : la caméra, et la scène — sa référence a pu
        naître (matérialisation) ou changer. Ne pas s'en remettre au signal
        `changed` pour ça : il sert à rafraîchir les vues, personne ne s'y est
        abonné pour écrire sur le disque."""
        if self._project:
            if self._camera:
                self._project.cameras.save(self._camera)
            if self._scene:
                self._project.save_scene(self._scene)
        self.changed.emit()
        if refresh:
            self._refresh()

    def _on_camera_picked(self, idx: int):
        if self._blocking or not self._scene:
            return
        self._scene.camera = self._combo_camera.itemData(idx) or ""
        self._commit()

    def _on_rename(self):
        cam = self._camera
        if self._blocking or cam is None or not self._project:
            return
        new = self._ed_name.text().strip()
        if not new or new == cam.name:
            return
        if self._project.cameras.get(new) is not None:
            QMessageBox.warning(self, "Rename camera",
                                f"A camera named '{new}' already exists.")
            self._ed_name.setText(cam.name)
            return
        old = cam.name
        self._project.rename_camera(old, new)
        self._commit()

    def _on_mode_changed(self, idx: int):
        if self._blocking:
            return
        cam = self._mutable()
        if cam is None:
            return
        cam.mode = _MODES[idx][0]
        self._commit()

    def _on_follow_changed(self, text: str):
        if self._blocking:
            return
        cam = self._mutable()
        if cam is None:
            return
        cam.follow_target = "" if text == _NO_TARGET else text.split("  (")[0]
        self._commit(refresh=False)

    def _on_margins_changed(self):
        if self._blocking:
            return
        cam = self._mutable()
        if cam is None:
            return
        cam.margin_x = self._margin_x.value()
        cam.margin_y = self._margin_y.value()
        self._commit(refresh=False)

    def _on_bounds_changed(self):
        if self._blocking:
            return
        cam = self._mutable()
        if cam is None:
            return
        cam.bounds_w = self._bounds_w.value() or None
        cam.bounds_h = self._bounds_h.value() or None
        cam.bounds_x = self._bounds_x.value() or None
        cam.bounds_y = self._bounds_y.value() or None
        self._commit(refresh=False)

    def _recalc_bounds(self):
        """Pré-remplit depuis le fond le plus proche d'une vitesse de 1.0 dans
        la scène SÉLECTIONNÉE — une caméra partagée n'a pas de fond à elle."""
        if not self._scene or not self._project:
            return
        layers = [L for L in self._scene.background_layers if L.background_name]
        if not layers:
            QMessageBox.information(self, "World bounds", "This scene has no background placed.")
            return
        ref = min(layers, key=lambda L: abs(L.scroll_speed - 1.0))
        size = self._bg_pixel_size(ref)
        if size is None:
            QMessageBox.warning(self, "World bounds", f"Could not read dimensions of '{ref.background_name}'.")
            return
        w, h = size
        self._bounds_x.setValue(0)
        self._bounds_y.setValue(0)
        self._bounds_w.setValue(w)
        self._bounds_h.setValue(h)
        # setValue déclenche déjà _on_bounds_changed via valueChanged.

    def _bg_pixel_size(self, layer) -> Optional[tuple[int, int]]:
        ba = self._project.get_background(layer.background_name)
        if ba is None:
            return None
        if getattr(ba, "tileset", None):
            return ba.tiles_w * 8, ba.tiles_h * 8
        png = self._project.background_images_dir / (
            ba.asset if getattr(ba, "asset", None) else f"{layer.background_name}.png"
        )
        try:
            from PIL import Image
            with Image.open(png) as img:
                return img.size
        except Exception:
            return None

    # ── Script ────────────────────────────────────────────────────

    def _script_new(self):
        if not self._project:
            return
        d = self._project.scripts_cameras_dir
        scripts: list[tuple[str, str]] = []
        if d.exists():
            for f in sorted(d.glob("*.lua")):
                rel = str(f.relative_to(self._project.root)).replace("\\", "/")
                scripts.append((f.name, rel))
        popup = ScriptPickerPopup(scripts, C.ACCENT_ORG, parent=self)
        popup.picked.connect(self._script_assign)
        popup.new_requested.connect(self._script_create_new)
        popup.show_below(self._script_slot)

    def _script_assign(self, rel: str):
        cam = self._mutable()
        if cam is None:
            return
        cam.script = rel
        self._commit()

    def _script_create_new(self):
        cam = self._mutable()
        if cam is None:
            return
        name, ok = QInputDialog.getText(self, "New camera script", "Name (without .lua):")
        if not ok or not name.strip():
            return
        from scripting.script_templates import ScriptTemplateContext, generate_script_template
        d = self._project.scripts_cameras_dir
        d.mkdir(parents=True, exist_ok=True)
        sp = d / f"{name.strip()}.lua"
        if not sp.exists():
            ctx = ScriptTemplateContext(kind="camera", name=name.strip(), camera_name=cam.name)
            sp.write_text(generate_script_template(ctx), encoding="utf-8")
        cam.script = str(sp.relative_to(self._project.root)).replace("\\", "/")
        self._commit()
        if self._script_open_fn:
            self._script_open_fn(str(sp))

    def _script_open(self):
        cam = self._camera
        if cam is None or not self._project or not cam.script:
            return
        sp = self._project.asset_abs(cam.script)
        if sp and sp.exists() and self._script_open_fn:
            self._script_open_fn(str(sp))

    def _script_clear(self):
        cam = self._camera
        if cam is None:
            return
        cam.script = ""
        self._commit()
