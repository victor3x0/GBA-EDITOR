"""ui/script_editor/sidebar_panel.py — panneau gauche : sections EVENTS / API / RÉFÉRENCES."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QToolButton
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from scripting.api import KNOWN_EVENTS, KNOWN_SCENE_EVENTS, EVENT_REGISTRY as _EVENT_META
from ui.common.theme import C, T
from .colors import _BG, _BG_HOVER, _TEXT_DIM, _TEXT_NORM, _C_API, _C_REF, _C_EVENT, _C_BEHAVIOR
from .sidebar_widgets import (
    _Section, _EntryButton,
    _BTN_BASE, _BTN_API, _BTN_REF, _BTN_BEHAVIOR, _BTN_EVENT_DEFINED, _event_tooltip,
)

class SidebarPanel(QWidget):
    """
    Panneau gauche du script editor avec 3 sections collapsibles :
    EVENTS / API / RÉFÉRENCES. Émet snippet_requested(str) à chaque clic.
    """

    snippet_requested = pyqtSignal(str)     # snippet à insérer dans l'éditeur
    stub_requested    = pyqtSignal(str)     # event name → insérer stub ou jumper

    def __init__(self, parent=None):
        super().__init__(parent)
        # Bornes larges = colonne « étirable » dans le QSplitter du Script Editor
        # (même esprit que les finders du Sprite Editor : min/max, pas de fixe).
        self.setMinimumWidth(190)
        self.setMaximumWidth(400)
        self.setStyleSheet(f"background:{_BG};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background:{_BG};border:none;")

        container = QWidget()
        container.setStyleSheet(f"background:{_BG};")
        self._cl = QVBoxLayout(container)
        self._cl.setContentsMargins(0, 0, 0, 0)
        self._cl.setSpacing(0)

        # ── Section EVENTS ─────────────────────────────────────────
        self._sec_events = _Section("EVENTS", _C_EVENT)
        self._event_btns: dict[str, _EntryButton] = {}
        for ev in KNOWN_EVENTS:
            meta  = _EVENT_META.get(ev, {})
            btn   = _EntryButton(f"  {ev}", _BTN_BASE, _event_tooltip(ev),
                                 icon_key=meta.get("icon_key"), icon_color=_TEXT_DIM)
            btn.clicked.connect(lambda _, e=ev: self.stub_requested.emit(e))
            self._sec_events.add_widget(btn)
            self._event_btns[ev] = btn
        self._cl.addWidget(self._sec_events)

        # ── Section API ─────────────────────────────────────────────
        self._sec_api = _Section("API", _C_API, expanded=False)
        self._build_api_section()
        self._cl.addWidget(self._sec_api)

        # ── Section RÉFÉRENCES ──────────────────────────────────────
        self._sec_refs = _Section("RÉFÉRENCES", _C_REF, expanded=False)
        self._cl.addWidget(self._sec_refs)

        self._cl.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ── API section (statique, depuis api_reference.json) ────────────

    def _build_api_section(self):
        from scripting.api_reference import get_categories, make_tooltip
        for cat in get_categories():
            sub = self._sec_api.sub_section(cat["name"])
            for entry in cat.get("entries", []):
                display = entry['label'].removeprefix("self:")
                label   = f"  {display}"
                tooltip = make_tooltip(entry)
                snippet = entry.get("snippet", entry.get("label", ""))
                btn = _EntryButton(label, _BTN_API, tooltip)
                btn.clicked.connect(lambda _, s=snippet: self.snippet_requested.emit(s))
                sub.add_widget(btn)

    # ── Références (dynamique, depuis le projet) ─────────────────────

    def set_project(self, project):
        """Recharge les sections dynamiques (RÉFÉRENCES) depuis le projet."""
        self._sec_refs.clear_body()
        if not project:
            return

        def _ref_btn(label: str, snippet: str, tip: str) -> _EntryButton:
            btn = _EntryButton(f"  {label}", _BTN_REF, tip)
            btn.clicked.connect(lambda _, s=snippet: self.snippet_requested.emit(s))
            return btn

        def _tip(sig: str, desc: str) -> str:
            return (
                f"<b style='font-family:Consolas,monospace;color:{_C_REF}'>{sig}</b>"
                f"<p style='color:{_TEXT_NORM};margin:4px 0'>{desc}</p>"
            )

        # Scènes
        scenes = list(project.scenes)
        if scenes:
            sub = self._sec_refs.sub_section("Scènes")
            for s in scenes:
                sn = f"scene_goto(\"{s.name}\")"
                sub.add_widget(_ref_btn(s.name, sn, _tip(sn, "Charge et démarre cette scène.")))

        # Actors
        actors = list(project.active_scene.actors) if project.active_scene else []
        if actors:
            sub = self._sec_refs.sub_section("Actors")
            for a in actors:
                sn = f"get_actor(\"{a.name}\")"
                sub.add_widget(_ref_btn(a.name, sn,
                    _tip(sn, "Référence à cet actor dans la scène active.")))

        # Prefabs
        prefabs = list(project.prefabs)
        if prefabs:
            sub = self._sec_refs.sub_section("Prefabs")
            for p in prefabs:
                sn = f"instantiate(\"{p.name}\", x, y)"
                sub.add_widget(_ref_btn(p.name, sn,
                    _tip(sn, f"Instancie le prefab <i>{p.name}</i> à (x, y).")))

        # Sprites
        sprites = list(project.sprites)
        if sprites:
            sub = self._sec_refs.sub_section("Sprites")
            for sp in sprites:
                sn = f"self:play_anim(\"{sp.name}\")"
                sub.add_widget(_ref_btn(sp.name, sn,
                    _tip(sn, f"Joue l'animation du sprite <i>{sp.name}</i>.")))

        # Backgrounds
        bgs = list(project.backgrounds)
        if bgs:
            sub = self._sec_refs.sub_section("Backgrounds")
            for bg in bgs:
                sub.add_widget(_ref_btn(bg.name, f"-- BG: {bg.name}",
                    _tip(bg.name, f"Background <i>{bg.name}</i> — référence éditoriale.")))

        # SFX
        sfx_list = list(project.sfx) if hasattr(project, "sfx") else []
        if sfx_list:
            sub = self._sec_refs.sub_section("SFX")
            for sfx in sfx_list:
                sn = f"sfx.play(\"{sfx.name}\")"
                sub.add_widget(_ref_btn(sfx.name, sn,
                    _tip(sn, f"Joue l'effet sonore <i>{sfx.name}</i>.")))

        # Scripts behaviors
        behaviors_dir = project.scripts_behaviors_dir
        scripts = sorted(behaviors_dir.glob("*.lua")) if behaviors_dir.exists() else []
        if scripts:
            sub = self._sec_refs.sub_section("Scripts")
            for sp in scripts:
                rel = f"behaviors/{sp.stem}"
                sn  = f"local {sp.stem} = require(\"{rel}\")"
                sub.add_widget(_ref_btn(sp.name, sn,
                    _tip(f"require(\"{rel}\")", f"Importe le module behavior <i>{sp.stem}</i>.")))

    # ── Mise à jour état events ───────────────────────────────────────

    def update_defined_events(self, defined: set[str]):
        for ev, btn in self._event_btns.items():
            btn.setText(f"  {ev}")
            if ev in defined:
                btn.setStyleSheet(_BTN_EVENT_DEFINED)
                btn.set_icon_color(_C_EVENT)
            else:
                btn.setStyleSheet(_BTN_BASE)
                btn.set_icon_color(_TEXT_DIM)

    # ── Adaptation contextuelle ───────────────────────────────────────

    def set_context(self, context: str):
        """Adapte les sections selon le type de script (actor/scene/behavior/unknown)."""
        self._event_btns.clear()
        self._sec_events.clear_body()

        if context == "behavior":
            # Remplace EVENTS par MODULE
            self._sec_events._title = "MODULE"
            self._sec_events._color = _C_BEHAVIOR
            self._sec_events._toggle.setStyleSheet(
                f"QToolButton{{color:{_C_BEHAVIOR};border:none;background:transparent;"
                f"font-family:{T.MONO};font-size:{T.SM}pt;font-weight:bold;"
                f"text-align:left;padding:0 4px 0 6px;}}"
                f"QToolButton:hover{{background:{_BG_HOVER};}}"
            )
            self._sec_events._toggle.setText(f"▾  MODULE")

            hint = QLabel("  Pas de handlers — appelé via require()")
            hint.setFont(QFont(T.MONO, T.XS))
            hint.setStyleSheet(f"color:{_TEXT_DIM};background:{_BG};padding:4px 8px;")
            hint.setWordWrap(True)
            self._sec_events.add_widget(hint)

            stub_text = "function M.nom(actor, ...)"
            stub_btn = _EntryButton(f"  {stub_text}", _BTN_BEHAVIOR,
                "<b style='font-family:Consolas,monospace'>function M.nom(actor, ...)</b>"
                f"<p style='color:{_TEXT_NORM}'>Stub de fonction exportée par ce module behavior.</p>",
                icon_key="behavior_stub", icon_color=_C_BEHAVIOR)
            stub_btn.clicked.connect(
                lambda: self.snippet_requested.emit("function M.nom(actor, ...)\n    \nend\n"))
            self._sec_events.add_widget(stub_btn)

            self._sec_refs.setVisible(False)
        else:
            # Restore EVENTS header style
            self._sec_events._title = "EVENTS"
            self._sec_events._color = _C_EVENT
            self._sec_events._toggle.setStyleSheet(
                f"QToolButton{{color:{_C_EVENT};border:none;background:transparent;"
                f"font-family:{T.MONO};font-size:{T.SM}pt;font-weight:bold;"
                f"text-align:left;padding:0 4px 0 6px;}}"
                f"QToolButton:hover{{background:{_BG_HOVER};}}"
            )
            self._sec_events._toggle.setText(f"▾  EVENTS")
            self._sec_refs.setVisible(True)

            events_to_show = KNOWN_SCENE_EVENTS if context == "scene" else KNOWN_EVENTS
            for ev in events_to_show:
                meta  = _EVENT_META.get(ev, {})
                btn   = _EntryButton(f"  {ev}", _BTN_BASE, _event_tooltip(ev),
                                     icon_key=meta.get("icon_key"), icon_color=_TEXT_DIM)
                btn.clicked.connect(lambda _, e=ev: self.stub_requested.emit(e))
                self._sec_events.add_widget(btn)
                self._event_btns[ev] = btn
