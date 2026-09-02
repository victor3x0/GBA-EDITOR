"""CameraInspector — une caméra PRÉCISE, possédée par la scène sélectionnée.

Reçoit une scène et une caméra (choisie dans le scene tree, ou l'icône cliquée
dans le canvas — cf. `CameraSelection`) et édite CETTE caméra. Deux états :

- **`camera` est `None`** — la scène n'a encore aucune caméra, elle est fixe à
  l'origine, sans bornes ni suivi, sans entrée dans `scene.cameras`. Les
  réglages sont visibles mais éteints ;
- **`camera` est un objet réel** — tout est éditable. Elle n'appartient qu'à
  CETTE scène (révisé le 2026-08-24 — ce n'est plus un asset de projet
  réutilisable, cf. `changelog-archive/v0.6.md`).

Le passage du premier au second n'est pas un bouton « créer » dans CET
inspecteur : il se produit au premier réglage, y compris le déplacement du
cadre dans le canvas (`Project.ensure_scene_camera`) — la création explicite
se fait depuis le scene tree (bouton **+**).

Le combo « Starting camera » est un contrôle SÉPARÉ : il choisit laquelle des
caméras de la scène est celle de démarrage (`scene.camera`), indépendamment de
celle affichée/éditée ici.

Ce que l'inspecteur ne propose pas : rotation, zoom, projection. Un calque
régulier ne sait ni tourner ni se mettre à l'échelle (ce sont les calques
affines, v2.0) — les proposer promettrait un rendu que le matériel ne produit
pas. Le viewport, lui, EST proposé (carte Transform, `frame_w`/`frame_h`,
réglé le 2026-08-24) : WIN0 appartient désormais à la caméra active, WIN1
reste à la scène (`Scene.windows`) — cf. `core/models/camera.py`.
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QScrollArea,
    QSpinBox, QPushButton, QMessageBox, QInputDialog,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from core.models.camera import Camera, CAM_FIXED, CAM_FOLLOW, CAM_SCRIPT
from core.models.scene import Scene
from core.project import Project
from ui.common.theme import C, T, QSS
from ui.common.icons import COLOR_SCRIPT
from ui.common.widgets import ScriptSlot, ScriptPickerPopup, CollapsibleCard

_MODES = [
    (CAM_FIXED,  "Fixed"),
    (CAM_FOLLOW, "Follow an Actor"),
    (CAM_SCRIPT, "Script-driven"),
]

_NO_TARGET = "(none)"
_DEFAULT_CAMERA = "(default)"


class CameraInspector(QWidget):
    """Édite une caméra précise, possédée par la scène sélectionnée."""
    changed = pyqtSignal()
    # Position ou frame édités ICI (pas par drag canvas) — le canvas doit
    # suivre. Symétrique de `update_position`, qui fait le chemin inverse.
    camera_moved = pyqtSignal(object)   # Camera

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene: Optional[Scene] = None
        self._camera: Optional[Camera] = None
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

        # ── Quelle caméra démarre la scène ────────────────────────
        # Renommer CETTE caméra se fait dans l'en-tête partagé (AssetHeaderBar,
        # cf. DynamicInspector._on_header_rename) — même contrat que
        # Scene/Actor/Prefab, pas de second champ « name » ici.
        camera_card = CollapsibleCard("This camera")
        start_row = QHBoxLayout()
        start_row.setSpacing(6)
        start_lbl = QLabel("Starting camera:")
        start_lbl.setFont(QFont(T.UI, T.XS))
        start_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        start_row.addWidget(start_lbl)
        self._combo_camera = QComboBox()
        self._combo_camera.setFont(QFont(T.UI, T.MD))
        self._combo_camera.setStyleSheet(QSS.combobox)
        self._combo_camera.setToolTip(
            "<b>Which of this scene's cameras it starts on</b><br><br>"
            "A script switches to another with <code>camera.switch</code>.<br>"
            "Independent of the camera shown above — this only decides "
            "which one activates first.<br><br>"
            "<b>(default)</b>: fixed at the origin, no bounds, no target."
        )
        self._combo_camera.currentIndexChanged.connect(self._on_camera_picked)
        start_row.addWidget(self._combo_camera, 1)
        camera_card.body_layout.addLayout(start_row)

        self._lbl_users = QLabel("")
        self._lbl_users.setFont(QFont(T.UI, T.XS))
        self._lbl_users.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._lbl_users.setWordWrap(True)
        camera_card.body_layout.addWidget(self._lbl_users)
        layout.addWidget(camera_card)

        # ── Mode ──────────────────────────────────────────────────
        mode_card = CollapsibleCard("Mode")
        self._mode_combo = QComboBox()
        self._mode_combo.setFont(QFont(T.UI, T.MD))
        self._mode_combo.setStyleSheet(QSS.combobox)
        for _, label in _MODES:
            self._mode_combo.addItem(label)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_card.body_layout.addWidget(self._mode_combo)

        mode_info = QLabel(
            "Fixed: stays where activation put it.\n"
            "Follow: keeps the chosen Actor inside a deadzone.\n"
            "Script: the engine computes nothing, the script decides."
        )
        mode_info.setFont(QFont(T.UI, T.XS))
        mode_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        mode_info.setWordWrap(True)
        mode_card.body_layout.addWidget(mode_info)
        layout.addWidget(mode_card)

        # ── Transform : position (canvas ↔ inspecteur) + frame écran ──
        transform_card = CollapsibleCard("Transform")
        pos_row = QHBoxLayout()
        pos_row.setSpacing(10)
        for label, attr in (("Position X:", "_pos_x"), ("Position Y:", "_pos_y")):
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont(T.UI, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
            col.addWidget(lbl)
            spin = QSpinBox()
            spin.setFont(QFont(T.MONO, T.MD))
            spin.setStyleSheet(QSS.spinbox)
            spin.setRange(0, 32767)   # même plage que les bornes du monde plus bas
            spin.setSingleStep(8)
            setattr(self, attr, spin)
            col.addWidget(spin)
            pos_row.addLayout(col)
        pos_row.addStretch()
        transform_card.body_layout.addLayout(pos_row)

        pos_info = QLabel(
            "Reflects dragging the yellow rectangle in the canvas — editing here "
            "moves it too. Applied every time the camera is activated (scene "
            "start, or camera.switch)."
        )
        pos_info.setFont(QFont(T.UI, T.XS))
        pos_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        pos_info.setWordWrap(True)
        transform_card.body_layout.addWidget(pos_info)

        frame_row = QHBoxLayout()
        frame_row.setSpacing(10)
        for label, attr, maxv in (("Frame W:", "_frame_w", 240), ("Frame H:", "_frame_h", 160)):
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont(T.UI, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
            col.addWidget(lbl)
            spin = QSpinBox()
            spin.setFont(QFont(T.MONO, T.MD))
            spin.setStyleSheet(QSS.spinbox)
            spin.setRange(1, maxv)
            setattr(self, attr, spin)
            col.addWidget(spin)
            frame_row.addLayout(col)
        frame_row.addStretch()
        transform_card.body_layout.addLayout(frame_row)

        self._lbl_win_budget = QLabel("")
        self._lbl_win_budget.setFont(QFont(T.UI, T.XS))
        self._lbl_win_budget.setWordWrap(True)
        transform_card.body_layout.addWidget(self._lbl_win_budget)

        frame_info = QLabel(
            "Screen size the camera renders into (max 240×160). Smaller than "
            "full screen → the camera claims one of the scene's two windows "
            "while active (which one is decided at build — cf. Windows panel, "
            "Scene inspector)."
        )
        frame_info.setFont(QFont(T.UI, T.XS))
        frame_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        frame_info.setWordWrap(True)
        transform_card.body_layout.addWidget(frame_info)
        layout.addWidget(transform_card)

        # ── Suivi (visible en mode follow) ────────────────────────
        self._follow_group = CollapsibleCard("Follow an Actor")
        fg = self._follow_group.body_layout

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
        bounds_card = CollapsibleCard("World bounds (0 = unlimited)")
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
        bounds_card.body_layout.addLayout(bounds_row)
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
        bounds_card.body_layout.addLayout(origin_row)
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
        bounds_card.body_layout.addWidget(self._btn_recalc)

        bounds_info = QLabel(
            "Applied when the camera is activated. A script can redefine them "
            "afterwards with camera.bound = rect(x, y, w, h)."
        )
        bounds_info.setFont(QFont(T.UI, T.XS))
        bounds_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        bounds_info.setWordWrap(True)
        bounds_card.body_layout.addWidget(bounds_info)
        layout.addWidget(bounds_card)

        # ── Script de caméra ──────────────────────────────────────
        script_card = CollapsibleCard("Camera script")
        self._script_slot = ScriptSlot(
            add_label    = "Add a camera script",
            accent_color = COLOR_SCRIPT,
            hint         = "on_start · on_update",
        )
        self._script_slot.set_callbacks(
            on_add   = self._script_new,
            on_open  = self._script_open,
            on_clear = self._script_clear,
        )
        script_card.body_layout.addWidget(self._script_slot)

        script_info = QLabel(
            "Runs AFTER the declarative settings above and BEFORE world bounds "
            "are applied — so it adjusts the framing instead of fighting it."
        )
        script_info.setFont(QFont(T.UI, T.XS))
        script_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        script_info.setWordWrap(True)
        script_card.body_layout.addWidget(script_info)
        layout.addWidget(script_card)

        layout.addStretch()

        # Tout ce qui n'a de sens qu'avec une caméra RÉELLE.
        self._editors = (
            self._mode_combo, self._follow_group, self._margin_x, self._margin_y,
            self._bounds_w, self._bounds_h, self._bounds_x, self._bounds_y,
            self._btn_recalc, self._script_slot,
            self._pos_x, self._pos_y, self._frame_w, self._frame_h,
        )
        self._pos_x.valueChanged.connect(self._on_transform_changed)
        self._pos_y.valueChanged.connect(self._on_transform_changed)
        self._frame_w.valueChanged.connect(self._on_transform_changed)
        self._frame_h.valueChanged.connect(self._on_transform_changed)

    def set_script_open_fn(self, fn):
        self._script_open_fn = fn

    # ── Chargement ────────────────────────────────────────────────

    def load(self, scene: Scene, camera: Optional[Camera], project: Project):
        self._scene = scene
        self._camera = camera
        self._project = project
        self._refresh()

    def _refresh(self):
        self._blocking = True
        try:
            cam = self._camera
            scene = self._scene

            self._combo_camera.clear()
            self._combo_camera.addItem(_DEFAULT_CAMERA, "")
            for c in (scene.cameras if scene else []):
                self._combo_camera.addItem(c.name, c.name)
            idx = self._combo_camera.findData(getattr(scene, "camera", "") or "")
            self._combo_camera.setCurrentIndex(max(0, idx))

            for w in self._editors:
                w.setEnabled(cam is not None)

            self._lbl_users.setText(
                "" if cam is not None else
                "No camera yet — any change below creates one.")

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
                # Cible introuvable dans cette scène (acteur supprimé/renommé
                # sans passer par ici) : la garder visible plutôt que de la
                # réécrire en silence — le validateur le signale déjà.
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
            self._pos_x.setValue(cam.x if cam else 0)
            self._pos_y.setValue(cam.y if cam else 0)
            self._frame_w.setValue(cam.frame_w if cam else 240)
            self._frame_h.setValue(cam.frame_h if cam else 160)
            self._refresh_window_budget()

            script = (cam.script if cam else "") or ""
            if script:
                self._script_slot.set_script(script.rsplit("/", 1)[-1])
            else:
                self._script_slot.clear_script()
        finally:
            self._blocking = False

    def _refresh_window_budget(self):
        """Même chiffre que la carte Windows du Scene inspector — une seule
        fonction (`window_alloc.scene_window_budget`), pour que l'auteur voie
        le coût AVANT de réduire le cadre, pas seulement après un warning."""
        if not self._scene:
            self._lbl_win_budget.setText("")
            return
        from codegen.window_alloc import scene_window_budget
        used, total = scene_window_budget(self._scene)
        over = used > total
        self._lbl_win_budget.setStyleSheet(
            f"color:{C.ACCENT_RED if over else C.TEXT_MUTED};")
        msg = f"{used} / {total} windows used by this scene"
        if over:
            msg += " — over budget, build will fail"
        self._lbl_win_budget.setText(msg)

    def update_position(self, camera, x: int, y: int):
        """Appelé en direct par le canvas pendant un drag (cf. SceneEditor,
        même rôle que ActorInspector.update_position) : pas de `_refresh()`
        complet, juste les deux spinboxes concernées — et seulement si la
        caméra déplacée est bien celle affichée ici."""
        if self._blocking or camera is not self._camera:
            return
        self._blocking = True
        self._pos_x.setValue(x)
        self._pos_y.setValue(y)
        self._blocking = False

    # ── Mutations ─────────────────────────────────────────────────

    def _mutable(self) -> Optional[Camera]:
        """La caméra à éditer, matérialisée si la scène n'en avait encore
        aucune (état implicite, `self._camera is None`). Une fois réelle, la
        référence tenue par l'inspecteur devient cette caméra-là."""
        if not self._scene or not self._project:
            return None
        if self._camera is None:
            self._camera = self._project.ensure_scene_camera(self._scene)
        return self._camera

    def _commit(self, refresh: bool = True):
        """Un seul save : la caméra vit dans le JSON de la scène (plus de
        fichier séparé). Ne pas s'en remettre au signal `changed` pour ça :
        il sert à rafraîchir les vues, personne ne s'y est abonné pour
        écrire sur le disque."""
        if self._project and self._scene:
            self._project.save_scene(self._scene)
        self.changed.emit()
        if refresh:
            self._refresh()

    def _on_camera_picked(self, idx: int):
        """Choix de la caméra de DÉMARRAGE de la scène — indépendant de la
        caméra affichée/éditée par le reste de ce panneau."""
        if self._blocking or not self._scene:
            return
        self._scene.camera = self._combo_camera.itemData(idx) or ""
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

    def _on_transform_changed(self):
        """Position et frame : édition faite ICI (pas par drag canvas), donc
        `camera_moved` est émis en plus de `_commit()` — c'est ce qui fait
        suivre le rectangle du canvas (cf. SceneEditor.move_camera_item)."""
        if self._blocking:
            return
        cam = self._mutable()
        if cam is None:
            return
        cam.x = self._pos_x.value()
        cam.y = self._pos_y.value()
        cam.frame_w = self._frame_w.value()
        cam.frame_h = self._frame_h.value()
        self._commit(refresh=False)
        self.camera_moved.emit(cam)

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
        popup = ScriptPickerPopup(scripts, COLOR_SCRIPT, parent=self)
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
