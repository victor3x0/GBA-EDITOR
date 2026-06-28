"""build_utils.py — Utilitaires partagés entre build.py et runtime_codegen/."""


def sym(s: str) -> str:
    """Convertit un nom arbitraire en identifiant C valide."""
    r = "".join(c if (c.isalnum() or c == "_") else "_" for c in s)
    return ("_" + r) if r and r[0].isdigit() else r
