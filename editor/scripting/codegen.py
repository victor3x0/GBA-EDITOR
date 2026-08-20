"""
editor/scripting/codegen.py — Transpileur AST normalisé → C.

Reçoit un LuaScript (parser.py) et un CodegenContext (informations de
build) et produit le source C d'un fichier actor_<Name>.c.

Règles de génération :
  - Variables locales top-level  → static <type> <name>; (scope fichier)
  - … sauf dans un prefab poolé, où celles que le script ÉCRIT deviennent un
    champ de g_state_<sym>[], une entrée par instance du pool
  - Variables globales (globals.h) → accès direct par nom
  - self:method(args)  → actor_method(self, args) via RUNTIME_API
  - module.func(args)  → func_c(args) via RUNTIME_API
  - Opérateurs Lua     → opérateurs C (and→&&, or→||, ~=→!=, not→!)
  - Strings d'args API → constantes entières (ANIM_*, SFX_*, BTN_*, TAG_*)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .parser import (
    LuaScript, LuaFunction, LuaLocal,
    StmtCall, StmtAssign, StmtLocalAssign, StmtIf, StmtWhile,
    StmtForNum, StmtReturn, StmtBreak, StmtUnsupported,
    ExprNumber, ExprBool, ExprNil, ExprString, ExprName, ExprUnsupported,
    ExprIndex, ExprIndexAt, ExprTable, ExprInvoke, ExprCall, ExprBinop, ExprUnop,
    array_dims, require_target, DATA_NS,
    assigned_names, sequence_name, wait_call, WAIT_FN, WAIT_UNTIL_FN,
)
# Les volumes du modèle sont des POURCENTAGES ; chaque appel maxmod a sa
# propre échelle, et c'est ici qu'on convertit (cf. models/audio.py).
from core.models.audio import (
    volume_to_effect, volume_to_module, pitch_to_rate, panning_to_hardware,
    volume_to_effect_expr, volume_to_module_expr, pitch_to_rate_expr,
    panning_to_hardware_expr,
)
from .api import (
    RUNTIME_API, EVENT_C_SIGNATURES, KNOWN_EVENTS, ApiFunc,
    KNOWN_SCENE_EVENTS, KNOWN_EVENTS_BY_KIND, scene_event_sig,
    DOMAIN_OBJ_MODE, DOMAIN_DIRECTION, DOMAIN_WIN_REGION,
    DOMAIN_BLEND_MODE, DOMAIN_BLEND_SIDE, DOMAIN_EASE,
    hardware_enum_constant,
    DOMAIN_ANIM, DOMAIN_SFX, DOMAIN_MUSIC, DOMAIN_KEY, DOMAIN_TAG, DOMAIN_SCENE,
    DOMAIN_SOUND_BOX_STATE, DOMAIN_JINGLE_BOX_STATE, DOMAIN_MUSIC_BOX_TRIGGER,
    DOMAIN_CAMERA, camera_constant,
    DOMAIN_TEXT, DOMAIN_FONT, DOMAIN_REGION, DOMAIN_IMAGE, DOMAIN_IMAGE_STATE,
    DOMAIN_PALETTE, DOMAIN_UI_ELEMENT,
    DOMAIN_PREFAB, DOMAIN_ACTOR, DOMAIN_GLOBAL, DOMAIN_CONST, DOMAIN_SEQUENCE,
    anim_constant, sfx_constant, music_constant, key_constant, tag_constant, scene_constant,
    text_constant, font_constant, region_constant, anon_text_key, palette_constant,
    image_constant, image_state_constant, ui_element_constant,
    SCREEN_CONSTANTS,
)
from .checker import check as _lua_check, BuildContext as _BuildContext
from .expr_types import (VEC_CONSTRUCTORS, C_TYPES, C_REF_TYPES,
                         infer_vec_type, infer_ref_type, resolve_prop)


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

# Ce qu'un champ d'état pèse par instance. Tout est aligné sur 4 octets côté
# ARM, donc la somme des champs est la taille de la structure — ce que le build
# annonce pour un prefab poolé (cf. CodeGen._emit_pool_state).
_STATE_BYTES = {"vec2": 8, "vec3": 12}


# ─── Séquences : découpage ────────────────────────────────────────

@dataclass
class _Step:
    """Une tranche de séquence : soit du code, soit une attente."""
    kind:  str          # "body" | WAIT_FN | WAIT_UNTIL_FN
    stmts: list = field(default_factory=list)   # kind == "body"
    arg:   Any = None                            # l'attente : durée ou condition


@dataclass
class _SequencePlan:
    name:    str                # "intro"
    steps:   list               # list[_Step], numérotées 1..N à l'émission
    lifted:  list               # noms des locals qui traversent une attente
    timer:   bool               # au moins un wait(n) → un compteur partagé


def referenced_names(nodes) -> set[str]:
    """Tous les noms LUS ou ÉCRITS dans ces statements/expressions.

    Sert à une seule question : ce `local` est-il encore regardé APRÈS une
    attente ? Si oui il doit survivre, donc vivre dans l'état de la séquence."""
    found: set[str] = set()

    def expr(e):
        if e is None:
            return
        if isinstance(e, ExprName):
            found.add(e.name)
        elif isinstance(e, ExprIndex):
            expr(e.obj)
        elif isinstance(e, ExprIndexAt):
            expr(e.obj); expr(e.index)
        elif isinstance(e, ExprBinop):
            expr(e.left); expr(e.right)
        elif isinstance(e, ExprUnop):
            expr(e.operand)
        elif isinstance(e, ExprCall):
            expr(e.func)
            for a in e.args:
                expr(a)
        elif isinstance(e, ExprInvoke):
            expr(e.obj)
            for a in e.args:
                expr(a)
        elif isinstance(e, ExprTable):
            for it in e.items:
                expr(it)

    def walk(stmts):
        for s in stmts:
            if isinstance(s, StmtCall):
                expr(s.call)
            elif isinstance(s, StmtLocalAssign):
                expr(s.value)
            elif isinstance(s, StmtAssign):
                expr(s.target); expr(s.value)
            elif isinstance(s, StmtIf):
                expr(s.cond); walk(s.then)
                for c, b in s.elseifs:
                    expr(c); walk(b)
                walk(s.else_)
            elif isinstance(s, StmtWhile):
                expr(s.cond); walk(s.body)
            elif isinstance(s, StmtForNum):
                expr(s.start); expr(s.stop); expr(s.step); walk(s.body)
            elif isinstance(s, StmtReturn):
                for v in s.values:
                    expr(v)

    walk(nodes)
    return found



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
    # Prefab poolé : les variables de tête que le script ÉCRIT deviennent un
    # champ de `g_state_<sym>[]`, une entrée par instance (cf. _emit_pool_state).
    # `pool_size` ne sert qu'à CHIFFRER ce que cet état coûte — le C émis, lui,
    # se dimensionne sur `POOL_<SYM>_SIZE` (headers.py), pour qu'un écart avec la
    # boucle de pool de main.c soit impossible.
    is_pooled: bool = False
    pool_size: int = 0
    scene_names: list[str] = field(default_factory=list)  # noms de scènes du projet
    sfx_component_name: Optional[str] = None  # Sfx lié au SoundFxComponent de cet actor (si présent)
    sfx_autoplay: bool = False   # True → SoundFxComponent.trigger == "on_spawn"
    sfx_volumes: dict = field(default_factory=dict)  # {nom Sfx: volume EN %} — converti à l'émission
    music_info: dict = field(default_factory=dict)
    # {nom d'état: rang dans SA boîte}, par famille, et {déclencheur: rang}
    sound_box_states: dict = field(default_factory=dict)
    jingle_box_states: dict = field(default_factory=dict)
    music_box_triggers: dict = field(default_factory=dict)
    text_keys:  list[str] = field(default_factory=list)  # clés de la table de textes (ordre = index C)
    font_names: list[str] = field(default_factory=list)  # polices encodables (ordre = index dans g_fonts)
    palette_names: list[str] = field(default_factory=list)  # catalogue de couleurs (ordre = index dans g_palettes)
    region_names: list[str] = field(default_factory=list)  # emplacements de texte (ordre = index dans g_ui_regions)
    image_names:  list[str] = field(default_factory=list)  # images d'interface (ordre = index dans g_ui_images)
    # TOUS les éléments d'UI, tous types confondus (ordre = index dans la table
    # de visibilité plate, UIELEM_*) — cf. Project.all_elements.
    element_names: list[str] = field(default_factory=list)
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
        # Prefab poolé — état par instance : nom Lua → champ de `<sym>State`.
        # C'est `_state_ref` qui en fait un accès (`_st->fx`), pour que la
        # forme vive à UN endroit. Vide pour un propriétaire unique.
        self._pool_state: dict[str, str] = {}
        self._pool_state_init: str = ""   # « .fx = FX_POP, .fx_t = 0 »
        self.pool_state_bytes: int = 0
        # Séquences — remplis par `_plan_sequences`, avant toute émission.
        self._seq_plans: list = []                 # list[_SequencePlan], ordre source
        self._plan_of: dict[str, _SequencePlan] = {}   # nom de handler → plan
        # (type C, champ, init) de l'état des séquences. Champs de `<sym>State`
        # pour un prefab poolé, statiques de fichier sinon.
        self._state_extra: list[tuple[str, str, str]] = []
        # Actif pendant l'émission d'UNE séquence : ses locals qui traversent
        # une attente, et le champ d'état où ils vivent (cf. _emit_sequence).
        self._local_state: dict[str, str] = {}
        # Le corps en cours d'émission a-t-il touché l'état de l'instance ?
        # C'est ce qui décide de poser `_st` en tête (cf. _close_state_scope).
        self._state_touched: bool = False
        # Tableaux déclarés dans ce script : nom → dimensions. Sert à `#t`, qui
        # est une constante de compilation — la taille fait partie du type, donc
        # elle n'est rangée nulle part à l'exécution.
        self._arrays: dict[str, tuple[int, ...]] = {}
        # Locals vec2/vec3 : nom → type. Rempli au fil de l'émission (comme
        # `_arrays` ci-dessus), pour que `_expr` sache émettre `vec2_add(...)`
        # plutôt que `+` sur un `a + b` dont les deux côtés sont des vecteurs.
        # Cf. scripting/vec_types.py — même règle que checker.py.
        self._vec_types: dict[str, str] = {}
        # Locals qui tiennent une référence : nom → type (cf. expr_types).
        self._ref_types: dict[str, str] = {}
        self.warnings: list[str] = []  # diagnostics non bloquants (ex: behavior manquant/invalide)

    # ── API publique ──────────────────────────────────────────────

    def generate(self, script: LuaScript) -> str:
        """Retourne le source C complet pour ce script."""
        # Le découpage des séquences vient d'abord : il dit quel état déclarer,
        # et `_emit_locals` en a besoin pour le poser au bon endroit (champ de
        # la structure de pool, ou statique de fichier).
        self._plan_sequences(script)
        self._emit_header()
        self._emit_locals(script)
        # Inline des behaviors requis (collectés pendant _emit_locals via StmtLocalAssign)
        self._emit_inlined_behaviors(script)
        # Remise à l'état de départ du slot, pour les prefabs poolés (avant les handlers)
        if self.ctx.is_pooled:
            self._emit_pool_init()
        defined = set()
        for fn in script.functions:
            plan = self._plan_of.get(fn.name)
            if plan is not None:
                self._emit_sequence(plan)
            else:
                self._emit_function(fn)
                defined.add(fn.name)
        # Stubs vides pour les events non définis (évite les erreurs de linker)
        known = self._known_hooks() if self.ctx.is_scene else KNOWN_EVENTS
        for event in known:
            if event not in defined:
                self._emit_stub(event)
        return "\n".join(self._lines) + "\n"

    # ── Séquences ─────────────────────────────────────────────────

    def _plan_sequences(self, script: LuaScript):
        """Découpe chaque séquence à ses attentes, et dit quel état elle demande.

        Rien n'est émis ici : le résultat sert d'abord à DÉCLARER l'état (au bon
        endroit selon que le propriétaire est poolé ou non), et seulement
        ensuite à écrire le `switch`."""
        for fn in script.functions:
            name = sequence_name(fn.name)
            if name is None:
                continue
            steps, buf = [], []
            for stmt in fn.body:
                w = wait_call(stmt)
                if w is None:
                    buf.append(stmt)
                    continue
                if buf:
                    steps.append(_Step("body", stmts=buf))
                    buf = []
                steps.append(_Step(w[0], arg=w[1]))
            if buf or not steps:
                # Une séquence vide garde une tranche : elle démarre et
                # s'arrête, plutôt que de rester sur une étape que rien ne fait
                # avancer.
                steps.append(_Step("body", stmts=buf))

            # Un `local` de la séquence encore regardé après une attente doit
            # survivre : il devient un champ de l'état. Ceux qui vivent et
            # meurent dans leur tranche restent des locals C.
            lifted, plus_tard = [], set()
            for i in range(len(steps) - 1, -1, -1):
                st = steps[i]
                if st.kind == "body":
                    for s in st.stmts:
                        if isinstance(s, StmtLocalAssign) and s.name in plus_tard:
                            if s.name not in lifted:
                                lifted.append(s.name)
                    plus_tard |= referenced_names(st.stmts)
                else:
                    plus_tard |= referenced_names([StmtCall(call=ExprCall(
                        func=ExprName(st.kind), args=[st.arg] if st.arg else []))])
            lifted.reverse()

            plan = _SequencePlan(
                name=name, steps=steps, lifted=lifted,
                timer=any(st.kind == WAIT_FN for st in steps))
            self._seq_plans.append(plan)
            self._plan_of[fn.name] = plan

            # L'état demandé par cette séquence : l'étape, le compteur s'il y a
            # une durée à décompter, et les locals qui traversent.
            self._state_extra.append(("int", f"seq_{name}_step", "0"))
            if plan.timer:
                self._state_extra.append(("int", f"seq_{name}_timer", "0"))
            for loc in lifted:
                self._state_extra.append(("int", f"seq_{name}_{loc}", "0"))

    def _state_ref(self, field: str) -> str:
        """Où vit ce morceau d'état — dans le slot de l'instance pour un prefab
        poolé, dans une statique de fichier pour un propriétaire unique.

        Côté poolé, l'accès passe par `_st`, un pointeur posé en tête de la
        fonction qui en a besoin (cf. `_close_state_scope`). Écrire
        `g_state_Ball[Ball_pool_slot(self)].fx` à chaque site rendait le C
        illisible — 38 caractères de machinerie autour du nom que l'auteur a
        écrit — et laissait gcc recalculer le slot plus souvent que nécessaire
        (`sizeof(Actor)` ne vaut pas une puissance de deux : la soustraction de
        pointeurs coûte une division)."""
        if self.ctx.is_pooled:
            self._state_touched = True
            return f"_st->{field}"
        return f"{self.ctx.actor_sym}_{field}"

    # ── Le pointeur d'état d'un prefab poolé ──────────────────────

    def _open_state_scope(self) -> int:
        """Retient où insérer `_st`, et repart d'un corps qui n'y a pas encore
        touché. À appeler juste après l'accolade ouvrante d'une fonction."""
        self._state_touched = False
        return len(self._lines)

    def _close_state_scope(self, mark: int, receiver: str = "self"):
        """Pose `_st` en tête du corps, s'il y a servi.

        S'il n'a pas servi, ne rien poser : un pointeur déclaré et jamais lu,
        c'est un `-Wunused-variable` à chaque build."""
        if not self._state_touched:
            return
        sym = self.ctx.actor_sym
        self._lines.insert(
            mark,
            "    " * self._indent
            + f"{sym}State* _st = &g_state_{sym}[{sym}_pool_slot({receiver})];")
        self._state_touched = False

    def _emit_sequence_statics(self):
        """L'état des séquences d'un propriétaire NON poolé — une statique par
        champ. Pour un prefab poolé, ces mêmes champs sont déjà entrés dans
        `<sym>State` (cf. _emit_pool_state)."""
        if not self._state_extra or self.ctx.is_pooled:
            return
        sym = self.ctx.actor_sym
        self._w("/* État des séquences — 0 = arrêtée, 1..N = l'étape en cours */")
        for c_type, field, init in self._state_extra:
            self._w(f"static {c_type} {sym}_{field} = {init};")
        self._w("")

    def _emit_sequence_decls(self):
        """Déclarations avancées des tranches : `on_update` les appelle, et il
        peut être écrit avant elles dans le fichier Lua."""
        if not self._seq_plans:
            return
        arg = "void" if self.ctx.is_scene else "Actor* self"
        for plan in self._seq_plans:
            self._w(f"static void {self._sequence_sym(plan)}({arg});")
        self._w("")

    def _sequence_sym(self, plan: _SequencePlan) -> str:
        kind = f"_{self.ctx.hook_kind}" if self.ctx.is_scene else ""
        return f"{self.ctx.actor_sym}{kind}_sequence_{plan.name}"

    def _emit_sequence(self, plan: _SequencePlan):
        """Le `switch` d'une séquence : un `case` par tranche, dans l'ordre de
        la source, et une tranche par frame.

        Pas de boucle autour du `switch` — chaque case rend la main. Une
        séquence à N attentes coûte donc N frames de plus qu'une exécution en
        ligne droite, et ne peut structurellement pas tourner en rond."""
        arg  = "void" if self.ctx.is_scene else "Actor* self"
        # Les locals qui traversent une attente sont lus et écrits dans l'état
        # pour toute la durée de l'émission de cette séquence — y compris leur
        # `local x = …`, qui devient une simple affectation.
        self._local_state = {loc: f"seq_{plan.name}_{loc}" for loc in plan.lifted}
        self._w(f"/* Séquence « {plan.name} » — une tranche par attente, "
                f"dans l'ordre de la source.")
        if plan.lifted:
            self._w(f"   Survivent à l'attente : {', '.join(plan.lifted)}. */")
        else:
            self._w("   Aucune variable ne traverse d'attente. */")
        self._w(f"static void {self._sequence_sym(plan)}({arg}) {{")
        self._indent += 1
        mark = self._open_state_scope()
        step_ref = self._state_ref(f"seq_{plan.name}_step")
        self._w(f"switch ({step_ref}) {{")
        for i, st in enumerate(plan.steps, start=1):
            suivant = i + 1 if i < len(plan.steps) else 0
            fin = "   /* dernière tranche : la séquence s'arrête */" if suivant == 0 else ""
            if st.kind == "body":
                self._w(f"case {i}: {{")
            elif st.kind == WAIT_FN:
                self._w(f"case {i}: {{   /* {WAIT_FN}({self._expr(st.arg)}) */")
            else:
                self._w(f"case {i}: {{   /* {WAIT_UNTIL_FN} */")
            self._indent += 1
            if st.kind == "body":
                self._emit_block(st.stmts)
            elif st.kind == WAIT_FN:
                timer = self._state_ref(f"seq_{plan.name}_timer")
                self._w(f"if (++{timer} < {self._expr(st.arg)}) break;")
                self._w(f"{timer} = 0;")
            else:
                self._w(f"if (!({self._expr(st.arg)})) break;")
            self._w(f"{step_ref} = {suivant};{fin}")
            self._indent -= 1
            self._w("} break;")
        self._w("}")
        self._close_state_scope(mark)
        self._indent -= 1
        self._w("}")
        self._w("")
        self._local_state = {}

    def _emit_sequence_pump(self):
        """Les séquences avancent à la FIN de `on_update`, dans l'ordre de
        déclaration. Un seul endroit, visible dans le C émis, et rien à ajouter
        à la boucle de frame de `main.c` — elle appelle déjà `on_update` pour
        chaque propriétaire. Le test sur l'étape évite l'appel quand la
        séquence est arrêtée."""
        if not self._seq_plans:
            return
        arg = "" if self.ctx.is_scene else "self"
        self._w("/* Séquences — dans l'ordre de déclaration */")
        for plan in self._seq_plans:
            step_ref = self._state_ref(f"seq_{plan.name}_step")
            self._w(f"if ({step_ref}) {self._sequence_sym(plan)}({arg});")

    def _emit_pool_init(self):
        """Génère void SYM_pool_init(Actor* self) — appelée par spawn avant
        on_start. Une seule affectation de structure : elle couvre les tableaux
        et les vecteurs, qu'un champ à la fois ne saurait pas réinitialiser."""
        sym = self.ctx.actor_sym
        self._w(f"void {sym}_pool_init(Actor* self) {{")
        self._indent += 1
        mark = self._open_state_scope()
        if self._pool_state_init:
            # Littéral composé, et non un `static const` de fichier : l'état de
            # départ cite les constantes du script (`.fx = FX_POP`), qui sont
            # des variables C — le C n'accepte pas une variable dans
            # l'initialiseur d'un objet statique, même déclarée `const`.
            self._state_touched = True
            self._w(f"*_st = ({sym}State){{ {self._pool_state_init} }};")
        else:
            self._w("(void)self;")
        self._close_state_scope(mark)
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
                # Le receveur d'un behavior n'est pas forcément nommé `self` :
                # si son corps touche l'état de l'hôte (un homonyme d'une
                # variable de tête), c'est SON premier paramètre qui donne
                # l'instance. Cf. ARCHITECTURE.md pour la limite connue de
                # cette substitution par nom.
                mark = self._open_state_scope()
                self._emit_block(fn.body)
                if fn.params:
                    self._close_state_scope(mark, receiver=fn.params[0])
                self._state_touched = False
                self._indent -= 1
                self._w("}")
                self._w("")

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
        # Constantes d'élément d'UI — index dans la table de visibilité plate,
        # espace SÉPARÉ de REGION_*/IMAGE_* : elle couvre aussi les panels-
        # groupes purs, qui n'y figurent dans aucune des deux autres tables.
        if self.ctx.element_names:
            self._w("")
            self._w("/* Éléments d'interface (visibilité) */")
            for i, name in enumerate(self.ctx.element_names):
                self._w(f"#define {ui_element_constant(name)} {i}")
        self._w("")

    # ── Variables locales top-level (static = scope fichier) ──────

    def _emit_locals(self, script: LuaScript):
        # Pré-enregistrer les require() et les exclure des déclarations C. La
        # FORME est reconnue par `parser.require_target`, où vit déjà celle du
        # tableau — elle était réécrite ici, et une deuxième fois plus bas.
        non_require = []
        for loc in script.locals:
            target = require_target(loc.value)
            if target is None:
                non_require.append(loc)
            else:
                self._required_behaviors[loc.name] = f"beh_{Path(target).stem}"
        # Ce qui change appartient à l'INSTANCE, ce qui ne change pas appartient
        # au PREFAB. Un `local FX_POP = 1` qu'aucune ligne n'assigne est une
        # constante : la recopier dans chaque slot du pool ferait payer seize
        # fois une valeur qui ne bouge jamais, et ferait mentir la mesure du
        # build — qui annoncerait la longueur de l'en-tête du fichier au lieu de
        # l'état. Un acteur de scène n'a qu'une instance : tout y reste partagé.
        if self.ctx.is_pooled:
            written = assigned_names(script)
            state  = [loc for loc in non_require if loc.name in written]
            shared = [loc for loc in non_require if loc.name not in written]
        else:
            state, shared = [], non_require

        if shared:
            self._w("/* Constantes du script — jamais assignées, donc partagées "
                    "par toutes les instances */" if self.ctx.is_pooled
                    else "/* Variables locales à cet acteur */")
            for loc in shared:
                self._emit_shared_local(loc)
            self._w("")
        if state or (self.ctx.is_pooled and self._state_extra):
            self._emit_pool_state(state)
        self._emit_sequence_statics()
        self._emit_sequence_decls()

    def _emit_shared_local(self, loc: LuaLocal):
        """Un local de tête déclaré au scope FICHIER : une seule copie pour
        tout le programme."""
        dims = array_dims(loc.value)
        if dims:
            self._arrays[loc.name] = dims
            self._w(f"static {self._array_decl(loc.name, dims)} = "
                    f"{self._array_init(loc.value, dims)};")
            return
        vt = infer_vec_type(loc.value, self._vec_types) if loc.value is not None else None
        if vt:
            self._vec_types[loc.name] = vt
            self._w(f"static {C_TYPES[vt]} {loc.name} = {self._expr(loc.value)};")
            return
        c_type, init, note = self._local_decl(loc)
        if c_type is None:
            self._w(f"/* {loc.name} : {note} */")
            return
        suffix = f"   /* {note} */" if note else ""
        self._w(f"static {c_type} {self._unused_attr(loc)}{loc.name} = {init};{suffix}")

    def _emit_pool_state(self, locals_: list[LuaLocal]):
        """L'état par instance d'un prefab poolé : une structure par slot du
        pool, un champ par variable de tête que le script écrit.

        Le pool est une plage contiguë de `g_actors[]` dont les bornes sont des
        constantes de build (`POOL_<SYM>_START/SIZE`, émises par headers.py) :
        le slot d'une instance est donc une soustraction de pointeurs, et rien
        n'a besoin d'être rangé dans la struct `Actor`.

        La taille vient du #define et non d'un littéral recalculé ici : c'est la
        même constante que la boucle de pool de `main.c`, un écart entre les deux
        serait un débordement de tableau silencieux."""
        sym      = self.ctx.actor_sym
        struct_t = f"{sym}State"
        fields, inits, per_instance = [], [], 0
        for loc in locals_:
            dims = array_dims(loc.value)
            if dims:
                self._arrays[loc.name] = dims
                count = 1
                for d in dims:
                    count *= d
                fields.append(f"{self._array_decl(loc.name, dims)};")
                inits.append(f".{loc.name} = {self._array_init(loc.value, dims)}")
                per_instance += 4 * count
            else:
                vt = infer_vec_type(loc.value, self._vec_types) if loc.value is not None else None
                if vt:
                    self._vec_types[loc.name] = vt
                    fields.append(f"{C_TYPES[vt]} {loc.name};")
                    inits.append(f".{loc.name} = {self._expr(loc.value)}")
                    per_instance += _STATE_BYTES[vt]
                else:
                    c_type, init, note = self._local_decl(loc)
                    if c_type is None:
                        self._w(f"/* {loc.name} : {note} */")
                        continue
                    fields.append(f"{c_type} {loc.name};")
                    inits.append(f".{loc.name} = {init}")
                    per_instance += 4
            self._pool_state[loc.name] = loc.name

        # L'état des séquences rejoint la même structure : une séquence d'un
        # prefab poolé avance indépendamment dans chaque instance, exactement
        # comme ses variables de tête.
        for c_type, field_name, init in self._state_extra:
            fields.append(f"{c_type} {field_name};")
            inits.append(f".{field_name} = {init}")
            per_instance += 4

        if not fields:
            return
        self.pool_state_bytes = per_instance
        self._pool_state_init = ", ".join(inits)
        total = per_instance * self.ctx.pool_size
        self._w("/* État par instance — un champ par variable de tête que le script")
        self._w(f"   écrit, plus l'étape de chaque séquence. {per_instance} octets × "
                f"{self.ctx.pool_size} instance(s) = {total} octets. */")
        self._w(f"typedef struct {{")
        self._indent += 1
        for f in fields:
            self._w(f)
        self._indent -= 1
        self._w(f"}} {struct_t};")
        self._w(f"static {struct_t} g_state_{sym}[POOL_{sym.upper()}_SIZE];")
        self._w(f"static inline int {sym}_pool_slot(Actor* self) {{ "
                f"return (int)(self - g_actors) - POOL_{sym.upper()}_START; }}")
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
        mark = self._open_state_scope()
        if not self.ctx.is_scene and fn.name == "on_start":
            self._emit_sfx_autoplay()
        self._emit_block(fn.body)
        if fn.name == "on_update":
            self._emit_sequence_pump()
        self._close_state_scope(mark)
        self._indent -= 1
        self._w("}")
        self._w("")

    def _emit_sfx_autoplay(self):
        """Injecte l'appel sfx_play() auto au début de on_start si trigger == 'on_spawn'.

        Le volume vient de la ressource, comme partout ailleurs : il MANQUAIT
        ici, et l'appel à un seul argument n'aurait pas compilé — personne
        n'avait encore posé un SoundFX en « on_spawn » dans un projet."""
        if self.ctx.sfx_autoplay and self.ctx.sfx_component_name:
            name = self.ctx.sfx_component_name
            volume = volume_to_effect(self.ctx.sfx_volumes.get(name, 100))
            self._w(f"sfx_play({sfx_constant(name)}, {volume}, 0);")

    # ── Blocs et statements ───────────────────────────────────────

    def _emit_block(self, stmts: list):
        for s in stmts:
            self._emit_stmt(s)

    def _emit_stmt(self, s):
        if isinstance(s, StmtCall):
            # `sfx.play(...)` posé SEUL ne tient pas sa référence : son canal
            # reste volable par l'effet suivant quand tout est plein (cf.
            # `hold` dans headers.py, ROADMAP v0.8.8). C'est la seule décision
            # de tout le générateur qui dépend de la POSITION de l'appel et non
            # de ce qu'il contient — d'où ce test ici, et pas dans l'émetteur.
            if (isinstance(s.call, ExprCall)
                    and self._call_key(s.call.func) == "sfx.play"):
                self._w(self._emit_sfx_play(s.call.args, hold=False) + ";")
            else:
                self._w(self._call_expr(s.call) + ";")

        elif isinstance(s, StmtAssign):
            prop = resolve_prop(s.target)
            if prop is not None:
                receiver, p = prop
                if p.c_setter is None:
                    # lecture seule — le checker a déjà refusé ; on trace plutôt
                    # que d'émettre du C qui ne compile pas.
                    self.warnings.append(
                        f"{p.lua_name} est en lecture seule — l'assignation est ignorée.")
                    return
                setter, value = self._prop_write(p, s.value)
                c_args = [receiver] if p.self_first else []
                c_args.append(value)
                self._w(f"{setter}({', '.join(c_args)});")
                return
            tgt = self._expr(s.target)
            val = self._expr(s.value)
            self._w(f"{tgt} = {val};")

        elif isinstance(s, StmtLocalAssign):
            # local M = require("behaviors/foo") → enregistre l'alias, pas de
            # déclaration C : le behavior est inliné dans l'en-tête.
            target = require_target(s.value)
            if target is not None:
                self._required_behaviors[s.name] = f"beh_{Path(target).stem}"
                return
            # Une variable de séquence qui traverse une attente est DÉJÀ
            # déclarée, dans l'état : son `local` n'est plus qu'une affectation.
            # Sans ça, le C redéclarerait un homonyme local à la tranche, et la
            # valeur ne survivrait pas à l'attente qui suit.
            lifted = self._local_state.get(s.name)
            if lifted is not None:
                val = self._expr(s.value) if s.value is not None else "0"
                # Le type de la référence se note même quand la variable est
                # HISSÉE dans l'état d'une séquence : c'est le même nom, et
                # `pas:set_volume(…)` doit rester un réglage d'effet après
                # l'attente qui l'a fait monter là.
                rt = infer_ref_type(s.value) if s.value is not None else None
                if rt:
                    self._ref_types[s.name] = rt
                self._w(f"{self._state_ref(lifted)} = {val};")
                return
            dims = array_dims(s.value)
            if dims:
                # Un tableau déclaré DANS un handler est reconstruit à chaque
                # appel, comme n'importe quel `local` de Lua.
                self._arrays[s.name] = dims
                self._w(f"{self._array_decl(s.name, dims)} = "
                        f"{self._array_init(s.value, dims)};")
                return
            vt = infer_vec_type(s.value, self._vec_types) if s.value is not None else None
            if vt:
                self._vec_types[s.name] = vt
                self._w(f"{C_TYPES[vt]} {s.name} = {self._expr(s.value)};")
                return
            val = self._expr(s.value) if s.value is not None else "0"
            # Détecte local var = get_actor("...") → Actor* au lieu de int
            is_actor_ref = (
                s.value is not None
                and isinstance(s.value, ExprCall)
                and isinstance(s.value.func, ExprName)
                and s.value.func.name == "get_actor"
            )
            # Une RÉFÉRENCE rendue par un appel (`sfx.play`) porte le type C du
            # handle, et le nom est retenu : c'est lui qui dira à `_invoke` que
            # `pas:set_volume(80)` est un réglage d'effet et non d'acteur.
            rt = infer_ref_type(s.value) if s.value is not None else None
            if rt:
                self._ref_types[s.name] = rt
            ctype = "Actor*" if is_actor_ref else (C_REF_TYPES[rt] if rt else "int")
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

        elif isinstance(s, StmtUnsupported):
            # Le checker a déjà refusé, et une erreur bloque le build : on
            # n'arrive ici que par le chemin des behaviors, où ses erreurs sont
            # relayées en avertissements. Le trou est alors ÉCRIT dans le C
            # plutôt que laissé invisible — c'est tout ce que ce fichier peut
            # faire d'honnête avec un code qu'il ne sait pas traduire.
            self._w(f"/* non traduit : {s.node} (ligne {s.line}) */")

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
        if isinstance(e, ExprUnsupported):
            # Même chemin que StmtUnsupported ci-dessus : refusé par le checker,
            # atteint seulement depuis un behavior. `0` et le nœud en commentaire
            # valent mieux que l'ancien `__unsupported_Concat`, identifiant C
            # inexistant qui n'échouait qu'au `make`.
            return f"0 /* non traduit : {e.node} (ligne {e.line}) */"
        if isinstance(e, ExprString):
            # String littérale en dehors d'un appel API → chaîne C (rare en v1)
            return f'"{e.value}"'
        if isinstance(e, ExprName):
            # Une variable d'une séquence qui traverse une attente vit dans
            # l'état de cette séquence — et masque un éventuel homonyme de tête,
            # comme un `local` masque en Lua.
            field = self._local_state.get(e.name)
            if field is not None:
                return self._state_ref(field)
            # Prefab poolé : une variable de tête écrite par le script vit dans
            # le slot de CETTE instance, pas au scope fichier.
            field = self._pool_state.get(e.name)
            if field is not None:
                return self._state_ref(field)
            return e.name
        if isinstance(e, ExprIndex):
            # screen.width / screen.height / etc. → littéral C
            if isinstance(e.obj, ExprName) and e.obj.name == "screen":
                val = SCREEN_CONSTANTS.get(e.field)
                if val is not None:
                    return str(val)
            # PROPRIÉTÉ : self.position, camera.bound, other.velocity, scene.size…
            # Un accès pointé se traduit par le GETTER (appel C, ou expression
            # synthétique pour scene.size). Le champ qui suit (`self.position.x`)
            # se compose tout seul sur le résultat, comme en Lua.
            prop = resolve_prop(e)
            if prop is not None:
                receiver, p = prop
                return self._prop_read(receiver, p)
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
            enum_cmp = self._prop_enum_compare(e)
            if enum_cmp is not None:
                return enum_cmp
            lt = infer_vec_type(e.left, self._vec_types)
            rt = infer_vec_type(e.right, self._vec_types)
            vt = lt or rt
            if vt and e.op in ("+", "-", "*"):
                # Pas d'opérateur `+`/`-`/`*` sur les structs en C : ce sont
                # les fonctions vec2_*/vec3_* de actor_api_static.h qui portent
                # l'opération (checker.py a déjà refusé vec2+vec3, vec*vec…).
                left, right = self._expr(e.left), self._expr(e.right)
                if e.op == "*":
                    vecexpr, scalar = (left, right) if lt else (right, left)
                    return f"{vt}_scale({vecexpr}, {scalar})"
                fn = "add" if e.op == "+" else "sub"
                return f"{vt}_{fn}({left}, {right})"
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

    # ── Propriétés à domaine ──────────────────────────────────────
    # `self.obj_mode = "window"`, `blend.mode == "alpha"`, `other.tag == "Ball"`.
    # Le C reste un entier ; ce qui change est ce que l'auteur écrit, et la
    # constante émise (`OBJ_MODE_WINDOW` plutôt que `2`, `TAG_BALL` plutôt
    # qu'un index de scène). La résolution passe par `_DOMAIN_CONSTANT`, la même
    # table que pour un ARGUMENT du même domaine : le domaine décide, pas ce
    # qui le porte.

    def _prop_constant(self, p, name: str) -> str:
        make = _DOMAIN_CONSTANT.get(p.domain)
        return make(self, name) if make else f'"{name}"'

    def _prop_write(self, p, value) -> tuple[str, str]:
        """(fonction C d'écriture, valeur C) pour une assignation de propriété.

        Le nom d'une énumération devient sa constante — et, quand la propriété
        a une porte NOMMÉE distincte (`self.direction`, un vec2 côté calcul mais
        une boussole côté nom), c'est elle qu'on emprunte : `actor_set_dir` prend
        un index 0-8, `actor_set_direction` prend un Vec2. Une propriété, deux
        écritures, deux fonctions — l'état atteint est le même."""
        if p.domain is not None and isinstance(value, ExprString):
            return ((p.c_setter_named or p.c_setter),
                    self._prop_constant(p, value.value))
        return p.c_setter, self._expr(value)

    def _prop_read(self, receiver: str, p, named: bool = False) -> str:
        """Lecture d'une propriété, par sa porte ordinaire ou par sa porte
        nommée quand la comparaison porte sur un nom."""
        if not named and p.getter_expr is not None:
            return p.getter_expr
        fn = (p.c_getter_named or p.c_getter) if named else p.c_getter
        return f"{fn}({receiver})" if p.self_first else f"{fn}()"

    def _prop_enum_compare(self, e) -> Optional[str]:
        """`blend.mode == "alpha"` → `(blend_get_mode() == BLD_MODE_ALPHA)`, et
        `self.direction == "west"` → `(actor_get_dir(self) == DIR_WEST)`.

        Sans ça, la comparaison partirait sur une chaîne C là où le getter rend
        un entier : gcc accepterait le pointeur, et le test serait toujours
        faux. Pire pour `self.direction`, dont le getter ordinaire rend un
        `Vec2` — que le C ne sait pas comparer du tout. La lecture passe donc
        par la même porte que l'écriture."""
        if e.op not in ("==", "!="):
            return None
        for prop_side in (e.left, e.right):
            prop = resolve_prop(prop_side)
            if prop is None or prop[1].domain is None:
                continue
            receiver, p = prop
            other = e.right if prop_side is e.left else e.left
            if not isinstance(other, ExprString):
                continue
            const = self._prop_constant(p, other.value)
            read  = self._prop_read(receiver, p, named=True)
            left  = read  if prop_side is e.left else const
            right = const if prop_side is e.left else read
            return f"({left} {e.op} {right})"
        return None

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
        # Le NOM tel qu'il est écrit sert de clé (type de référence, tables de
        # dispatch) ; ce qui est ÉMIS passe par `_expr`, parce qu'une variable
        # peut vivre ailleurs que sous son nom — hissée dans l'état d'une
        # séquence qui traverse une attente, ou dans le slot d'un prefab poolé.
        # Émettre le nom nu produisait un identifiant que le C ne connaît pas.
        name     = e.obj.name          # "self", "other", "paddle", ...
        receiver = self._expr(e.obj)
        # Les méthodes d'actor sont indexées sous "self:" ; celles d'une
        # référence sous le type qu'elle porte (`sfx:`). Le repli `actor_*`
        # plus bas ne doit surtout pas s'appliquer à une référence : il
        # inventerait un `actor_set_volume(pas, …)` qui ne compile pas.
        ref = self._ref_types.get(name)
        key = f"{ref}:{e.method}" if ref else f"self:{e.method}"
        custom = _INVOKE_CUSTOM.get(key)
        if custom:
            return custom(self, e.args, receiver)
        api = RUNTIME_API.get(key)
        if api is None:
            if ref:
                return f"/* {name}:{e.method}() : inconnu sur une référence {ref} */"
            args = ", ".join(self._expr(a) for a in e.args)
            return f"actor_{e.method}({receiver}, {args})"
        return self._emit_api_call(api, e.args, receiver=receiver)

    def _call(self, e: ExprCall) -> str:
        """func(args) ou module.func(args)"""
        key = self._call_key(e.func)

        if key in VEC_CONSTRUCTORS:
            # vec2(x, y) / vec3(x, y, z) / rect(x, y, w, h) → littéral composé
            # C, pas un appel : aucune fonction `vec2`/`rect` n'existe côté runtime.
            args = ", ".join(self._expr(a) for a in e.args)
            return f"({C_TYPES[key]}){{{args}}}"

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
        volume = volume_to_effect(self.ctx.sfx_volumes.get(name, 100))
        return f"sfx_play({sfx_constant(name)}, {volume}, 0)"

    def _emit_destroy(self, args: list, receiver: str) -> str:
        """self:destroy() → appelle on_destroy() puis désactive l'actor."""
        sym = self.ctx.actor_sym
        return f"{sym}_on_destroy({receiver}); actor_destroy_internal({receiver})"

    def _emit_ui_element_show(self, args: list, receiver: str) -> str:
        """self:show() → ui_element_show(idx, 1). Un seul point d'entrée
        runtime pour show ET hide (cf. `_emit_ui_element_hide`), comme
        `ui_image_show`/`layer_show` avant lui — la syntaxe change côté
        script, pas la forme côté C."""
        return f"ui_element_show({receiver}, 1)"

    def _emit_ui_element_hide(self, args: list, receiver: str) -> str:
        """self:hide() → ui_element_show(idx, 0). Cache tout le sous-arbre
        sans toucher aux enfants : la visibilité effective remonte la chaîne
        des parents au runtime, même règle que `UILayout.is_visible` côté
        éditeur."""
        return f"ui_element_show({receiver}, 0)"

    def _emit_sfx_play(self, args: list, hold: bool = True) -> str:
        """sfx.play("Name") → sfx_play(SFX_NAME, volume, hold).

        Volume lu depuis la ressource Sfx. `hold` dit si l'appelant garde la
        référence : vrai quand l'appel est une VALEUR (`local h = sfx.play…`),
        faux quand il est posé seul — c'est `_emit_stmt` qui le sait."""
        if not args or not isinstance(args[0], ExprString):
            return "/* sfx.play() : argument invalide */"
        name   = args[0].value
        volume = volume_to_effect(self.ctx.sfx_volumes.get(name, 100))
        return f"sfx_play({sfx_constant(name)}, {volume}, {1 if hold else 0})"

    def _percent_arg(self, args: list, fold, to_expr, default: int = 100) -> str:
        """Un pourcentage écrit DANS l'appel → la graduation du registre visé.

        Plié au build quand c'est un littéral — le C reste lisible et l'arrondi
        est exact — et converti à l'exécution sinon, parce qu'un niveau peut
        venir d'une variable (`global.get("Volume")`). Les deux formes de
        conversion vivent côte à côte dans `models/audio.py`, pour qu'aucune ne
        dérive de l'autre.
        """
        if not args:
            return str(fold(default))
        a = args[0]
        # `-50` est un moins UNAIRE sur un littéral, pas un littéral négatif :
        # sans ce cas, le seul panning qu'on écrit vraiment (« à gauche »)
        # partirait en arithmétique C au lieu d'être plié.
        if isinstance(a, ExprUnop) and a.op == "-" and isinstance(a.operand, ExprNumber):
            return str(fold(-int(a.operand.value)))
        if isinstance(a, ExprNumber):
            return str(fold(int(a.value)))
        return to_expr(self._expr(a))

    def _emit_sfx_set_volume(self, args: list, receiver: str) -> str:
        return (f"sfx_set_volume({receiver}, "
                f"{self._percent_arg(args, volume_to_effect, volume_to_effect_expr)})")

    def _emit_sfx_set_pitch(self, args: list, receiver: str) -> str:
        return (f"sfx_set_pitch({receiver}, "
                f"{self._percent_arg(args, pitch_to_rate, pitch_to_rate_expr)})")

    def _emit_sfx_set_panning(self, args: list, receiver: str) -> str:
        """Le panning s'écrit −100..+100 et le registre prend 0–255 : ce n'est
        pas une mise à l'échelle mais un décalage autour du centre."""
        return (f"sfx_set_panning({receiver}, "
                f"{self._percent_arg(args, panning_to_hardware, panning_to_hardware_expr, 0)})")

    def _emit_music_set_volume(self, args: list) -> str:
        return (f"music_set_volume("
                f"{self._percent_arg(args, volume_to_module, volume_to_module_expr)})")

    def _emit_sound_box_set_volume(self, args: list) -> str:
        return (f"sfx_set_effects_volume("
                f"{self._percent_arg(args, volume_to_module, volume_to_module_expr)})")

    def _emit_jingle_box_set_volume(self, args: list) -> str:
        return (f"music_jingle_volume("
                f"{self._percent_arg(args, volume_to_module, volume_to_module_expr)})")

    def _emit_music_play(self, args: list) -> str:
        """music.play("Name") → music_play(MUSIC_NAME, loop, volume) — loop/volume lus depuis la ressource Music."""
        if not args or not isinstance(args[0], ExprString):
            return "/* music.play() : argument invalide */"
        name = args[0].value
        loop, volume = self.ctx.music_info.get(name, (True, 100))
        return (f"music_play({music_constant(name)}, {1 if loop else 0}, "
                f"{volume_to_module(volume)})")

    def _emit_music_transition(self, args: list, c_func: str, extra: str = "") -> str:
        """Les deux transitions se traduisent pareil : loop et volume viennent
        de la RESSOURCE, comme pour `music.play` — un fondu ne change pas ce
        qu'est la piste d'arrivée, seulement la façon d'y aller."""
        if not args or not isinstance(args[0], ExprString):
            return f"/* {c_func}() : argument invalide */"
        name = args[0].value
        loop, volume = self.ctx.music_info.get(name, (True, 100))
        tail = f", {extra}" if extra else ""
        return (f"{c_func}({music_constant(name)}, {1 if loop else 0}, "
                f"{volume_to_module(volume)}{tail})")

    def _emit_box_set_state(self, kind: str, index: dict, args: list) -> str:
        """`<boîte>.set_state("sable")` → `<boîte>_set_state(1)`.

        L'index est le RANG de l'état dans SA boîte : chaque boîte a son propre
        espace de noms, donc deux boîtes peuvent porter « sable » sans que
        l'appel devienne ambigu — c'est l'appel qui nomme la boîte.
        """
        if not args or not isinstance(args[0], ExprString):
            return f"/* {kind}.set_state() : argument invalide */"
        name = args[0].value
        idx = index.get(name, -1)
        if idx < 0:
            return f'/* {kind}.set_state("{name}") : état inconnu */'
        return f"{kind}_set_state({idx})"

    def _emit_sound_box_set_state(self, args: list) -> str:
        return self._emit_box_set_state("sound_box", self.ctx.sound_box_states, args)

    def _emit_jingle_box_set_state(self, args: list) -> str:
        return self._emit_box_set_state("jingle_box", self.ctx.jingle_box_states, args)

    def _emit_sound_trigger(self, args: list) -> str:
        """music_box.trigger("combat_start") → music_box_trigger(0)."""
        if not args or not isinstance(args[0], ExprString):
            return "/* music_box.trigger() : argument invalide */"
        name = args[0].value
        idx = self.ctx.music_box_triggers.get(name, -1)
        if idx < 0:
            return f'/* music_box.trigger("{name}") : aucune arête sur ce déclencheur */'
        return f"music_box_trigger({idx})"

    def _emit_music_jingle(self, args: list) -> str:
        """music.jingle("Fanfare") → music_jingle(MUSIC_X, volume).

        `mmSetJingleVolume` partage l'échelle 0–1024 de `mmSetModuleVolume` :
        c'est bien la conversion « module », pas celle d'un effet.
        """
        if not args or not isinstance(args[0], ExprString):
            return "/* music.jingle() : argument invalide */"
        name = args[0].value
        _loop, volume = self.ctx.music_info.get(name, (True, 100))
        return f"music_jingle({music_constant(name)}, {volume_to_module(volume)})"

    def _emit_music_fade_to(self, args: list) -> str:
        frames = self._expr(args[1]) if len(args) > 1 else "30"
        return self._emit_music_transition(args, "music_fade_to", frames)

    def _emit_music_cut_to(self, args: list) -> str:
        return self._emit_music_transition(args, "music_cut_to")

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

    def _emit_ui_get(self, args: list) -> str:
        """ui.get("alerte") → UIELEM_ALERTE — résolu à la compilation, comme
        get_actor. Pas de fonction runtime : l'index est la même constante
        que celle émise en tête de fichier pour `element_names`."""
        if not args or not isinstance(args[0], ExprString):
            return "/* ui.get() : argument invalide */"
        return ui_element_constant(args[0].value)

    def _sequence_step_arg(self, args: list, call: str) -> Optional[str]:
        """L'accès à l'étape de la séquence nommée, ou None si le nom n'est pas
        un littéral (le checker l'a déjà refusé)."""
        if not args or not isinstance(args[0], ExprString):
            self.warnings.append(f"{call} : nom de séquence non littéral.")
            return None
        return self._state_ref(f"seq_{args[0].value}_step")

    def _emit_sequence_start(self, args: list) -> str:
        """`sequence.start("intro")` → l'étape passe à 1. Aucune fonction C :
        démarrer une séquence, c'est écrire 1 dans son entier d'état."""
        ref = self._sequence_step_arg(args, "sequence.start")
        return f"{ref} = 1" if ref else "0"

    def _emit_sequence_stop(self, args: list) -> str:
        """0 = arrêtée. Une séquence relancée repart de sa première tranche —
        l'étape est la seule chose qui dise où elle en était."""
        ref = self._sequence_step_arg(args, "sequence.stop")
        return f"{ref} = 0" if ref else "0"

    def _emit_sequence_running(self, args: list) -> str:
        ref = self._sequence_step_arg(args, "sequence.running")
        return f"({ref} != 0)" if ref else "0"

    def _emit_actor_spawn(self, args: list) -> str:
        """actor.spawn("PrefabName", pos) → spawn_PrefabName(pos.x, pos.y)"""
        if len(args) < 2 or not isinstance(args[0], ExprString):
            return "/* actor.spawn : nom de prefab non littéral */"
        prefab_name = args[0].value
        sym = prefab_name.replace(" ", "_")
        pos = args[1]
        # vec2(x, y) littéral → ses deux composantes une fois, pas d'expression
        # dupliquée ; toute autre expression vec2 (variable, get_position()…)
        # → composantes déréférencées, comme le ferait l'appelant.
        if (isinstance(pos, ExprCall)
                and self._call_key(pos.func) == "vec2"
                and len(pos.args) == 2):
            px, py = self._expr(pos.args[0]), self._expr(pos.args[1])
        else:
            e = self._expr(pos)
            px, py = f"({e}).x", f"({e}).y"
        return f"spawn_{sym}({px}, {py})"

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
        """Stub vide pour un event non défini dans le script.

        Sauf `on_update` quand le script déclare des séquences : c'est là
        qu'elles avancent, et un script peut très bien n'écrire QUE des
        séquences — le stub porte alors le pompage."""
        if event_name == "on_update" and self._seq_plans:
            if self.ctx.is_scene:
                sig = scene_event_sig(self.ctx.actor_sym, "on_update", self.ctx.hook_kind)
            else:
                sig = EVENT_C_SIGNATURES["on_update"].format(prefix=self.ctx.actor_sym)
            self._w(sig + " {")
            self._indent += 1
            mark = self._open_state_scope()
            self._emit_sequence_pump()
            self._close_state_scope(mark)
            self._indent -= 1
            self._w("}")
            self._w("")
            return
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
    # Les trois réglages d'une référence d'effet qui portent un POURCENTAGE :
    # ils passent par un émetteur parce que la valeur change de graduation
    # entre le script et le registre. `:stop()` et `:playing()` n'en ont pas
    # besoin — ils se traduisent terme à terme depuis le catalogue.
    "sfx:set_volume":  CodeGen._emit_sfx_set_volume,
    "sfx:set_pitch":   CodeGen._emit_sfx_set_pitch,
    "sfx:set_panning": CodeGen._emit_sfx_set_panning,
    "self:destroy":  CodeGen._emit_destroy,
    "self:play_sfx": CodeGen._emit_play_sfx,
    "self:show":     CodeGen._emit_ui_element_show,
    "self:hide":     CodeGen._emit_ui_element_hide,
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
    DOMAIN_EASE:       lambda g, name: hardware_enum_constant(DOMAIN_EASE, name),
}

# Domaines SANS constante générique : leur argument est résolu par un émetteur
# dédié de `_CALL_CUSTOM` (nom de prefab poolé, actor résolu à la compilation,
# variable C nommée) et n'atteint donc jamais `_resolve_arg`. Les déclarer est
# ce qui distingue « traité ailleurs » de « oublié ».
_DOMAIN_EMITTED_ELSEWHERE: frozenset = frozenset({
    # Résolus par les émetteurs des trois boîtes : l'index est le RANG de
    # l'état dans sa boîte, pas une constante par nom.
    DOMAIN_SOUND_BOX_STATE, DOMAIN_JINGLE_BOX_STATE, DOMAIN_MUSIC_BOX_TRIGGER,
    DOMAIN_PREFAB, DOMAIN_ACTOR, DOMAIN_GLOBAL, DOMAIN_CONST,
    # Une séquence n'a pas de constante C : son nom désigne une variable
    # d'état, que `_emit_sequence_start/stop/running` écrit ou teste.
    DOMAIN_SEQUENCE,
    # L'état d'une image se résout avec l'image (`IMGST_{image}_{état}`), donc
    # à partir de DEUX arguments — cf. `_emit_ui_image_set`.
    DOMAIN_IMAGE_STATE,
    # ui.get("nom") résout directement en UIELEM_<NOM>, comme get_actor résout
    # DOMAIN_ACTOR — cf. `_emit_ui_get`.
    DOMAIN_UI_ELEMENT,
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
    "sequence.start":   CodeGen._emit_sequence_start,
    "sequence.stop":    CodeGen._emit_sequence_stop,
    "sequence.running": CodeGen._emit_sequence_running,
    "sfx.play":    CodeGen._emit_sfx_play,
    "music.play":    CodeGen._emit_music_play,
    "music.set_volume":      CodeGen._emit_music_set_volume,
    "sound_box.set_volume":  CodeGen._emit_sound_box_set_volume,
    "jingle_box.set_volume": CodeGen._emit_jingle_box_set_volume,
    "sound_box.set_state":  CodeGen._emit_sound_box_set_state,
    "jingle_box.set_state": CodeGen._emit_jingle_box_set_state,
    "music_box.trigger":    CodeGen._emit_sound_trigger,
    "music.jingle":  CodeGen._emit_music_jingle,
    "music.fade_to": CodeGen._emit_music_fade_to,
    "music.cut_to":  CodeGen._emit_music_cut_to,
    "ui.image_set": CodeGen._emit_ui_image_set,
    "ui.get":       CodeGen._emit_ui_get,
}


# ─── Point d'entrée public ────────────────────────────────────────

def generate(script: LuaScript, ctx: CodegenContext) -> tuple[str, list[str], int]:
    """Retourne (code C, warnings, octets d'état par instance).

    `warnings` couvre les behaviors requis manquants/invalides, non bloquants
    mais à faire remonter à l'utilisateur. Le troisième terme est ce que
    l'état de ce script coûte dans UNE instance d'un prefab poolé — 0 partout
    ailleurs, un acteur de scène n'ayant qu'une instance et rangeant tout au
    scope fichier. C'est le chiffre que le build annonce."""
    gen = CodeGen(ctx)
    code = gen.generate(script)
    return code, gen.warnings, gen.pool_state_bytes
