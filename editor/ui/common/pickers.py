"""editor/ui/common/pickers.py — Slots de sélection réutilisables, construits
sur le même modèle que le "script selector" (ScriptSlot + ScriptPickerPopup) :
bouton "+ Choisir..." quand vide, nom + Changer + × quand assigné, popup
recherche+liste au clic.
"""
from __future__ import annotations

from typing import Callable, Optional

from ui.common.widgets import ScriptSlot, ScriptPickerPopup
from ui.common.palette_swatch import bank_icon
from core.project import PaletteBank


def palette_picker_slot(
    banks: list[PaletteBank],
    current_name: Optional[str],
    accent: str,
    on_picked: Callable[[str], None],
    on_cleared: Optional[Callable[[], None]] = None,
    add_label: str = "Choisir une palette",
    parent=None,
) -> ScriptSlot:
    """Slot pour choisir une PaletteBank par nom parmi `banks` — l'appelant
    décide du sous-ensemble proposé (tout le catalogue projet pour l'éditeur
    de scène, ou seulement les palettes actives d'une scène pour le picker
    pal_bank d'un Actor)."""
    slot = ScriptSlot(
        add_label=add_label, accent_color=accent, edit_label="Changer",
        show_clear=on_cleared is not None,
    )

    current = next((b for b in banks if b.name == current_name), None) if current_name else None
    if current:
        slot.set_script(current.name, icon=bank_icon(current))

    def _open_picker():
        entries = [(bank.name, bank.name, bank_icon(bank)) for bank in banks]
        popup = ScriptPickerPopup(entries, accent, parent=parent, new_label=None)

        def _picked(name: str):
            # Met à jour l'affichage du slot AVANT de notifier l'appelant —
            # sinon le label/icône restent figés sur l'ancienne palette (le
            # callback ne fait que muter le modèle, pas rafraîchir le widget).
            b = next((x for x in banks if x.name == name), None)
            if b:
                slot.set_script(b.name, icon=bank_icon(b))
            on_picked(name)

        popup.picked.connect(_picked)
        popup.show_below(slot)

    slot.set_callbacks(on_add=_open_picker, on_open=_open_picker, on_clear=on_cleared)
    return slot


def sprite_picker_slot(
    sprite_names: list[str],
    current_name: Optional[str],
    accent: str,
    on_picked: Callable[[str], None],
    on_cleared: Optional[Callable[[], None]] = None,
    add_label: str = "Choisir un sprite",
    parent=None,
) -> ScriptSlot:
    """Slot pour choisir un SpriteAsset par nom — même modèle que
    `palette_picker_slot`, sans icône (pas d'aperçu bon marché pour un sprite)."""
    slot = ScriptSlot(
        add_label=add_label, accent_color=accent, edit_label="Changer",
        show_clear=on_cleared is not None,
    )
    if current_name:
        slot.set_script(current_name)

    def _open_picker():
        entries = [(n, n) for n in sorted(sprite_names)]
        popup = ScriptPickerPopup(entries, accent, parent=parent, new_label=None)

        def _picked(name: str):
            slot.set_script(name)   # rafraîchit le label avant de notifier
            on_picked(name)

        popup.picked.connect(_picked)
        popup.show_below(slot)

    slot.set_callbacks(on_add=_open_picker, on_open=_open_picker, on_clear=on_cleared)
    return slot
