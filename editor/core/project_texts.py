"""core/project_texts.py — la table de textes destinés au joueur.

Son I/O, son CRUD, et les règles de la CLÉ (`rename_text_key`, `resync`,
`restore`, `_apply`). La clé reste ici et non avec les renommages d'assets :
renommer un asset déplace un fichier et répare des références, alors qu'une clé
de texte est une règle d'identité de la table — la séparer de ses trois voisines
la rendrait incompréhensible.

S'y ajoutent les littéraux écrits au vol dans un script, qui deviennent des
entrées anonymes au build (`collect_literal_texts`), et `text_values`, qui donne
à l'ÉDITION les valeurs à substituer aux `$nom`.

Une TRANCHE de la classe `Project`, pas un module autonome : les méthodes
ci-dessous s'appellent `self.…` entre elles et avec le reste de `Project`. La
découpe sert la lecture — chaque responsabilité dans son fichier — sans ajouter
le moindre saut d'appel : un mixin est résolu à la construction de la classe,
`project.save_texts()` s'écrit exactement comme avant.

**Ce fichier n'importe jamais `core.project`** : ce serait un cycle immédiat,
puisque `project.py` l'importe pour composer la classe.
"""

import json
from typing import Optional

from core.resource_store import atomic_write
from core import project_json
from core.models.text import (
    Text, key_from_path as text_key_from_path, norm_path as norm_text_path,
    new_id as new_text_id,
)


class ProjectTextsMixin:
    # ── Littéraux de script → entrées anonymes ────────────────────
    # `text.draw` est la seule primitive à accepter un littéral en plus d'une
    # clé (ROADMAP v0.3.2, 2026-07-27) : un accès rapide hors interface, au prix
    # assumé de la traduction. À la compilation il devient une entrée ANONYME de
    # la table, donc le runtime ne connaît qu'un seul chemin (mêmes codepoints,
    # même balisage, mêmes valeurs interpolées).

    def collect_literal_texts(self) -> list:
        """Entrées anonymes à ajouter à la table pour ce build.

        Le repérage est celui du renommage (`iter_refs`, par DOMAINE) : une
        chaîne qui matche une clé existante n'en est pas un, c'est la référence
        à cette entrée."""
        from core.models.text import Text
        from scripting.refactor import iter_refs, script_paths
        from scripting.api import DOMAIN_TEXT, LITERAL_TEXT_CALLS, anon_text_key
        keys = {t.key for t in self.texts}
        found: dict[str, str] = {}
        for path in script_paths(self):
            try:
                src = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for ref in iter_refs(src, path=path, domain=DOMAIN_TEXT):
                if ref.api_key in LITERAL_TEXT_CALLS and ref.value not in keys:
                    found.setdefault(anon_text_key(ref.value), ref.value)
        return [Text(key=k, content=v) for k, v in sorted(found.items())]
    def build_texts(self) -> list:
        """La table de textes VUE PAR LE BUILD : les entrées du projet, puis les
        littéraux des scripts.

        Les entrées réelles gardent leur rang — c'est lui qui fait l'index dans
        `g_texts`, et un littéral ajouté ne doit décaler aucune clé."""
        return list(self.texts) + list(getattr(self, "_anon_texts", []))
    def text_values(self) -> dict:
        """Valeurs à substituer aux marqueurs `$nom` d'un texte, à l'ÉDITION.

        Un global n'a de valeur courante qu'en jeu : l'éditeur montre sa valeur
        INITIALE, la seule qu'il connaisse et celle que la ROM affichera avant
        que quoi que ce soit ne l'ait changée. Une constante, elle, ne bouge
        jamais — l'aperçu montre exactement ce que l'encodeur cuira."""
        out = {g.name: g.default for g in self.globals}
        out.update({c.name: c.value for c in self.constants})
        return out
    # ── I/O textes (table de chaînes destinées au joueur) ───────────

    def save_texts(self):
        data = {"texts": [t.to_dict() for t in self.texts]}
        self.project_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.texts_file, project_json.dumps(data))

    def load_texts(self):
        self.texts = []
        if not self.texts_file.exists():
            return
        d = json.loads(self.texts_file.read_text(encoding="utf-8"))
        self.texts = [Text.from_dict(t) for t in d.get("texts", [])]
        self._repair_texts()

    def _repair_texts(self):
        """Rattrape un fichier édité à la main : id manquant ou dupliqué, clé
        manquante ou dupliquée. L'id prime — c'est lui l'identité ; une clé en
        double est celle qu'on renumérote."""
        seen_ids: set[int] = set()
        seen_keys: set[str] = set()
        for t in self.texts:
            t.path = norm_text_path(t.path)
            if not t.id or t.id in seen_ids:
                t.id = new_text_id(seen_ids)
            seen_ids.add(t.id)
            if not t.key or t.key in seen_keys:
                t.key = text_key_from_path(t.path, taken=seen_keys)
            seen_keys.add(t.key)

    # ── CRUD textes ─────────────────────────────────────────────────

    def text_keys(self) -> set[str]:
        return {t.key for t in self.texts}

    def get_text(self, key: str) -> Optional[Text]:
        """Résolution par clé — l'unique chemin de résolution côté script."""
        return next((t for t in self.texts if t.key == key), None)

    def get_text_by_id(self, tid: int) -> Optional[Text]:
        """Résolution par id — pour les références stockées dans les fichiers
        de données (inspecteurs, scènes), insensibles au renommage."""
        return next((t for t in self.texts if t.id == tid), None)

    def new_text(self, content: str = "", scene: str = "", path=None) -> Text:
        """Crée une entrée. La clé dérive du chemin de rangement, jamais du
        contenu (cf. models/text.py).

        Un texte créé depuis une scène naît sous un nœud portant son nom :
        l'arbre se remplit tout seul, et le chemin par défaut situe déjà."""
        p = norm_text_path(path if path is not None else ([scene] if scene else []))
        t = Text(
            id      = new_text_id({x.id for x in self.texts}),
            key     = text_key_from_path(p, taken=self.text_keys()),
            path    = p,
            content = content,
            scene   = scene,
        )
        self.texts.append(t)
        return t

    def text_path_key(self, text: Text) -> str:
        """Clé que le chemin actuel de `text` produirait — sans l'appliquer.
        Sa propre clé est exclue des collisions, sinon un texte déjà posé au
        bon endroit se verrait proposer un rang `_02` contre lui-même."""
        return text_key_from_path(text.path, taken=self.text_keys() - {text.key})

    def rename_text_key(self, text: Text, new_key: str) -> bool:
        """Renommage MANUEL. Retourne False si le nom est vide ou déjà pris —
        l'appelant (UI) affiche l'erreur. Les appels text.draw("clé") des
        scripts suivent (cf. rename_lua_refs).

        La clé se DÉTACHE alors du chemin (`auto_key=False`) : elle appartient
        à l'utilisateur, ranger le texte ailleurs ne la touchera plus."""
        return self._apply_text_key(text, new_key, manual=True)

    def resync_text_key(self, text: Text) -> Optional[str]:
        """Recale une clé automatique sur le chemin de rangement, et retourne
        la nouvelle clé (None si rien n'a bougé).

        No-op sur une clé nommée à la main — c'est tout l'intérêt de
        `auto_key` : le rangement reste un geste cosmétique tant que
        l'utilisateur n'a pas pris la main sur la clé."""
        if not text.auto_key:
            return None
        want = self.text_path_key(text)
        return want if (want != text.key
                        and self._apply_text_key(text, want, manual=False)) else None

    def restore_text_key(self, text: Text, key: str) -> bool:
        """Repose une clé telle quelle sans la marquer « nommée à la main ».

        Sert à l'ANNULATION d'un rangement : rejouer `resync_text_key` en sens
        inverse ne rendrait pas forcément la même clé (le rang `_NN` dépend des
        clés prises à cet instant), il faut donc remettre l'exacte ancienne."""
        return self._apply_text_key(text, key, manual=False)

    def _apply_text_key(self, text: Text, new_key: str, *, manual: bool) -> bool:
        new_key = (new_key or "").strip()
        if not new_key or any(t.key == new_key and t is not text for t in self.texts):
            return False
        old_key = text.key
        if new_key == old_key:
            return True
        with self._renaming():
            refs = self.rename_lua_refs(DOMAIN_TEXT, old_key, new_key)
            text.key = new_key
            if manual:
                text.auto_key = False
        self._notify_renamed("Text", old_key, new_key, refs)
        return True

    def delete_text(self, text: Text):
        if text in self.texts:
            self.texts.remove(text)
