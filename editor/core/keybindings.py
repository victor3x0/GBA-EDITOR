"""
core/keybindings.py — registre central des raccourcis REMAPPABLES.

Avant ce fichier, un raccourci était une chaîne codée en dur au point où il
s'active — 22 sites, répartis sur 7 fichiers, sans nom ni mémoire commune.
Changer une touche voulait dire éditer le code ; l'écran Réglages (catégorie
« Shortcuts ») ne peut lister et remapper que ce qui a un NOM et une valeur
par défaut ici — le reste continue de s'activer directement.

Chaque site d'origine résout sa touche via `resolve(id)` au lieu d'une chaîne
en dur ; ce module ne branche rien lui-même, il ne fait que dire quelle touche
va avec quel id.

Trois familles VOLONTAIREMENT absentes de ce registre, remappables nulle part :

  - **Undo/Redo** (window.py) — `QKeySequence.StandardKey`, la convention du
    système d'exploitation, pas un choix de ce projet ; Redo est en plus
    doublement lié (Ctrl+Y ET la touche standard) pour couvrir les deux
    habitudes à la fois. Remapper l'un des deux casserait l'autre en silence.
    Listés quand même dans l'écran Réglages via `DISPLAY_ONLY` ci-dessous —
    pour la découvrabilité, pas pour le remappage : lecture seule, aucune
    entrée dans `BINDINGS`/`_BY_ID`.
  - **Renommer (F2)** (scene_tree_panel.py, asset_finder.py) — le `F2` qui
    apparaît dans ces menus est un LIBELLÉ, pas un branchement : Qt déclenche
    déjà l'édition en place via son trigger natif `EditKeyPressed` sur
    QTreeWidget/QListWidget. Le remapper ici changerait le texte affiché sans
    changer la touche qui agit réellement — pire que ne rien afficher.
  - **Nudge de sélection** (scene_canvas.py, flèches ± Shift) — les 8
    variantes sont POSITIONNELLES (haut/bas/gauche/droite), pas des actions
    nommées ; leur binder une à une n'offrirait rien qu'un vrai remappage de
    clavier de jeu n'offre pas déjà, pour 8 lignes de registre.
  - **Backspace en second alias de Suppr** (scene_canvas.py) — un simple
    confort clavier, jamais montré nulle part : remapper « Suppr » ne doit
    pas le priver de son alias.

Persistance : un fichier JSON à côté de `toolchain.json` (même dossier de
config, cf. `core/toolchain.config_dir`), qui ne porte QUE les
SUBSTITUTIONS à la valeur par défaut — un raccourci jamais changé n'y figure
pas, donc une valeur par défaut modifiée dans une prochaine version profite
à qui n'a rien personnalisé.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut, QAction

from core.toolchain import config_dir

CONFIG_FILE = config_dir() / "keybindings.json"


@dataclass(frozen=True)
class Binding:
    id: str            # stable — c'est la clé de persistance, jamais affichée
    context_id: str     # regroupement stable, résolu en libellé par l'UI
    default: str         # QKeySequence, ex. "Ctrl+D", "Shift+X", "F"


# ── Le registre — un binding par ligne, dans l'ordre d'affichage ──────────
BINDINGS: list[Binding] = [
    # Global (window.py — menus File / Game)
    Binding("file.new",   "global", "Ctrl+N"),
    Binding("file.open",  "global", "Ctrl+O"),
    Binding("file.save",  "global", "Ctrl+S"),
    Binding("file.quit",  "global", "Ctrl+Q"),
    Binding("game.build", "global", "F5"),

    # Scene canvas (ui/scene_manager/scene_canvas.py)
    Binding("canvas.tool_select",    "scene_canvas", "S"),
    Binding("canvas.tool_add",       "scene_canvas", "A"),
    Binding("canvas.tool_erase",     "scene_canvas", "E"),
    Binding("canvas.tool_collision", "scene_canvas", "C"),
    Binding("canvas.tool_inpaint",   "scene_canvas", "B"),
    Binding("canvas.tool_ui",        "scene_canvas", "T"),
    Binding("canvas.fit",            "scene_canvas", "F"),
    Binding("canvas.cancel",         "scene_canvas", "Escape"),
    Binding("canvas.delete",         "scene_canvas", "Del"),
    Binding("canvas.duplicate",      "scene_canvas", "Ctrl+D"),
    Binding("canvas.copy",           "scene_canvas", "Ctrl+C"),
    Binding("canvas.paste",          "scene_canvas", "Ctrl+V"),

    # Sprite editor (ui/sprite_editor/*)
    Binding("sprite.flip_h",         "sprite_editor", "Shift+X"),
    Binding("sprite.flip_v",         "sprite_editor", "Shift+Y"),
    Binding("sprite.duplicate_frame","sprite_editor", "Ctrl+D"),
    Binding("sprite.delete_frame",   "sprite_editor", "Del"),

    # Sound mixer (ui/sound_mixer/sound_panel.py)
    Binding("sound.play_pause", "sound_mixer", "Space"),
]

_BY_ID: dict[str, Binding] = {b.id: b for b in BINDINGS}


# ── Affichage seul — pas dans BINDINGS, jamais remappable ──────────────────
# Insérées, dans l'ordre, juste après le binding_id `insert_after` de leur
# contexte — ShortcutsPanel s'en sert pour les placer au bon endroit de la
# table sans dupliquer l'ordre d'affichage ici.
DISPLAY_ONLY: list[tuple[str, str, str]] = [
    # (context_id, display_id, touche affichée)
    ("global", "undo", "Ctrl+Z"),
    ("global", "redo", "Ctrl+Y"),
]
DISPLAY_ONLY_INSERT_AFTER = "file.save"   # binding_id après lequel les insérer


class Keybindings(QObject):
    """Charge/sauvegarde les substitutions, résout un id vers sa touche
    effective. `QObject` pour UNE raison : `changed` permet à un raccourci
    déjà construit (QShortcut/QAction) de se remettre à jour SANS relancer
    l'éditeur quand l'écran Réglages le change — cf. `bind()` plus bas, seul
    consommateur du signal."""

    changed = pyqtSignal(str)   # binding_id qui vient de changer

    def __init__(self):
        super().__init__()
        self._overrides: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save(self):
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self._overrides, indent=2), encoding="utf-8")

    def resolve(self, binding_id: str) -> str:
        """La touche EFFECTIVE d'un id — la substitution si elle existe,
        sinon la valeur par défaut du registre. Un id inconnu du registre
        (faute de frappe au site d'appel) rend une chaîne vide plutôt que de
        lever : un raccourci manquant se voit à l'usage, il ne doit pas
        empêcher l'écran de s'ouvrir."""
        b = _BY_ID.get(binding_id)
        if b is None:
            return ""
        return self._overrides.get(binding_id, b.default)

    def set(self, binding_id: str, sequence: str):
        b = _BY_ID.get(binding_id)
        if b is None:
            return
        sequence = sequence.strip()
        if sequence == b.default:
            self._overrides.pop(binding_id, None)   # revenu au défaut = plus une substitution
        else:
            self._overrides[binding_id] = sequence
        self.save()
        self.changed.emit(binding_id)

    def reset(self, binding_id: str):
        if binding_id in self._overrides:
            del self._overrides[binding_id]
            self.save()
            self.changed.emit(binding_id)

    def reset_all(self):
        ids = list(self._overrides)
        self._overrides.clear()
        self.save()
        for binding_id in ids:
            self.changed.emit(binding_id)

    def is_customized(self, binding_id: str) -> bool:
        return binding_id in self._overrides


# ── Singleton — même règle que get_history()/get_bus()/get_dispatcher() :
# un registre, partagé par tous les sites qui en ont besoin sans avoir à se
# le passer de widget en widget.
_instance: Keybindings | None = None


def get_keybindings() -> Keybindings:
    global _instance
    if _instance is None:
        _instance = Keybindings()
    return _instance


def bind(binding_id: str, target: QShortcut | QAction) -> None:
    """Pose la touche EFFECTIVE de `binding_id` sur `target`, et le tient à
    jour si l'écran Réglages la change EN COURS DE SESSION — un seul appel
    remplace à la fois la construction d'une `QKeySequence` en dur et
    l'abonnement à son changement. Remplace, à chaque site d'origine :

        a = QAction("New project", self); a.setShortcut("Ctrl+N")
    par
        a = QAction("New project", self); bind("file.new", a)

    Un id absent du registre (faute de frappe) laisse `target` sans touche —
    silencieux à dessein, cf. `Keybindings.resolve`."""
    kb = get_keybindings()

    def _apply():
        seq = QKeySequence(kb.resolve(binding_id))
        if isinstance(target, QShortcut):
            target.setKey(seq)
        else:
            target.setShortcut(seq)

    _apply()
    kb.changed.connect(lambda changed_id: _apply() if changed_id == binding_id else None)
