"""DiagnosticsView (U3, volet B) — la liste du validateur, cliquable.

Sans enrichir `ValidationMessage` : un message qui cite `fichier.lua:ligne` route
vers le script, un message d'acteur route vers sa sélection, le reste s'affiche
sans cible.
"""
from __future__ import annotations

from core.validator import ValidationMessage, DiagnosticTarget
from ui.common.build_panel import DiagnosticsView, BuildPanel


def _view(qapp) -> DiagnosticsView:
    return DiagnosticsView()


def test_set_diagnostics_erreurs_dabord(qapp):
    d = _view(qapp)
    warns = [ValidationMessage("warning", "Hero", "sprite manquant")]
    errs = [ValidationMessage("error", "", "Titre.lua:2 : syntax error")]
    d.set_diagnostics(warns, errs)
    assert d._list.count() == 2
    assert d._msgs[0].level == "error"          # ce qui bloque le build en tête
    assert "1 warning(s)" in d._summary.text() and "1 error(s)" in d._summary.text()


def test_liste_vide(qapp):
    d = _view(qapp)
    d.set_diagnostics([], [])
    assert d._list.count() == 0
    assert d._summary.text() == "No problems"


def test_routage_script_acteur_et_global(qapp):
    d = _view(qapp)
    d.set_diagnostics(
        warnings=[ValidationMessage("warning", "Hero", "sprite manquant"),
                  ValidationMessage("warning", "", "font X ne couvre pas « é »")],
        errors=[ValidationMessage("error", "", "Titre.lua:2 : syntax error")],
    )
    loc, act = [], []
    d.location_activated.connect(lambda f, l: loc.append((f, l)))
    d.actor_activated.connect(lambda n: act.append(n))

    d._on_row(d._list.item(0))   # erreur script → fichier:ligne
    d._on_row(d._list.item(1))   # warning acteur → nom
    d._on_row(d._list.item(2))   # warning global → aucune cible

    assert loc == [("Titre.lua", 2)]
    assert act == ["Hero"]


def test_routage_cible_ui_element_prioritaire(qapp):
    """Une cible structurée `ui_element` route vers l'élément — avant même
    l'heuristique (le message pourrait aussi citer un acteur/un fichier)."""
    d = _view(qapp)
    d.set_diagnostics(
        warnings=[ValidationMessage("warning", "", "le fond du conteneur ne sera pas émis",
                                    DiagnosticTarget("ui_element", "Cursor", "HUD"))],
        errors=[],
    )
    el = []
    d.element_activated.connect(lambda lay, n: el.append((lay, n)))
    d._on_row(d._list.item(0))
    assert el == [("HUD", "Cursor")]


def test_build_panel_a_les_deux_onglets(qapp):
    bp = BuildPanel()
    assert hasattr(bp, "console") and hasattr(bp, "diagnostics")
