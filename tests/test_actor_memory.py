"""Contrat mémoire de la table runtime des acteurs."""

from pathlib import Path


def test_actor_table_is_emitted_in_ewram():
    source = Path("editor/codegen/runtime_codegen/main_gen.py").read_text(encoding="utf-8")

    assert 'Actor g_actors[{n_actors}] EWRAM_DATA;' in source
