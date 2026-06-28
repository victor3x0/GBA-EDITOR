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
    """table.field ou table[key]"""
    obj:   Any
    field: str   # pour notation DOT ; pour [] ce sera une Expr → non géré v1


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
                        # chercher default dans la sous-table
                        default_val = None
                        if type(field_node.value).__name__ == "Table":
                            for sub in field_node.value.fields:
                                sub_key = getattr(sub.key, "id", None)
                                if sub_key == "default" and sub.value is not None:
                                    default_val = self._expr(sub.value)
                                    break
                        locals_.append(LuaLocal(name=key, value=default_val))
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
                return StmtForNum(
                    var   = node.start.id if hasattr(node.start, "id") else "i",
                    start = self._expr(node.stop),    # luaparser: start/stop sont inversés parfois
                    stop  = self._expr(node.step) if node.step else None,
                    step  = None,
                    body  = self._block(node.body, set(local_scope)),
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
                obj   = self._expr(node.value)
                field = node.idx.id if hasattr(node.idx, "id") else str(node.idx)
                return ExprIndex(obj=obj, field=field)
            case "Invoke":
                return self._expr_invoke(node)
            case "Call":
                return self._expr_call(node)
            case "UMinusOp" | "NotOp" | "LenOp":
                op = {"UMinusOp": "-", "NotOp": "not", "LenOp": "#"}.get(t, t)
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
        for s in stmts:
            if isinstance(s, StmtAssign) and isinstance(s.target, ExprName):
                if s.target.name not in local_names:
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
                self._collect_globals(s.then, local_names, out)
                for _, b in s.elseifs:
                    self._collect_globals(b, local_names, out)
                self._collect_globals(s.else_, local_names, out)
            elif isinstance(s, (StmtWhile, StmtForNum)):
                self._collect_globals(s.body, local_names, out)


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
