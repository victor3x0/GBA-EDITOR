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

# Jeton renvoyé à on_picked quand l'utilisateur choisit « Sans palette » —
# l'appelant le mappe vers OWN_PAL_BANK (l'asset garde ses couleurs d'origine).
PALETTE_NONE = "__none__"
_NONE_LABEL = "Sans palette (couleurs du PNG)"


def palette_picker_slot(
    banks: list[PaletteBank],
    current_name: Optional[str],
    accent: str,
    on_picked: Callable[[str], None],
    on_cleared: Optional[Callable[[], None]] = None,
    add_label: str = "Choisir une palette",
    parent=None,
    allow_none: bool = True,
) -> ScriptSlot:
    """Slot pour choisir une PaletteBank par nom parmi `banks`. Si
    `allow_none` (défaut), une entrée « Sans palette » en tête permet de
    revenir aux couleurs d'origine du PNG — on_picked reçoit alors le jeton
    PALETTE_NONE. `current_name` None + allow_none => affiche « Sans palette »."""
    slot = ScriptSlot(
        add_label=add_label, accent_color=accent, edit_label="Changer",
        show_clear=on_cleared is not None,
    )

    current = next((b for b in banks if b.name == current_name), None) if current_name else None
    if current:
        slot.set_script(current.name, icon=bank_icon(current))
    elif allow_none:
        slot.set_script(_NONE_LABEL)

    def _open_picker():
        entries = [(bank.name, bank.name, bank_icon(bank)) for bank in banks]
        if allow_none:
            entries.insert(0, (_NONE_LABEL, PALETTE_NONE, None))
        popup = ScriptPickerPopup(entries, accent, parent=parent, new_label=None)

        def _picked(name: str):
            # Met à jour l'affichage du slot AVANT de notifier l'appelant.
            if name == PALETTE_NONE:
                slot.set_script(_NONE_LABEL)
            else:
                b = next((x for x in banks if x.name == name), None)
                if b:
                    slot.set_script(b.name, icon=bank_icon(b))
            on_picked(name)

        popup.picked.connect(_picked)
        popup.show_below(slot)

    slot.set_callbacks(on_add=_open_picker, on_open=_open_picker, on_clear=on_cleared)
    return slot


def bank_slot_picker_slot(
    current_slot: Optional[int],
    accent: str,
    on_picked: Callable[[str], None],
    parent=None,
    num_slots: int = 16,
) -> ScriptSlot:
    """Picker de SLOT matériel numéroté (0 à num_slots-1) — pour un MODÈLE de
    prefab, qui n'a pas de scène et ne peut donc pas référencer une palette
    nommée. L'utilisateur choisit directement le slot de banque hardware que
    TOUTE instance utilisera (prévisible quelle que soit la scène). Entrée
    « Sans palette » (couleurs du PNG, auto-allouée) en tête.
    `current_slot` : int (0-15) ou None (== OWN). on_picked reçoit PALETTE_NONE
    ou la chaîne du numéro de slot."""
    slot = ScriptSlot(
        add_label="Choisir un slot", accent_color=accent, edit_label="Changer",
        show_clear=False,
    )
    slot.set_script(_NONE_LABEL if current_slot is None else f"Slot {current_slot}")

    def _open_picker():
        entries = [(_NONE_LABEL, PALETTE_NONE, None)]
        entries += [(f"Slot {i}", str(i), None) for i in range(num_slots)]
        popup = ScriptPickerPopup(entries, accent, parent=parent, new_label=None)

        def _picked(val: str):
            slot.set_script(_NONE_LABEL if val == PALETTE_NONE else f"Slot {val}")
            on_picked(val)

        popup.picked.connect(_picked)
        popup.show_below(slot)

    slot.set_callbacks(on_add=_open_picker, on_open=_open_picker)
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
