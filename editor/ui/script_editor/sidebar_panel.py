"""ui/script_editor/sidebar_panel.py — panneau gauche : sections EVENTS / API / RÉFÉRENCES."""
from html import escape

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QToolButton
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from scripting.api import (KNOWN_EVENTS, KNOWN_SCENE_EVENTS, KNOWN_EVENTS_BY_KIND,
                           EVENT_REGISTRY as _EVENT_META)
from scripting import api_snippets
from core.models.text import SEP
from core.text_markup import display_text
from ui.common.theme import C, T
from .colors import _BG, _TEXT_DIM, _TEXT_NORM, _C_API, _C_REF, _C_EVENT, _C_BEHAVIOR
from .sidebar_widgets import (
    _Section, _EntryButton, _group_label,
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
        self._sec_events = _Section("Events", _C_EVENT)
        self._event_btns: dict[str, _EntryButton] = {}
        for ev in KNOWN_EVENTS:
            meta  = _EVENT_META.get(ev, {})
            btn   = _EntryButton(f"  {ev}", _BTN_BASE, _event_tooltip(ev),
                                 icon_key=meta.get("icon_key"), icon_color=_TEXT_DIM)
            btn.clicked.connect(lambda _, e=ev: self.stub_requested.emit(e))
            self._sec_events.add_widget(btn)
            self._event_btns[ev] = btn
        self._cl.addWidget(self._sec_events)

        # ── Sections API, éclatées en 3 grosses parties ───────────────
        # Gameplay / Scripting / Hardware — la même API qu'avant sous un seul
        # « API », désormais rangée par NATURE plutôt que par ordre du JSON
        # seul. Une section vide (Hardware, tant qu'aucune catégorie n'y est
        # rangée) ne se crée simplement pas — cf. api_reference.get_categories_by_group().
        self._api_sections: list[_Section] = []
        self._build_api_sections()
        for sec in self._api_sections:
            self._cl.addWidget(sec)

        # ── Section RÉFÉRENCES ──────────────────────────────────────
        self._sec_refs = _Section("References", _C_REF, expanded=False)
        self._cl.addWidget(self._sec_refs)

        self._cl.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ── Sections API (statiques, depuis api_reference.json) ───────────

    def _build_api_sections(self):
        from scripting.api_reference import get_categories_by_group, make_tooltip
        for _group, label, cats in get_categories_by_group():
            sec = _Section(label, _C_API, expanded=False)
            for cat in cats:
                sub = sec.sub_section(cat["name"])
                for entry in cat.get("entries", []):
                    display = entry['label'].removeprefix("self:")
                    btn_label = f"  {display}"
                    tooltip   = make_tooltip(entry)
                    snippet   = entry.get("snippet", entry.get("label", ""))
                    btn = _EntryButton(btn_label, _BTN_API, tooltip)
                    btn.clicked.connect(lambda _, s=snippet: self.snippet_requested.emit(s))
                    sub.add_widget(btn)
            self._api_sections.append(sec)

    # ── Références (dynamique, depuis le projet) ─────────────────────

    def set_project(self, project):
        """Recharge les sections dynamiques (RÉFÉRENCES) depuis le projet.

        Les snippets viennent d'`api_snippets.call()`, jamais d'une chaîne
        écrite ici : c'est ce qui empêche un bouton de survivre à la fonction
        qu'il appelle (`scene_goto`, `instantiate` — deux noms proposés ici
        pendant des mois alors qu'aucun n'existait dans le catalogue)."""
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

        def _api_tip(api_name: str, snippet: str, extra: str = "") -> str:
            """Tooltip d'un bouton d'asset : l'appel tel qu'il sera inséré, la
            description de la fonction telle qu'elle vit dans `api.py`, puis ce
            que l'éditeur seul sait de l'asset."""
            tip = _tip(snippet, api_snippets.description(api_name))
            if extra:
                tip += f"<p style='color:{_TEXT_DIM};margin:2px 0'>{extra}</p>"
            return tip

        def _add(sub, label: str, api_name: str, extra: str = "", **domains):
            sn = api_snippets.call(api_name, **domains)
            sub.add_widget(_ref_btn(label, sn, _api_tip(api_name, sn, extra)))

        # Scènes
        scenes = list(project.scenes)
        if scenes:
            sub = self._sec_refs.sub_section("Scenes")
            for s in scenes:
                _add(sub, s.name, "scene.switch", scene=s.name)

        # Actors
        actors = list(project.active_scene.actors) if project.active_scene else []
        if actors:
            sub = self._sec_refs.sub_section("Actors")
            for a in actors:
                _add(sub, a.name, "get_actor", "Active scene.", actor=a.name)

        # Prefabs
        prefabs = list(project.prefabs)
        if prefabs:
            sub = self._sec_refs.sub_section("Prefabs")
            for p in prefabs:
                _add(sub, p.name, "actor.spawn", prefab=p.name)

        # Sprites
        sprites = list(project.sprites)
        if sprites:
            sub = self._sec_refs.sub_section("Sprites")
            for sp in sprites:
                _add(sub, sp.name, "self:play_anim", anim=sp.name)

        # Backgrounds — aucune API ne prend un nom de fond en argument (un fond
        # se pose dans la scène, pas dans un script) : la référence reste un
        # commentaire, et le dire évite de chercher la fonction manquante.
        bgs = list(project.backgrounds)
        if bgs:
            sub = self._sec_refs.sub_section("Backgrounds")
            for bg in bgs:
                sub.add_widget(_ref_btn(bg.name, f"-- BG: {bg.name}",
                    _tip(bg.name, "Editorial reference — a background is placed in "
                                  "the scene, not from a script.")))

        # ── Textes ─────────────────────────────────────────────────
        # Rangés par premier niveau de chemin : c'est l'arbre de l'écran Texte,
        # aplati à un niveau. Aller plus profond ici ferait des sous-sections de
        # deux entrées dans une colonne de 200 px — la recherche fine reste le
        # métier de l'écran Texte, la sidebar sert à INSÉRER.
        texts = list(getattr(project, "texts", []))
        if texts:
            sub = self._sec_refs.sub_section("Texts")
            _UNFILED = "(unfiled)"
            values = project.text_values()
            groups: dict[str, list] = {}
            for t in texts:
                groups.setdefault(t.path[0] if t.path else _UNFILED, []).append(t)
            for folder in sorted(groups):
                if len(groups) > 1:
                    sub.add_widget(_group_label(folder))
                for t in groups[folder]:
                    where = escape(SEP.join(t.path)) if t.path else _UNFILED
                    excerpt = escape(
                        display_text(t.content, values).replace("\n", " ⏎ ")[:60])
                    _add(sub, t.key, "text.draw",
                         f"<i>{where}</i><br>« {excerpt} »", text=t.key)

        # ── Zones de texte ─────────────────────────────────────────
        # Celles des nœuds `Interface` de la scène active (v0.25) — comme les
        # Actors, et pour la même raison : une zone d'une autre scène a des
        # coordonnées réelles mais aucune surface réservée là où on écrirait.
        slots = (project.scene_ui_slots(project.active_scene)
                 if project.active_scene and hasattr(project, "scene_ui_slots")
                 else [])
        if slots:
            sub = self._sec_refs.sub_section("Text zones")
            for layout, r in slots:
                # Une zone propose son texte d'aperçu ; un texte AUTHORÉ porte
                # directement sa clé, et reste adressable (cf. KIND_SLOTS) pour
                # être remplacé en cours de jeu.
                key = getattr(r, "preview_text", "") or getattr(r, "text_key", "") or ""
                doms = {"region": r.name}
                if key:
                    doms["text"] = key
                _add(sub, r.name, "text.draw_in",
                     f"Interface <i>{layout.name}</i>"
                     + (f" — preview “{escape(key)}”" if key else ""), **doms)

        # ── Polices ────────────────────────────────────────────────
        fonts = list(getattr(project, "fonts", []))
        if fonts:
            sub = self._sec_refs.sub_section("Fonts")
            for f in fonts:
                _add(sub, f.name, "text.set_font", font=f.name)

        # SFX
        sfx_list = list(project.sfx) if hasattr(project, "sfx") else []
        if sfx_list:
            sub = self._sec_refs.sub_section("SFX")
            for sfx in sfx_list:
                _add(sub, sfx.name, "sfx.play", sfx=sfx.name)

        # Scripts behaviors
        behaviors_dir = project.scripts_behaviors_dir
        scripts = sorted(behaviors_dir.glob("*.lua")) if behaviors_dir.exists() else []
        if scripts:
            sub = self._sec_refs.sub_section("Scripts")
            for sp in scripts:
                rel = f"behaviors/{sp.stem}"
                sn  = f"local {sp.stem} = require(\"{rel}\")"
                sub.add_widget(_ref_btn(sp.name, sn,
                    _tip(f"require(\"{rel}\")", f"Imports the behavior module <i>{sp.stem}</i>.")))

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
            self._sec_events.set_title_and_color("MODULE", _C_BEHAVIOR)

            hint = QLabel("  No handlers — called via require()")
            hint.setFont(QFont(T.UI, T.XS))
            hint.setStyleSheet(f"color:{_TEXT_DIM};background:{_BG};padding:4px 8px;")
            hint.setWordWrap(True)
            self._sec_events.add_widget(hint)

            stub_text = "function M.name(actor, ...)"
            stub_btn = _EntryButton(f"  {stub_text}", _BTN_BEHAVIOR,
                "<b style='font-family:Consolas,monospace'>function M.name(actor, ...)</b>"
                f"<p style='color:{_TEXT_NORM}'>Function stub exported by this behavior module.</p>",
                icon_key="behavior_stub", icon_color=_C_BEHAVIOR)
            stub_btn.clicked.connect(
                lambda: self.snippet_requested.emit("function M.name(actor, ...)\n    \nend\n"))
            self._sec_events.add_widget(stub_btn)

            self._sec_refs.setVisible(False)
        else:
            # Restore EVENTS header style
            self._sec_events.set_title_and_color("EVENTS", _C_EVENT)
            self._sec_refs.setVisible(True)

            # Un script sans `self` (scène ou caméra) a ses propres points
            # d'entrée — une caméra n'a pas d'on_late_update.
            events_to_show = KNOWN_EVENTS_BY_KIND.get(context, KNOWN_EVENTS)
            for ev in events_to_show:
                meta  = _EVENT_META.get(ev, {})
                btn   = _EntryButton(f"  {ev}", _BTN_BASE, _event_tooltip(ev),
                                     icon_key=meta.get("icon_key"), icon_color=_TEXT_DIM)
                btn.clicked.connect(lambda _, e=ev: self.stub_requested.emit(e))
                self._sec_events.add_widget(btn)
                self._event_btns[ev] = btn
