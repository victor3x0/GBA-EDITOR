"""Loader pour api_reference.json — source de vérité de l'API runtime GBA."""
from __future__ import annotations
import json
from pathlib import Path

_JSON_PATH = Path(__file__).parent / "api_reference.json"
_cache: list[dict] | None = None


def get_categories() -> list[dict]:
    """Retourne la liste des catégories depuis api_reference.json (mise en cache)."""
    global _cache
    if _cache is None:
        _cache = json.loads(_JSON_PATH.read_text(encoding="utf-8")).get("categories", [])
    return _cache


def make_tooltip(entry: dict) -> str:
    """Génère un tooltip HTML riche pour une entrée API."""
    sig   = entry.get("label", "")
    desc  = entry.get("description", "")
    params = entry.get("params", [])
    ret   = entry.get("returns", "")

    lines = [
        f"<b style='font-family:Consolas,monospace;color:#4ec9b0'>{sig}</b>",
        f"<p style='color:#aaaaaa;margin:4px 0'>{desc}</p>",
    ]

    if params:
        lines.append("<table cellspacing='2' style='margin-top:4px'>")
        for p in params:
            name = p.get("name", "")
            typ  = p.get("type", "")
            pdesc = p.get("description", "")
            lines.append(
                f"<tr>"
                f"<td style='font-family:Consolas,monospace;color:#c48b3c'>{name}</td>"
                f"<td style='color:#555;padding:0 6px'>{typ}</td>"
                f"<td style='color:#888'>{pdesc}</td>"
                f"</tr>"
            )
        lines.append("</table>")

    if ret:
        lines.append(
            f"<p style='color:#555;margin-top:4px;font-style:italic'>→ {ret}</p>"
        )

    lines.append(
        "<p style='color:#383838;margin-top:6px;font-size:9px'>? doc (bientôt disponible)</p>"
    )

    return "".join(lines)
