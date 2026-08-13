"""
editor/scripting/parser.py — Parse un script Lua et retourne un AST normalisé.

On utilise luaparser (luaparser.ast) pour obtenir l'AST brut, puis on
l'enveloppe dans nos propres noeuds (ScriptAST) pour isoler le reste
du pipeline de la lib externe. Si luaparser change d'API, seul ce
fichier doit changer.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


# ─── Import luaparser ──────────────────────────────────────────────
try:
    from luaparser import ast as _lua_ast
    from luaparser import astnodes as _lua_nodes
    _LUAPARSER_OK = True
except ImportError:
    _LUAPARSER_OK = False


# ─── Noeuds AST normalisés ─────────────────────────────────────────
# On ne ré-exporte pas les noeuds luaparser ; les autres modules
# ne dépendent que de ces classes.

@dataclass
class LuaScript:
    """Racine : liste de déclarations top-level."""
    functions:  list[LuaFunction] = field(default_factory=list)   # handlers d'event
    locals:     list[LuaLocal]    = field(default_factory=list)    # local x = val
    globals_w:  list[str]         = field(default_factory=list)    # noms des vars globales écrites


@dataclass
class LuaFunction:
    name:   str                           # "on_start", "on_collide"…
    params: list[str]                     # ["other"] pour on_collide, [] pour on_start
    body:   list[Any]                     # liste de noeuds Statement


@dataclass
class LuaLocal:
    name:    str
    value:   Any      # noeud Expr (peut être None si pas initialisé)
    # Type déclaré dans la table `exports` ("int", "string", "actor_ref"…) —
    # None pour un vrai `local`, dont le type C est alors déduit de la valeur.
    # Cf. scripting/exports_parser.KNOWN_TYPES et codegen._local_decl.
    export_type: Optional[str] = None


# ── Statements ────────────────────────────────────────────────────

@dataclass
class StmtCall:
    """Appel de fonction / méthode."""
    call: Any   # noeud Expr (ExprInvoke, ExprCall…)


@dataclass
class StmtAssign:
    target: Any   # ExprName ou ExprIndex
    value:  Any


@dataclass
class StmtLocalAssign:
    name:  str
    value: Any


@dataclass
class StmtIf:
    cond:     Any
    then:     list[Any]
    elseifs:  list[tuple[Any, list[Any]]] = field(default_factory=list)
    else_:    list[Any]                   = field(default_factory=list)


@dataclass
class StmtWhile:
    cond: Any
    body: list[Any]


@dataclass
class StmtReturn:
    values: list[Any]


@dataclass
class StmtForNum:
    var:   str
    start: Any
    stop:  Any
    step:  Any          # peut être None (défaut 1)
    body:  list[Any]


@dataclass
class StmtBreak:
    pass


# ── Expressions ───────────────────────────────────────────────────

@dataclass
class ExprNumber:
    value: int


@dataclass
class ExprBool:
    value: bool


@dataclass
class ExprNil:
    pass


@dataclass
class ExprString:
    value: str


@dataclass
class ExprName:
    name: str


@dataclass
class ExprIndex:
    """module.champ — notation POINTÉE uniquement.

    L'indexation par crochets a son propre noeud (`ExprIndexAt`) : les deux
    s'écrivent pareil en Lua mais ne veulent pas dire la même chose ici. Un
    champ est un NOM connu à l'écriture (`screen.width`, `data.Objets`), un
    index est une EXPRESSION calculée."""
    obj:   Any
    field: str


@dataclass
class ExprIndexAt:
    """t[i] — indexation par une expression, notation CROCHETS.

    Deux niveaux imbriqués pour un tableau à deux dimensions : `g[y][x]` est
    `ExprIndexAt(ExprIndexAt(g, y), x)`, exactement comme le C qu'il produit."""
    obj:   Any
    index: Any


@dataclass
class ExprTable:
    """{1, 2, 3} — constructeur de tableau.

    `items` porte des ExprTable quand le tableau est à deux dimensions
    (`{{1,2},{3,4}}`). `has_keys` retient qu'une entrée était NOMMÉE
    (`{a = 1}`) : c'est un enregistrement et non un tableau, donc une erreur —
    mais elle se dit dans le checker, pas ici. Le parser décrit ce qui est
    écrit, il ne juge pas."""
    items:    list[Any] = field(default_factory=list)
    has_keys: bool      = False


@dataclass
class ExprInvoke:
    """self:method(args)"""
    obj:    Any          # ExprName("self") en pratique
    method: str
    args:   list[Any]


@dataclass
class ExprCall:
    """func(args) ou module.func(args)"""
    func: Any            # ExprName ou ExprIndex
    args: list[Any]


@dataclass
class ExprBinop:
    op:    str           # "+", "-", "*", "/", "%", "==", "~=", "<", "<=", ">", ">=", "and", "or"
    left:  Any
    right: Any


@dataclass
class ExprUnop:
    op:    str           # "-", "not"
    operand: Any


# ─── Erreur de parse ───────────────────────────────────────────────

class LuaParseError(Exception):
    pass


# ─── Convertisseur AST luaparser → nos noeuds ─────────────────────

class _Converter:
    """Traverse l'AST luaparser et produit nos noeuds."""

    def convert_chunk(self, node) -> LuaScript:
        block = node.body
        functions = []
        locals_   = []
        globals_w = set()

        for stmt in block.body:
            t = type(stmt).__name__
            if t == "Function":
                fn = self._func(stmt)
                functions.append(fn)
                # repérer les writes sur variables non-locales dans le corps
                self._collect_globals(fn.body, set(fn.params), globals_w)
            elif t == "LocalAssign":
                for tgt, val in zip(stmt.targets, stmt.values or [None]*len(stmt.targets)):
                    locals_.append(LuaLocal(
                        name  = tgt.id,
                        value = self._expr(val) if val is not None else None,
                    ))
            elif t == "Assign":
                # exports = { key = { default=N, ... }, ... }  → variables C statiques
                targets = stmt.targets if hasattr(stmt, "targets") else []
                values  = stmt.values  if hasattr(stmt, "values")  else []
                if (targets and getattr(targets[0], "id", None) == "exports"
                        and values and type(values[0]).__name__ == "Table"):
                    for field_node in values[0].fields:
                        key = getattr(field_node.key, "id", None)
                        if key is None:
                            continue
                        # chercher default ET type dans la sous-table : le type
                        # déclaré pilote le type C émis (une string exportée ne
                        # doit pas devenir un `int`), cf. codegen._local_decl.
                        default_val = None
                        decl_type   = None
                        if type(field_node.value).__name__ == "Table":
                            for sub in field_node.value.fields:
                                sub_key = getattr(sub.key, "id", None)
                                if sub_key == "default" and sub.value is not None:
                                    default_val = self._expr(sub.value)
                                elif sub_key == "type" and sub.value is not None:
                                    typ_expr = self._expr(sub.value)
                                    if isinstance(typ_expr, ExprString):
                                        decl_type = typ_expr.value
                        locals_.append(LuaLocal(name=key, value=default_val,
                                                export_type=decl_type))
            # On ignore les autres statements top-level.

        return LuaScript(
            functions = functions,
            locals    = locals_,
            globals_w = sorted(globals_w),
        )

    def _func(self, node) -> LuaFunction:
        if hasattr(node.name, "id"):
            name = node.name.id                                    # simple: on_update
        elif hasattr(node.name, "idx") and node.name.idx is not None:
            name = f"{node.name.value.id}.{node.name.idx.id}"     # M.update
        else:
            name = str(node.name)
        params = [a.id for a in (node.args or [])]
        body   = self._block(node.body, set(params))
        return LuaFunction(name=name, params=params, body=body)

    def _block(self, block, local_scope: set[str]) -> list:
        stmts = []
        for s in (block.body if block else []):
            st = self._stmt(s, local_scope)
            if st is not None:
                stmts.append(st)
        return stmts

    def _stmt(self, node, local_scope: set[str]):
        t = type(node).__name__
        match t:
            case "Assign":
                tgt = self._expr(node.targets[0])
                val = self._expr(node.values[0])
                return StmtAssign(target=tgt, value=val)
            case "LocalAssign":
                name = node.targets[0].id
                val  = self._expr(node.values[0]) if node.values else None
                local_scope.add(name)
                return StmtLocalAssign(name=name, value=val)
            case "Call":
                return StmtCall(call=self._expr_call(node))
            case "Invoke":
                return StmtCall(call=self._expr_invoke(node))
            case "If":
                return self._if(node, local_scope)
            case "While":
                return StmtWhile(
                    cond = self._expr(node.test),
                    body = self._block(node.body, set(local_scope)),
                )
            case "Fornum":
                # luaparser expose EXACTEMENT (target, start, stop, step, body).
                # Ces champs étaient lus décalés d'un cran — `start` pris pour la
                # variable, `stop` pour la borne de départ, `step` pour la borne
                # d'arrivée, et le pas jeté. `for i = 1, 10, 2` produisait donc
                # `for (int i = 10; i <= 2; i += 1)` : un corps de boucle qui ne
                # s'exécute jamais, sans une erreur de checker ni un
                # avertissement gcc pour le dire.
                var = getattr(node.target, "id", "i")
                inner = set(local_scope)
                inner.add(var)
                # Pas omis : luaparser ne pose pas None mais l'ENTIER Python 1,
                # que `_expr` ne sait pas lire (il attend un noeud) et traduisait
                # en `__unsupported_int`.
                raw_step = node.step
                if raw_step is None:
                    step = None
                elif isinstance(raw_step, int):
                    step = ExprNumber(raw_step)
                else:
                    step = self._expr(raw_step)
                return StmtForNum(
                    var   = var,
                    start = self._expr(node.start),
                    stop  = self._expr(node.stop),
                    step  = step,
                    body  = self._block(node.body, inner),
                )
            case "Return":
                vals = [self._expr(v) for v in (node.values or [])]
                return StmtReturn(values=vals)
            case "Break":
                return StmtBreak()
            case _:
                return None   # noeud non géré (silencieux en v1)

    def _if(self, node, local_scope) -> StmtIf:
        then = self._block(node.body, set(local_scope))
        elseifs = []
        else_ = []
        cur = node.orelse
        while cur:
            if type(cur).__name__ == "ElseIf":
                elseifs.append((
                    self._expr(cur.test),
                    self._block(cur.body, set(local_scope)),
                ))
                cur = cur.orelse
            else:
                else_ = self._block(cur, set(local_scope))
                break
        return StmtIf(
            cond    = self._expr(node.test),
            then    = then,
            elseifs = elseifs,
            else_   = else_,
        )

    def _expr(self, node) -> Any:
        if node is None:
            return ExprNil()
        t = type(node).__name__
        match t:
            case "Number":
                return ExprNumber(int(node.n))
            case "TrueExpr":
                return ExprBool(True)
            case "FalseExpr":
                return ExprBool(False)
            case "Nil":
                return ExprNil()
            case "String":
                return ExprString(node.raw)
            case "Name":
                return ExprName(node.id)
            case "Index":
                obj = self._expr(node.value)
                # La NOTATION décide, pas la forme de l'index. Lue de `hasattr
                # (node.idx, "id")`, elle rendait `t[i]` indiscernable de `t.i`
                # (le C émis lisait un champ) et `t[1]` indiscernable de rien du
                # tout (le repr Python du noeud partait dans le C).
                if node.notation == _lua_nodes.IndexNotation.SQUARE:
                    return ExprIndexAt(obj=obj, index=self._expr(node.idx))
                field = node.idx.id if hasattr(node.idx, "id") else str(node.idx)
                return ExprIndex(obj=obj, field=field)
            case "Table":
                items = [self._expr(f.value) for f in (node.fields or [])]
                return ExprTable(
                    items    = items,
                    has_keys = any(f.key is not None for f in (node.fields or [])),
                )
            case "Invoke":
                return self._expr_invoke(node)
            case "Call":
                return self._expr_call(node)
            # Noms EXACTS de luaparser — `ULNotOp` et `ULengthOP` (capitale
            # finale comprise), pas `NotOp`/`LenOp`. Écrits de mémoire, ils ne
            # matchaient rien : `not x` retombait sur la branche binaire et
            # levait « 'ULNotOp' object has no attribute 'left' », un message
            # qui ne dit ni le nom de l'opérateur ni la ligne fautive.
            case "UMinusOp" | "ULNotOp" | "ULengthOP" | "UBNotOp":
                op = {"UMinusOp": "-", "ULNotOp": "not",
                      "ULengthOP": "#", "UBNotOp": "~"}.get(t, t)
                return ExprUnop(op=op, operand=self._expr(node.operand))
            case n if n.endswith("Op"):
                return self._binop(node, t)
            case _:
                return ExprName(f"__unsupported_{t}")

    def _expr_invoke(self, node) -> ExprInvoke:
        obj    = self._expr(node.source)
        method = node.func.id if hasattr(node.func, "id") else str(node.func)
        args   = [self._expr(a) for a in (node.args or [])]
        return ExprInvoke(obj=obj, method=method, args=args)

    def _expr_call(self, node) -> ExprCall:
        func = self._expr(node.func)
        args = [self._expr(a) for a in (node.args or [])]
        return ExprCall(func=func, args=args)

    _BINOP_MAP = {
        "AddOp": "+", "SubOp": "-", "MultOp": "*", "FloatDivOp": "/",
        "ModOp": "%", "EqOp": "==", "EqToOp": "==", "NotEqOp": "!=", "NotEqToOp": "!=", "LessThanOp": "<",
        "GreaterThanOp": ">", "LessOrEqThanOp": "<=", "GreaterOrEqThanOp": ">=",
        "AndLoOp": "&&", "OrLoOp": "||",
    }

    def _binop(self, node, t: str) -> ExprBinop:
        op = self._BINOP_MAP.get(t, t)
        return ExprBinop(op=op, left=self._expr(node.left), right=self._expr(node.right))

    def _collect_globals(self, stmts: list, local_names: set[str], out: set[str]):
        """Collecte les noms écrits (Assign) qui ne sont pas dans local_names,
        et les noms passés à global.set("name", ...) ."""
        # Étendue locale : commence par les noms connus, puis accumule les déclarations
        locals_here = set(local_names)
        for s in stmts:
            if isinstance(s, StmtLocalAssign):
                # Une déclaration locale ne génère pas de global et l'exclut des assigns suivants
                locals_here.add(s.name)
            elif isinstance(s, StmtAssign) and isinstance(s.target, ExprName):
                if s.target.name not in locals_here:
                    out.add(s.target.name)
            elif isinstance(s, StmtCall):
                # global.set("name", value) → déclarer "name" dans globals.h
                call = s.call
                if (isinstance(call, ExprCall)
                        and isinstance(call.func, ExprIndex)
                        and isinstance(call.func.obj, ExprName)
                        and call.func.obj.name == "global"
                        and call.func.field == "set"
                        and call.args
                        and isinstance(call.args[0], ExprString)):
                    out.add(call.args[0].value)
            elif isinstance(s, StmtIf):
                self._collect_globals(s.then, locals_here, out)
                for _, b in s.elseifs:
                    self._collect_globals(b, locals_here, out)
                self._collect_globals(s.else_, locals_here, out)
            elif isinstance(s, StmtWhile):
                self._collect_globals(s.body, locals_here, out)
            elif isinstance(s, StmtForNum):
                # La variable de boucle est LOCALE à la boucle : lui affecter
                # une valeur dans le corps ne déclare pas une globale du projet.
                self._collect_globals(s.body, locals_here | {s.var}, out)


# ─── Déclaration d'un tableau ─────────────────────────────────────
# Deux façons de déclarer, parce que ce sont deux besoins : `{1, 2, 4, 8}`
# donne le CONTENU et en déduit la taille, `array(20, 12)` donne la TAILLE et
# remplit de zéros. La reconnaissance vit ici, avec la forme d'AST qu'elle lit,
# et le checker comme le codegen l'appellent — ils ont chacun besoin des mêmes
# dimensions, pour en faire deux choses différentes.

ARRAY_CTOR = "array"

# L'espace de noms des tables AUTHORÉES du projet : `data.Objets[i].prix`.
# Un nom réservé plutôt qu'un nom global par table — sans lui, une table
# nommée `score` masquerait un `local score` du script, et l'auteur n'aurait
# aucun moyen de savoir lequel des deux il lit.
DATA_NS = "data"


def array_dims(expr) -> Optional[tuple[int, ...]]:
    """Dimensions déclarées par cette expression d'initialisation, ou None si
    ce n'en est pas une (ou si sa forme est fautive — c'est alors au checker de
    dire laquelle, avec les mots qui vont bien).

    L'ORDRE DES ARGUMENTS EST L'ORDRE DES INDEX : `array(20, 12)` se lit
    `t[1..20][1..12]` et devient `int t[20][12]`. Aucune notion de largeur, de
    hauteur, de ligne ni de colonne — la déclaration montre déjà l'ordre."""
    if (isinstance(expr, ExprCall)
            and isinstance(expr.func, ExprName)
            and expr.func.name == ARRAY_CTOR):
        dims = []
        for a in expr.args:
            if not isinstance(a, ExprNumber) or a.value <= 0:
                return None
            dims.append(a.value)
        return tuple(dims) if 1 <= len(dims) <= 2 else None

    if isinstance(expr, ExprTable):
        if expr.has_keys or not expr.items:
            return None
        rows = [it for it in expr.items if isinstance(it, ExprTable)]
        if not rows:
            return (len(expr.items),)
        if len(rows) != len(expr.items):
            return None                       # mélange de lignes et de valeurs
        widths = {len(r.items) for r in rows}
        if len(widths) != 1 or 0 in widths or any(r.has_keys for r in rows):
            return None                       # lignes de longueurs différentes
        return (len(rows), widths.pop())

    return None


# ─── Point d'entrée public ────────────────────────────────────────

def parse(source: str) -> LuaScript:
    """
    Parse le source Lua et retourne un LuaScript normalisé.
    Lève LuaParseError en cas d'erreur de syntaxe.
    """
    if not _LUAPARSER_OK:
        raise LuaParseError("luaparser n'est pas installé (pip install luaparser)")
    try:
        raw = _lua_ast.parse(source)
        return _Converter().convert_chunk(raw)
    except Exception as e:
        raise LuaParseError(str(e)) from e
