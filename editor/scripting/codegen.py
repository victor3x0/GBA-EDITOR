"""
editor/scripting/codegen.py — Transpileur AST normalisé → C.

Reçoit un LuaScript (parser.py) et un CodegenContext (informations de
build) et produit le source C d'un fichier actor_<Name>.c.

Règles de génération :
  - Variables locales top-level  → static <type> g_<name>; (scope fichier)
  - Variables globales (globals.h) → accès direct par nom
  - self:method(args)  → actor_method(self, args) via RUNTIME_API
  - module.func(args)  → func_c(args) via RUNTIME_API
  - Opérateurs Lua     → opérateurs C (and→&&, or→||, ~=→!=, not→!)
  - Strings d'args API → constantes entières (ANIM_*, SFX_*, BTN_*, TAG_*)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .parser import (
    LuaScript, LuaFunction, LuaLocal,
    StmtCall, StmtAssign, StmtLocalAssign, StmtIf, StmtWhile,
    StmtForNum, StmtReturn, StmtBreak,
    ExprNumber, ExprBool, ExprNil, ExprString, ExprName,
    ExprIndex, ExprIndexAt, ExprTable, ExprInvoke, ExprCall, ExprBinop, ExprUnop,
    array_dims, DATA_NS,
)
from .api import (
    RUNTIME_API, EVENT_C_SIGNATURES, KNOWN_EVENTS, ApiFunc,
    KNOWN_SCENE_EVENTS, KNOWN_EVENTS_BY_KIND, scene_event_sig,
    DOMAIN_OBJ_MODE, DOMAIN_DIRECTION, DOMAIN_WIN_REGION,
    DOMAIN_BLEND_MODE, DOMAIN_BLEND_SIDE, hardware_enum_constant,
    DOMAIN_ANIM, DOMAIN_SFX, DOMAIN_MUSIC, DOMAIN_KEY, DOMAIN_TAG, DOMAIN_SCENE,
    DOMAIN_CAMERA, camera_constant,
    DOMAIN_TEXT, DOMAIN_FONT, DOMAIN_REGION, DOMAIN_IMAGE, DOMAIN_PALETTE,
    DOMAIN_PREFAB, DOMAIN_ACTOR, DOMAIN_GLOBAL, DOMAIN_CONST,
    anim_constant, sfx_constant, music_constant, key_constant, tag_constant, scene_constant,
    text_constant, font_constant, region_constant, anon_text_key, palette_constant,
    image_constant, image_state_constant,
    SCREEN_CONSTANTS,
)
from .checker import check as _lua_check, BuildContext as _BuildContext


# ─── Types C des variables exposées (table `exports`) ─────────────
# Le type déclaré dans le .lua pilote la déclaration C émise ; sans lui, une
# string exportée devenait `static int x = "";` (erreur gcc int-conversion).
# Le moteur est entièrement entier — aucun float dans runtime/ — donc `float`
# devient un int (le parser tronque déjà les littéraux, cf. ExprNumber).
# Les *_ref valent un index/handle entier (la résolution éditeur → valeur
# d'instance n'est pas encore câblée, cf. Script Inspector).
_EXPORT_C_TYPE: dict[str, str] = {
    "int":       "int",
    "float":     "int",
    "bool":      "int",
    "enum":      "int",
    "actor_ref": "int",
    "scene_ref": "int",
    "sfx_ref":   "int",
    "string":    "const char *",
}
# Types composites : pas de scalaire C équivalent, on ne déclare rien (un
# commentaire garde la trace de la variable côté C).
_EXPORT_COMPOSITE = ("vec2", "vec3", "rect")


# ─── Contexte de génération ───────────────────────────────────────

@dataclass
class CodegenContext:
    """
    Informations fournies par build.py pour la génération du C.
    Permet de résoudre les constantes (ANIM_*, SFX_*…) à la compilation.
    """
    actor_name:   str            # "Hero" — utilisé comme préfixe C
    actor_sym:    str            # "Hero" nettoyé pour C (ex: "Mon_Hero")
    anim_names:   list[str]      # ["idle", "walk", "attack"] — depuis SpriteAsset
    sfx_names:    list[str]      # noms des Sfx du projet
    music_names:  list[str]      # noms des Music du projet
    global_names: set[str]       # noms des variables globales (depuis globals.h)
    const_names:  set[str]       # noms des constantes (depuis constants.h)
    all_actor_syms: list[str]    # tous les acteurs de la scène
    is_scene: bool = False       # True → script SANS self (scène ou caméra)
    # Famille de propriétaire, quand is_scene : nomme le symbole C émis
    # (`<sym>_scene_on_update` / `<sym>_camera_on_update`). Une caméra a les
    # mêmes points d'entrée qu'une scène et emprunte donc le même chemin.
    hook_kind: str = "scene"
    scripts_dir: Path | None = None  # racine project/scripts/ pour résoudre les require()
    is_pooled: bool = False      # True → locals → self->data[N] (prefab poolé)
    scene_names: list[str] = field(default_factory=list)  # noms de scènes du projet
    sfx_component_name: Optional[str] = None  # Sfx lié au SoundFxComponent de cet actor (si présent)
    sfx_autoplay: bool = False   # True → SoundFxComponent.trigger == "on_spawn"
    sfx_volumes: dict = field(default_factory=dict)  # {nom Sfx: volume 0-255} — sfx_play(id, volume)
    music_info: dict = field(default_factory=dict)  # {nom Music: (loop, volume)} — music_play(id, loop, volume)
    text_keys:  list[str] = field(default_factory=list)  # clés de la table de textes (ordre = index C)
    font_names: list[str] = field(default_factory=list)  # polices encodables (ordre = index dans g_fonts)
    palette_names: list[str] = field(default_factory=list)  # catalogue de couleurs (ordre = index dans g_palettes)
    region_names: list[str] = field(default_factory=list)  # emplacements de texte (ordre = index dans g_ui_regions)
    image_names:  list[str] = field(default_factory=list)  # images d'interface (ordre = index dans g_ui_images)
    # {nom d'image: [noms d'état de SON sprite]} — un état n'a de sens que dans
    # un sprite, et c'est l'image que le script nomme (cf. api.image_state_constant).
    image_states: dict = field(default_factory=dict)
    # Tables de données : {nom: (noms de colonnes, nombre de lignes)}. Le nombre
    # de lignes sert à `#data.X`, qui est une constante de compilation comme
    # `#t` sur un tableau — la taille est connue, elle n'est rangée nulle part.
    data_tables: dict = field(default_factory=dict)
    # Sauvegarde — deux faits du projet, portés jusqu'ici pour que le checker des
    # BEHAVIORS (relancé depuis ce contexte-ci) voie ce que voit celui des
    # acteurs. Sans eux, `save.write(7)` passerait dans un behavior et pas dans
    # un script d'acteur, ce qui serait incompréhensible.
    save_slots: Optional[int] = None
    has_persistent: Optional[bool] = None


# ─── Générateur ───────────────────────────────────────────────────

class CodeGen:

    def __init__(self, ctx: CodegenContext):
        self.ctx   = ctx
        self._lines: list[str] = []
        self._indent = 0
        self._required_behaviors: dict[str, str] = {}  # alias Lua → sym C
        self._pool_locals: dict[str, tuple[int, any]] = {}  # name → (data_index, init_value)
        # Tableaux déclarés dans ce script : nom → dimensions. Sert à `#t`, qui
        # est une constante de compilation — la taille fait partie du type, donc
        # elle n'est rangée nulle part à l'exécution.
        self._arrays: dict[str, tuple[int, ...]] = {}
        self.warnings: list[str] = []  # diagnostics non bloquants (ex: behavior manquant/invalide)

    # ── API publique ──────────────────────────────────────────────

    def generate(self, script: LuaScript) -> str:
        """Retourne le source C complet pour ce script."""
        self._emit_header()
        self._emit_locals(script.locals)
        # Inline des behaviors requis (collectés pendant _emit_locals via StmtLocalAssign)
        self._emit_inlined_behaviors(script)
        # Fonction d'init des data[] pour les prefabs poolés (avant les handlers)
        if self.ctx.is_pooled:
            self._emit_pool_init()
        defined = set()
        for fn in script.functions:
            self._emit_function(fn)
            defined.add(fn.name)
        # Stubs vides pour les events non définis (évite les erreurs de linker)
        known = self._known_hooks() if self.ctx.is_scene else KNOWN_EVENTS
        for event in known:
            if event not in defined:
                self._emit_stub(event)
        return "\n".join(self._lines) + "\n"

    def _emit_pool_init(self):
        """Génère void SYM_pool_init(Actor* self) — appelée par spawn avant on_start."""
        sym = self.ctx.actor_sym
        self._w(f"void {sym}_pool_init(Actor* self) {{")
        self._indent += 1
        if self._pool_locals:
            for name, (idx, init_val) in self._pool_locals.items():
                self._w(f"self->data[{idx}] = {init_val};  /* {name} */")
        else:
            self._w("(void)self;")
        self._indent -= 1
        self._w("}")
        self._w("")

    def _emit_inlined_behaviors(self, script: LuaScript):
        """Parse et transpile les behaviors requis en fonctions C statiques inline."""
        from .parser import parse as lua_parse, LuaParseError
        if not self._required_behaviors or not self.ctx.scripts_dir:
            return
        self._w("/* ── Behaviors inlinés ── */")
        for alias, sym in self._required_behaviors.items():
            stem = sym[len("beh_"):]          # "paddle_ai"
            beh_path = self.ctx.scripts_dir / "behaviors" / f"{stem}.lua"
            if not beh_path.exists():
                msg = f"behavior '{stem}' introuvable : {beh_path}"
                self._w(f"/* {msg} */")
                self.warnings.append(msg)
                continue
            beh_src = beh_path.read_text(encoding="utf-8")
            try:
                beh_ast = lua_parse(beh_src)
            except LuaParseError as ex:
                msg = f"behavior '{stem}' : erreur de parse Lua : {ex}"
                self._w(f"/* {msg} */")
                self.warnings.append(msg)
                continue
            # Validation basique (mêmes vérifs que les scripts actor/scène/prefab,
            # avec le contexte de l'actor qui inline ce behavior — pas de vérif de
            # plage sur les globals ici, cf. ARCHITECTURE.md pour les limites connues).
            check_ctx = _BuildContext(
                actor_name   = self.ctx.actor_name,
                anim_names   = self.ctx.anim_names,
                sfx_names    = self.ctx.sfx_names,
                music_names  = self.ctx.music_names,
                scene_names  = self.ctx.scene_names,
                global_names = list(self.ctx.global_names) if self.ctx.global_names else None,
                const_names  = list(self.ctx.const_names) if self.ctx.const_names else None,
                sfx_component_name = self.ctx.sfx_component_name,
                save_slots   = self.ctx.save_slots,
                has_persistent = self.ctx.has_persistent,
                data_tables  = self.ctx.data_tables or None,
            )
            for err in _lua_check(beh_ast, check_ctx, check_event_names=False):
                self.warnings.append(f"behavior '{stem}': {err.message}")
            # Émettre chaque fonction du module comme helper C statique préfixé
            for fn in beh_ast.functions:
                # Ignore le nom de module (M.update → beh_paddle_ai_update)
                func_name = fn.name.split(".")[-1] if "." in fn.name else fn.name
                c_name    = f"{sym}_{func_name}"
                # Signature : premier param est l'actor receveur (conventionnellement "actor" ou "self")
                params_c  = ", ".join(
                    f"Actor* {p}" if i == 0 else f"int {p}"
                    for i, p in enumerate(fn.params)
                )
                self._w(f"static void {c_name}({params_c}) {{")
                self._indent += 1
                self._emit_block(fn.body)
                self._indent -= 1
                self._w("}")
                self._w("")

    def _scan_requires(self, stmts):
        """Pré-scan récursif pour enregistrer les require() avant la génération."""
        from .parser import StmtLocalAssign, ExprCall, ExprName, ExprString
        for s in stmts:
            if (isinstance(s, StmtLocalAssign)
                    and s.value is not None
                    and isinstance(s.value, ExprCall)
                    and isinstance(s.value.func, ExprName)
                    and s.value.func.name == "require"
                    and s.value.args
                    and isinstance(s.value.args[0], ExprString)):
                path_str = s.value.args[0].value
                stem     = Path(path_str).stem
                sym      = f"beh_{stem}"
                self._required_behaviors[s.name] = sym

    # ── En-tête ───────────────────────────────────────────────────

    def _known_hooks(self) -> list:
        """Les points d'entrée admis pour ce propriétaire — une scène en a
        trois, une caméra deux (cf. KNOWN_EVENTS_BY_KIND)."""
        return KNOWN_EVENTS_BY_KIND.get(self.ctx.hook_kind, KNOWN_SCENE_EVENTS)

    def _emit_header(self):
        sym = self.ctx.actor_sym
        if self.ctx.is_scene:
            kind = self.ctx.hook_kind
            self._w(f"/* {sym}.c — script de {kind}, généré par GBA Editor (ne pas éditer) */")
        else:
            self._w(f"/* actor_{sym}.c — généré par GBA Editor (ne pas éditer) */")
        # `actor_api.h` et non `runtime.h` : c'est l'en-tête généré qui porte
        # la vraie struct Actor et l'API. Le C émis l'incluait autrefois sous le
        # nom `runtime.h`, que chaque appelant remplaçait ensuite par celui-ci —
        # un détour dont il ne restait que le nom.
        self._w('#include "actor_api.h"')
        self._w('#include "globals.h"')
        self._w('#include "constants.h"')
        # Toujours inclus, même sans table : l'en-tête est toujours généré, et
        # un include conditionnel serait un second chemin pour un cas vide.
        self._w('#include "data_tables.h"')
        # Forward declarations pour éviter les erreurs d'ordre (ex: destroy appelle on_destroy)
        if not self.ctx.is_scene:
            self._w("")
            known = KNOWN_EVENTS
            for event in known:
                sig_tpl = EVENT_C_SIGNATURES.get(event)
                if sig_tpl:
                    self._w(sig_tpl.format(prefix=sym) + ";")
        # Constantes d'animation pour cet acteur
        if self.ctx.anim_names:
            self._w("")
            self._w(f"/* Animations de {self.ctx.actor_name} */")
            for i, name in enumerate(self.ctx.anim_names):
                self._w(f"#define {anim_constant(sym, name)} {i}")
        # Constantes SFX
        if self.ctx.sfx_names:
            self._w("")
            self._w("/* SFX */")
            for i, name in enumerate(self.ctx.sfx_names):
                self._w(f"#define {sfx_constant(name)} {i}")
        # Constantes Music
        if self.ctx.music_names:
            self._w("")
            self._w("/* Music */")
            for i, name in enumerate(self.ctx.music_names):
                self._w(f"#define {music_constant(name)} {i}")
        # Constantes Texte — index dans la table g_texts émise par main_gen
        if self.ctx.text_keys:
            self._w("")
            self._w("/* Textes */")
            for i, key in enumerate(self.ctx.text_keys):
                self._w(f"#define {text_constant(key)} {i}")
        # Constantes Police — index dans g_fonts (même ordre que main_gen)
        if self.ctx.font_names:
            self._w("")
            self._w("/* Polices */")
            for i, name in enumerate(self.ctx.font_names):
                self._w(f"#define {font_constant(name)} {i}")
        # Constantes Palette — index dans g_palettes. Le catalogue ENTIER y
        # passe : une palette pèse 32 octets en ROM, là où la réservation des
        # polices coûtait de la mémoire vidéo. Rien à dériver des scripts, donc
        # aucun risque de réserver trop peu — le piège que `scene_font_names`
        # doit désamorcer n'existe pas ici.
        if self.ctx.palette_names:
            self._w("")
            self._w("/* Palettes */")
            for i, name in enumerate(self.ctx.palette_names):
                self._w(f"#define {palette_constant(name)} {i}")
        # Constantes Zone de texte — index dans g_ui_regions. L'espace de noms
        # est le PROJET, pas la mise en page (cf. models/ui_region.py) : c'est
        # ce qui permet à cette table d'être plate, comme celle des textes.
        if self.ctx.region_names:
            self._w("")
            self._w("/* Emplacements de texte */")
            for i, name in enumerate(self.ctx.region_names):
                self._w(f"#define {region_constant(name)} {i}")
        # Constantes Image — index dans g_ui_images, même espace de noms projet
        # et même raison. Les ÉTATS suivent, indexés par IMAGE : un nom d'état
        # n'existe que dans un sprite, et c'est l'image que le script nomme.
        if self.ctx.image_names:
            self._w("")
            self._w("/* Images d'interface */")
            for i, name in enumerate(self.ctx.image_names):
                self._w(f"#define {image_constant(name)} {i}")
                for k, st in enumerate(self.ctx.image_states.get(name, [])):
                    self._w(f"#define {image_state_constant(name, st)} {k}")
        self._w("")

    # ── Variables locales top-level (static = scope fichier) ──────

    def _emit_locals(self, locals_: list[LuaLocal]):
        # Pré-enregistrer les require() et les exclure des déclarations C
        for loc in locals_:
            if (loc.value is not None
                    and isinstance(loc.value, ExprCall)
                    and isinstance(loc.value.func, ExprName)
                    and loc.value.func.name == "require"
                    and loc.value.args
                    and isinstance(loc.value.args[0], ExprString)):
                path_str = loc.value.args[0].value
                stem     = Path(path_str).stem
                self._required_behaviors[loc.name] = f"beh_{stem}"

        non_require = [
            loc for loc in locals_
            if not (loc.value is not None
                    and isinstance(loc.value, ExprCall)
                    and isinstance(loc.value.func, ExprName)
                    and loc.value.func.name == "require")
        ]
        if not non_require:
            return
        if self.ctx.is_pooled:
            # Prefab poolé : locals → self->data[N] (état par instance). Seuls
            # les scalaires entiers y tiennent — une string/composite retombe
            # sur une déclaration de fichier (partagée entre instances, sans
            # danger : ce sont des constantes d'initialisation).
            self._w("/* Variables locales — stockées dans Actor.data[] (une par instance) */")
            slot = 0
            for loc in non_require:
                dims = array_dims(loc.value)
                if dims:
                    # `Actor.data[8]` porte huit ENTIERS par instance : un
                    # tableau n'y tient pas. Le laisser retomber sur une
                    # déclaration de fichier le ferait partager par toutes les
                    # instances, silencieusement — le checker refuse donc en
                    # amont, et cette trace n'existe que si on l'a contourné.
                    msg = (f"'{loc.name}' : un tableau ne peut pas vivre dans un "
                           f"prefab poolé (Actor.data[] ne porte que des entiers).")
                    self._w(f"/* {msg} */")
                    self.warnings.append(msg)
                    continue
                c_type, init, note = self._local_decl(loc)
                if c_type == "int":
                    self._pool_locals[loc.name] = (slot, init)
                    self._w(f"/* data[{slot}] = {loc.name} (init={init}) */")
                    slot += 1
                elif c_type is None:
                    self._w(f"/* {loc.name} : {note} */")
                else:
                    self._w(f"static {c_type} {self._unused_attr(loc)}{loc.name} = {init};"
                            f"   /* {note or 'partagé entre instances'} */")
        else:
            # Actor statique : locals → variables C statiques (partagées, OK car une seule instance)
            self._w("/* Variables locales à cet acteur */")
            for loc in non_require:
                dims = array_dims(loc.value)
                if dims:
                    self._arrays[loc.name] = dims
                    self._w(f"static {self._array_decl(loc.name, dims)} = "
                            f"{self._array_init(loc.value, dims)};")
                    continue
                c_type, init, note = self._local_decl(loc)
                if c_type is None:
                    self._w(f"/* {loc.name} : {note} */")
                    continue
                suffix = f"   /* {note} */" if note else ""
                self._w(f"static {c_type} {self._unused_attr(loc)}{loc.name} = {init};{suffix}")
        self._w("")

    @staticmethod
    def _unused_attr(loc: LuaLocal) -> str:
        """Une variable exposée est déclarée pour l'éditeur : elle peut
        légitimement n'être lue par aucune ligne du script (-Wunused-variable
        à chaque build sinon). Un vrai `local` inutilisé reste signalé."""
        return "__attribute__((unused)) " if loc.export_type else ""

    def _local_decl(self, loc: LuaLocal) -> tuple[Optional[str], str, str]:
        """(type C, initialiseur, commentaire) pour un local top-level ou une
        variable exposée. Type C = None → rien à déclarer (composite).

        Le type déclaré dans `exports` fait foi ; pour un vrai `local`, il est
        déduit de la valeur d'initialisation (une string littérale n'est pas
        un int)."""
        typ = (loc.export_type or "").strip()
        if typ in _EXPORT_COMPOSITE:
            return None, "", f"type '{typ}' non représentable en scalaire C — non déclaré"

        init = self._expr(loc.value) if loc.value is not None else None

        if typ in _EXPORT_C_TYPE:
            c_type = _EXPORT_C_TYPE[typ]
            if c_type == "const char *":
                return c_type, init if init is not None else '""', ""
            if init is None:
                return c_type, "0", ""
            # Un défaut string sur un type entier (actor_ref/scene_ref/enum non
            # résolus) ne peut pas initialiser un int : on repart de 0.
            if isinstance(loc.value, ExprString):
                return c_type, "0", f"référence '{loc.value.value or 'vide'}' non résolue au build"
            # Les littéraux flottants sont déjà tronqués par le parser
            # (ExprNumber(int(...)) — le moteur n'a pas de flottants).
            return c_type, init, ""

        if typ:
            self.warnings.append(
                f"exports : type '{typ}' inconnu pour '{loc.name}' — déclaré en int."
            )

        # Vrai `local` (ou export de type inconnu) : déduction depuis la valeur.
        if isinstance(loc.value, ExprString):
            return "const char *", init, ""
        return "int", init if init is not None else "0", ""

    # ── Tableaux ──────────────────────────────────────────────────

    @staticmethod
    def _array_decl(name: str, dims: tuple[int, ...]) -> str:
        """`grille`, (20, 12) → « int grille[20][12] ». Le premier argument
        d'`array` est le premier index, en Lua comme en C."""
        return f"int {name}" + "".join(f"[{d}]" for d in dims)

    def _array_init(self, value, dims: tuple[int, ...]) -> str:
        """L'initialiseur C. `{1, 2, 4, 8}` recopie les valeurs écrites ;
        `array(n)` remplit de zéros."""
        if isinstance(value, ExprTable):
            if len(dims) == 2:
                return "{" + ", ".join(
                    "{" + ", ".join(self._expr(v) for v in row.items) + "}"
                    for row in value.items) + "}"
            return "{" + ", ".join(self._expr(v) for v in value.items) + "}"
        return "{0}" if len(dims) == 1 else "{{0}}"

    @staticmethod
    def _data_table_ref(e) -> Optional[str]:
        """`data.Objets` → "Objets", sinon None."""
        if (isinstance(e, ExprIndex) and isinstance(e.obj, ExprName)
                and e.obj.name == DATA_NS):
            return e.field
        return None

    def _array_length(self, operand) -> Optional[int]:
        """La valeur de `#x`, connue au build. `#t` est le nombre d'éléments,
        `#t[i]` la longueur d'une ligne d'un tableau à deux dimensions, et
        `#data.X` le nombre de lignes de la table."""
        name = self._data_table_ref(operand)
        if name is not None:
            entry = self.ctx.data_tables.get(name)
            return entry[1] if entry else None
        if isinstance(operand, ExprName):
            dims = self._arrays.get(operand.name)
            return dims[0] if dims else None
        if isinstance(operand, ExprIndexAt) and isinstance(operand.obj, ExprName):
            dims = self._arrays.get(operand.obj.name)
            return dims[1] if dims and len(dims) == 2 else None
        return None

    def _index(self, e) -> str:
        """Lua indexe à partir de 1, le C à partir de 0 — la traduction se fait
        ici, une fois. Un index littéral est replié tout de suite : `t[1]`
        devient `t[0]` et non `t[(1) - 1]`."""
        if isinstance(e, ExprNumber):
            return str(e.value - 1)
        return f"({self._expr(e)}) - 1"

    # ── Fonctions / handlers ──────────────────────────────────────

    def _emit_function(self, fn: LuaFunction):
        if self.ctx.is_scene:
            sym = self.ctx.actor_sym
            if fn.name in self._known_hooks():
                sig = scene_event_sig(sym, fn.name, self.ctx.hook_kind)   # "void PONG_scene_on_start(void)"
            else:
                sig = f"static void {sym}_scene_{fn.name}(void)"
        else:
            sig_tpl = EVENT_C_SIGNATURES.get(fn.name)
            if sig_tpl is None:
                sig = f"static void {self.ctx.actor_sym}_{fn.name}(Actor* self)"
            else:
                sig = sig_tpl.format(prefix=self.ctx.actor_sym)
        self._w(sig + " {")
        self._indent += 1
        if not self.ctx.is_scene and fn.name == "on_start":
            self._emit_sfx_autoplay()
        self._emit_block(fn.body)
        self._indent -= 1
        self._w("}")
        self._w("")

    def _emit_sfx_autoplay(self):
        """Injecte l'appel sfx_play() auto au début de on_start si trigger == 'on_spawn'."""
        if self.ctx.sfx_autoplay and self.ctx.sfx_component_name:
            self._w(f"sfx_play({sfx_constant(self.ctx.sfx_component_name)});")

    # ── Blocs et statements ───────────────────────────────────────

    def _emit_block(self, stmts: list):
        for s in stmts:
            self._emit_stmt(s)

    def _emit_stmt(self, s):
        if isinstance(s, StmtCall):
            self._w(self._call_expr(s.call) + ";")

        elif isinstance(s, StmtAssign):
            tgt = self._expr(s.target)
            val = self._expr(s.value)
            self._w(f"{tgt} = {val};")

        elif isinstance(s, StmtLocalAssign):
            # Détecte local M = require("behaviors/foo") → enregistre l'alias, pas de décl C
            if (s.value is not None
                    and isinstance(s.value, ExprCall)
                    and isinstance(s.value.func, ExprName)
                    and s.value.func.name == "require"
                    and s.value.args
                    and isinstance(s.value.args[0], ExprString)):
                path_str = s.value.args[0].value          # "behaviors/paddle_ai"
                stem     = Path(path_str).stem             # "paddle_ai"
                sym      = f"beh_{stem}"                   # "beh_paddle_ai"
                self._required_behaviors[s.name] = sym
                # Pas de déclaration C — le behavior est inclus dans l'en-tête
                return
            dims = array_dims(s.value)
            if dims:
                # Un tableau déclaré DANS un handler est reconstruit à chaque
                # appel, comme n'importe quel `local` de Lua.
                self._arrays[s.name] = dims
                self._w(f"{self._array_decl(s.name, dims)} = "
                        f"{self._array_init(s.value, dims)};")
                return
            val = self._expr(s.value) if s.value is not None else "0"
            # Détecte local var = get_actor("...") → Actor* au lieu de int
            is_actor_ref = (
                s.value is not None
                and isinstance(s.value, ExprCall)
                and isinstance(s.value.func, ExprName)
                and s.value.func.name == "get_actor"
            )
            ctype = "Actor*" if is_actor_ref else "int"
            self._w(f"{ctype} {s.name} = {val};")

        elif isinstance(s, StmtIf):
            cond = self._expr(s.cond)
            self._w(f"if ({cond}) {{")
            self._indent += 1
            self._emit_block(s.then)
            self._indent -= 1
            for elif_cond, elif_body in s.elseifs:
                self._w(f"}} else if ({self._expr(elif_cond)}) {{")
                self._indent += 1
                self._emit_block(elif_body)
                self._indent -= 1
            if s.else_:
                self._w("} else {")
                self._indent += 1
                self._emit_block(s.else_)
                self._indent -= 1
            self._w("}")

        elif isinstance(s, StmtWhile):
            self._w(f"while ({self._expr(s.cond)}) {{")
            self._indent += 1
            self._emit_block(s.body)
            self._indent -= 1
            self._w("}")

        elif isinstance(s, StmtForNum):
            # for i = start, stop[, step] do
            start = self._expr(s.start)
            stop  = self._expr(s.stop) if s.stop else "0"
            step  = self._expr(s.step) if s.step else "1"
            v     = s.var
            # Le SENS de la comparaison se décide au build, donc le pas doit
            # être un littéral (le checker le refuse autrement) : un pas calculé
            # obligerait à tester son signe à chaque tour, dans un moteur qui ne
            # teste rien ailleurs.
            descend = ((isinstance(s.step, ExprUnop) and s.step.op == "-")
                       or (isinstance(s.step, ExprNumber) and s.step.value < 0))
            cmp     = ">=" if descend else "<="
            self._w(f"for (int {v} = {start}; {v} {cmp} {stop}; {v} += {step}) {{")
            self._indent += 1
            self._emit_block(s.body)
            self._indent -= 1
            self._w("}")

        elif isinstance(s, StmtReturn):
            if s.values:
                self._w(f"return {self._expr(s.values[0])};")
            else:
                self._w("return;")

        elif isinstance(s, StmtBreak):
            self._w("break;")

    # ── Expressions ───────────────────────────────────────────────

    def _expr(self, e) -> str:
        if e is None:
            return "0"
        if isinstance(e, ExprNumber):
            return str(e.value)
        if isinstance(e, ExprBool):
            return "1" if e.value else "0"
        if isinstance(e, ExprNil):
            return "0"
        if isinstance(e, ExprString):
            # String littérale en dehors d'un appel API → chaîne C (rare en v1)
            return f'"{e.value}"'
        if isinstance(e, ExprName):
            # Prefab poolé : locals → self->data[N]
            if self.ctx.is_pooled and e.name in self._pool_locals:
                idx, _ = self._pool_locals[e.name]
                return f"self->data[{idx}]"
            return e.name
        if isinstance(e, ExprIndex):
            # screen.width / screen.height / etc. → littéral C
            if isinstance(e.obj, ExprName) and e.obj.name == "screen":
                val = SCREEN_CONSTANTS.get(e.field)
                if val is not None:
                    return str(val)
            # `data.Objets` → le tableau const émis par data_tables.c. Ce qui
            # suit (l'indexation puis la colonne) se compose tout seul : le
            # `.champ` ci-dessous et `ExprIndexAt` s'appliquent au résultat,
            # exactement comme en Lua.
            table = self._data_table_ref(e)
            if table is not None:
                return f"g_data_{table}"
            # module.field — retourne le nom composé pour la résolution ultérieure
            return f"{self._expr(e.obj)}.{e.field}"
        if isinstance(e, ExprIndexAt):
            return f"{self._expr(e.obj)}[{self._index(e.index)}]"
        if isinstance(e, ExprTable):
            # Un constructeur n'a de sens que comme initialiseur de déclaration
            # (`_array_init`) : ailleurs, il n'y a pas de tableau à écrire dedans.
            self.warnings.append("un constructeur { } ne peut initialiser qu'un "
                                 "tableau déclaré par `local`.")
            return "0"
        if isinstance(e, (ExprInvoke, ExprCall)):
            return self._call_expr(e)
        if isinstance(e, ExprBinop):
            return f"({self._expr(e.left)} {e.op} {self._expr(e.right)})"
        if isinstance(e, ExprUnop):
            if e.op == "#":
                n = self._array_length(e.operand)
                if n is None:
                    self.warnings.append("`#` appliqué à autre chose qu'un "
                                         "tableau déclaré dans ce script.")
                    return "0"
                return str(n)
            op = "!" if e.op == "not" else e.op
            return f"({op}{self._expr(e.operand)})"
        return "0"

    # ── Résolution des appels API ──────────────────────────────────

    def _call_expr(self, e) -> str:
        """Génère le C pour un appel de fonction/méthode."""
        if isinstance(e, ExprInvoke):
            return self._invoke(e)
        if isinstance(e, ExprCall):
            return self._call(e)
        return "/* appel non géré */"

    def _invoke(self, e: ExprInvoke) -> str:
        """var:method(args) — var peut être self ou toute variable Actor*."""
        if not isinstance(e.obj, ExprName):
            return f"/* invoke sur expression complexe ignoré */"
        receiver = e.obj.name          # "self", "other", "paddle", ...
        key = f"self:{e.method}"       # les méthodes sont toujours indexées sous "self:"
        custom = _INVOKE_CUSTOM.get(key)
        if custom:
            return custom(self, e.args, receiver)
        api = RUNTIME_API.get(key)
        if api is None:
            args = ", ".join(self._expr(a) for a in e.args)
            return f"actor_{e.method}({receiver}, {args})"
        return self._emit_api_call(api, e.args, receiver=receiver)

    def _call(self, e: ExprCall) -> str:
        """func(args) ou module.func(args)"""
        key = self._call_key(e.func)

        # Appel sur un behavior requis : AI.update(self, x) → beh_foo_update(self, x)
        if (isinstance(e.func, ExprIndex)
                and isinstance(e.func.obj, ExprName)
                and e.func.obj.name in self._required_behaviors):
            sym  = self._required_behaviors[e.func.obj.name]
            func = f"{sym}_{e.func.field}"
            args = ", ".join(self._expr(a) for a in e.args)
            return f"{func}({args})"

        # Cas spéciaux résolus directement par le codegen (table de dispatch,
        # cf. _CALL_CUSTOM en bas de fichier — pas d'appel de fonction C simple,
        # ou arguments C synthétisés depuis le contexte de build).
        custom = _CALL_CUSTOM.get(key) if key else None
        if custom:
            return custom(self, e.args)

        api = RUNTIME_API.get(key) if key else None
        if api is None:
            # Appel à une fonction helper interne ou inconnue
            func_c = key or self._expr(e.func)
            args   = ", ".join(self._expr(a) for a in e.args)
            return f"{func_c}({args})"
        return self._emit_api_call(api, e.args, with_self=False)

    def _call_key(self, func_expr) -> Optional[str]:
        if isinstance(func_expr, ExprName):
            return func_expr.name
        if isinstance(func_expr, ExprIndex):
            if isinstance(func_expr.obj, ExprName):
                return f"{func_expr.obj.name}.{func_expr.field}"
        return None

    def _emit_api_call(self, api: ApiFunc, lua_args: list,
                       with_self: bool = False, receiver: str | None = None) -> str:
        """Génère l'appel C en résolvant les args string → constantes."""
        c_args = []
        if receiver is not None:
            c_args.append(receiver)
        elif with_self:
            c_args.append("self")
        for param, arg in zip(api.params, lua_args):
            c_args.append(self._resolve_arg(param, arg))
        # Args variadiques : tous ceux qui dépassent les params déclarés
        if api.variadic:
            for extra in lua_args[len(api.params):]:
                c_args.append(self._expr(extra))
        return f"{api.c_func}({', '.join(c_args)})"

    def _resolve_arg(self, param, arg) -> str:
        """Convertit un arg Lua en expression C, résolvant les strings → constantes."""
        from .api import PARAM_STR_LITERAL
        if param.ptype == PARAM_STR_LITERAL:
            # Chaîne littérale → guillemets C, sans résolution de constante
            val = arg.value if isinstance(arg, ExprString) else self._expr(arg)
            return f'"{val}"' if isinstance(arg, ExprString) else val
        if not isinstance(arg, ExprString) or param.domain is None:
            return self._expr(arg)
        name = arg.value
        make_constant = _DOMAIN_CONSTANT.get(param.domain)
        if make_constant is None:
            # Domaine sans constante générique : la chaîne part telle quelle.
            # Légitime pour les domaines résolus par un émetteur dédié
            # (_DOMAIN_EMITTED_ELSEWHERE), qui n'arrivent pas jusqu'ici — et
            # c'est `validator._check_api_domains` qui garantit qu'aucun autre
            # domaine ne tombe dans ce cas par oubli.
            return f'"{name}"'
        return make_constant(self, name)

    # ── Cas spéciaux ──────────────────────────────────────────────

    def _emit_play_sfx(self, args: list, receiver: str) -> str:
        """self:play_sfx() → sfx_play(SFX_X, volume) où X/volume viennent du SoundFxComponent."""
        if not self.ctx.sfx_component_name:
            return "(void)0 /* self:play_sfx() : aucun SoundFX configuré sur cet actor */"
        name   = self.ctx.sfx_component_name
        volume = self.ctx.sfx_volumes.get(name, 255)
        return f"sfx_play({sfx_constant(name)}, {volume})"

    def _emit_destroy(self, args: list, receiver: str) -> str:
        """self:destroy() → appelle on_destroy() puis désactive l'actor."""
        sym = self.ctx.actor_sym
        return f"{sym}_on_destroy({receiver}); actor_destroy_internal({receiver})"

    def _emit_sfx_play(self, args: list) -> str:
        """sfx.play("Name") → sfx_play(SFX_NAME, volume) — volume lu depuis la ressource Sfx."""
        if not args or not isinstance(args[0], ExprString):
            return "/* sfx.play() : argument invalide */"
        name   = args[0].value
        volume = self.ctx.sfx_volumes.get(name, 255)
        return f"sfx_play({sfx_constant(name)}, {volume})"

    def _emit_music_play(self, args: list) -> str:
        """music.play("Name") → music_play(MUSIC_NAME, loop, volume) — loop/volume lus depuis la ressource Music."""
        if not args or not isinstance(args[0], ExprString):
            return "/* music.play() : argument invalide */"
        name = args[0].value
        loop, volume = self.ctx.music_info.get(name, (True, 255))
        return f"music_play({music_constant(name)}, {1 if loop else 0}, {volume})"

    def _emit_ui_image_set(self, args: list) -> str:
        """ui.image_set("coeur_2", "vide") → ui_image_set_state(IMAGE_COEUR_2,
        IMGST_COEUR_2_VIDE).

        Le seul appel d'image qui ne se traduit pas terme à terme : un nom
        d'état n'a de sens que DANS un sprite, donc sa constante est indexée par
        l'image, et il faut les deux arguments à la fois pour la construire — ce
        que `_map_arg`, qui voit un argument isolé, ne peut pas faire."""
        if len(args) < 2 or not all(isinstance(a, ExprString) for a in args[:2]):
            return "/* ui.image_set() : les deux arguments doivent être littéraux */"
        image, state = args[0].value, args[1].value
        return (f"ui_image_set_state({image_constant(image)}, "
                f"{image_state_constant(image, state)})")

    def _emit_array_misuse(self, args: list) -> str:
        """`array(n)` DÉCLARE un tableau : il est lu à l'endroit du `local`
        (cf. `_emit_locals`), et n'arrive ici que s'il a été écrit ailleurs —
        dans un calcul, un argument. Il n'y a rien à émettre pour ça."""
        self.warnings.append("array() déclare un tableau et ne s'écrit que dans "
                             "un `local` : local sac = array(8).")
        return "0 /* array() hors d'une déclaration */"

    def _emit_get_actor(self, args: list) -> str:
        """
        get_actor("PADDLE_AUTO")  →  &g_actors[TAG_PADDLE_AUTO]
        Résolu à la compilation, zéro overhead runtime. Le nom doit être
        sanitisé avec la même fonction que celle qui définit les macros
        TAG_* (headers.py::generate_actor_types, via codegen.c_names.sym) —
        sinon un nom d'actor avec un caractère hors [A-Za-z0-9_] (ex: un tiret)
        référence une macro qui n'existe pas.
        """
        from codegen.c_names import sym as c_sym
        if not args or not isinstance(args[0], ExprString):
            return "/* get_actor() : argument invalide */"
        sym = c_sym(args[0].value)
        return f"&g_actors[TAG_{sym.upper()}]"

    def _emit_actor_spawn(self, args: list) -> str:
        """actor.spawn("PrefabName", x, y) → spawn_PrefabName(x, y)"""
        if not args or not isinstance(args[0], ExprString):
            return "/* actor.spawn : nom de prefab non littéral */"
        prefab_name = args[0].value
        sym = prefab_name.replace(" ", "_")
        rest = ", ".join(self._expr(a) for a in args[1:])
        return f"spawn_{sym}({rest})"

    def _emit_global_get(self, args: list) -> str:
        if args and isinstance(args[0], ExprString):
            return f"g_{args[0].value}"
        return "/* global.get : nom non littéral */"

    def _emit_global_set(self, args: list) -> str:
        if len(args) >= 2 and isinstance(args[0], ExprString):
            val = self._expr(args[1])
            return f"g_{args[0].value} = {val}"
        return "/* global.set : nom non littéral */"

    def _emit_const_get(self, args: list) -> str:
        if args and isinstance(args[0], ExprString):
            return f"CONST_{args[0].value.upper()}"
        return "/* const.get : nom non littéral */"

    def _emit_stub(self, event_name: str):
        """Stub vide pour un event non défini dans le script."""
        if self.ctx.is_scene:
            if event_name not in self._known_hooks():
                return
            sig = scene_event_sig(self.ctx.actor_sym, event_name, self.ctx.hook_kind)
            self._w(sig + " {}")
        else:
            sig_tpl = EVENT_C_SIGNATURES.get(event_name)
            if sig_tpl is None:
                return
            sig = sig_tpl.format(prefix=self.ctx.actor_sym)
            sig = sig.replace("Actor* self", "Actor* self __attribute__((unused))")
            sig = sig.replace("Actor* other", "Actor* other __attribute__((unused))")
            sig = sig.replace("int event_id", "int event_id __attribute__((unused))")
            sig = sig.replace("int value", "int value __attribute__((unused))")
            sig = sig.replace("u8 my_box", "u8 my_box __attribute__((unused))")
            sig = sig.replace("u8 other_box", "u8 other_box __attribute__((unused))")
            sig = sig.replace("int normal_x", "int normal_x __attribute__((unused))")
            sig = sig.replace("int normal_y", "int normal_y __attribute__((unused))")
            if event_name == "on_start" and self.ctx.sfx_autoplay and self.ctx.sfx_component_name:
                self._w(sig + " {")
                self._indent += 1
                self._emit_sfx_autoplay()
                self._indent -= 1
                self._w("}")
            else:
                self._w(sig + " {}")
        self._w("")

    # ── Émission de lignes ────────────────────────────────────────

    def _w(self, line: str):
        self._lines.append("    " * self._indent + line)


# ─── Tables de dispatch — fonctions Lua qui ne se traduisent pas par un
# simple appel de fonction C (expression brute, args synthétisés depuis le
# contexte de build, émission multi-instructions...). Chaque clé existe
# aussi dans RUNTIME_API (scripting/api.py) pour la validation/doc — cette
# table ne gère que la traduction C, à un seul endroit plutôt qu'éparpillée
# en if/elif dans _invoke/_call.

_INVOKE_CUSTOM: dict = {
    "self:destroy":  CodeGen._emit_destroy,
    "self:play_sfx": CodeGen._emit_play_sfx,
}

# ── Résolution des domaines : un domaine → la constante C ──────────
# Une table et non un `match` : elle se compare à `ALL_DOMAINS` au build
# (`validator._check_api_domains`), ce qu'une suite de `case` ne permet pas.
# Un domaine ajouté sans entrée ici partait en littéral C, silencieusement.
_DOMAIN_CONSTANT: dict = {
    DOMAIN_ANIM:    lambda g, name: anim_constant(g.ctx.actor_sym, name),
    DOMAIN_SFX:     lambda g, name: sfx_constant(name),
    DOMAIN_MUSIC:   lambda g, name: music_constant(name),
    DOMAIN_KEY:     lambda g, name: key_constant(name),
    DOMAIN_TAG:     lambda g, name: tag_constant(name),
    DOMAIN_SCENE:   lambda g, name: scene_constant(name),
    DOMAIN_CAMERA:  lambda g, name: camera_constant(name),
    # Une chaîne qui ne matche aucune clé est un LITTÉRAL (`text.draw` seul le
    # permet, cf. Param.literal_ok) : il a sa propre entrée de table, donc le C
    # ne voit qu'un index comme pour tout texte.
    DOMAIN_TEXT:    lambda g, name: text_constant(
        name if name in g.ctx.text_keys else anon_text_key(name)),
    DOMAIN_FONT:    lambda g, name: font_constant(name),
    DOMAIN_PALETTE: lambda g, name: palette_constant(name),
    DOMAIN_REGION:  lambda g, name: region_constant(name),
    DOMAIN_IMAGE:   lambda g, name: image_constant(name),
    # Énumérations matérielles : la constante C vient de `HARDWARE_ENUMS`, la
    # même table que celle où le checker a validé le nom. Le C généré porte donc
    # `WINR_OBJ` et non `2` — lisible pour qui relit le build.
    DOMAIN_OBJ_MODE:   lambda g, name: hardware_enum_constant(DOMAIN_OBJ_MODE, name),
    DOMAIN_DIRECTION:  lambda g, name: hardware_enum_constant(DOMAIN_DIRECTION, name),
    DOMAIN_WIN_REGION: lambda g, name: hardware_enum_constant(DOMAIN_WIN_REGION, name),
    DOMAIN_BLEND_MODE: lambda g, name: hardware_enum_constant(DOMAIN_BLEND_MODE, name),
    DOMAIN_BLEND_SIDE: lambda g, name: hardware_enum_constant(DOMAIN_BLEND_SIDE, name),
}

# Domaines SANS constante générique : leur argument est résolu par un émetteur
# dédié de `_CALL_CUSTOM` (nom de prefab poolé, actor résolu à la compilation,
# variable C nommée) et n'atteint donc jamais `_resolve_arg`. Les déclarer est
# ce qui distingue « traité ailleurs » de « oublié ».
_DOMAIN_EMITTED_ELSEWHERE: frozenset = frozenset({
    DOMAIN_PREFAB, DOMAIN_ACTOR, DOMAIN_GLOBAL, DOMAIN_CONST,
})


def covered_domains() -> frozenset:
    """Domaines dont le codegen sait quoi faire — constante générique, ou
    émetteur dédié. Pendant exact de `checker.covered_domains()`."""
    return frozenset(_DOMAIN_CONSTANT) | _DOMAIN_EMITTED_ELSEWHERE


_CALL_CUSTOM: dict = {
    "array":       CodeGen._emit_array_misuse,
    "get_actor":   CodeGen._emit_get_actor,
    "global.get":  CodeGen._emit_global_get,
    "global.set":  CodeGen._emit_global_set,
    "const.get":   CodeGen._emit_const_get,
    "actor.spawn": CodeGen._emit_actor_spawn,
    "sfx.play":    CodeGen._emit_sfx_play,
    "music.play":  CodeGen._emit_music_play,
    "ui.image_set": CodeGen._emit_ui_image_set,
}


# ─── Point d'entrée public ────────────────────────────────────────

def generate(script: LuaScript, ctx: CodegenContext) -> tuple[str, list[str]]:
    """Retourne (code C, warnings) — warnings couvre les behaviors requis
    manquants/invalides, non bloquants mais à faire remonter à l'utilisateur."""
    gen = CodeGen(ctx)
    code = gen.generate(script)
    return code, gen.warnings
