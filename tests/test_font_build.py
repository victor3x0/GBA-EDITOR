"""Raccord FontAsset → tables GBA : pas de planche intermédiaire sur disque."""

from codegen.font_build import build_font_asset
from codegen.font_emit import TEXT_SURF_TILES, encode_font, font_vram_tiles
from core.font_rasterizer import RasterGlyph
from core.models.font_asset import FontAsset


def test_un_font_asset_rasterise_alimente_encodage_et_budget(monkeypatch):
    glyph = RasterGlyph("A", 3, 5, bytes([255]) * 15, 4, 0, 5, "source")
    monkeypatch.setattr("codegen.font_build.rasterize_asset_glyph",
                        lambda _project, _asset, char: glyph if char == "A"
                        else (_ for _ in ()).throw(RuntimeError("absent")))

    font = build_font_asset(object(), FontAsset(
        name="Dialogue", sources={"regular": ["source"]},
        pixel_height=8, line_height=8), {"A"})
    encoded = encode_font(font)

    assert encoded["codepoints"] == [ord("A")]
    assert encoded["n_tiles"] == 1
    # Chasse 4 px : le même Font temporaire choisit la composition et son
    # budget est bien celui de la surface, pas celui d'une planche source.
    assert font_vram_tiles(font, {ord("A")}) == TEXT_SURF_TILES
