"""Le point central : `Window._show_screen` appelle `refresh()` d'un écran à la
REVISITE, jamais à la première visite (chantier « L'écran resynchronisé à sa
revisite »).

À la première visite, `_load_screen_for_project` peuple déjà l'écran via
`load_project` — un `refresh` de plus serait redondant. Aux visites suivantes,
`load_project` est court-circuité (l'écran est déjà chargé) et c'est `refresh`
qui remet ses catalogues à jour.

Le test pilote les VRAIES méthodes de `MainWindow` sur un stub léger : pas de
widget Qt construit (donc pas de dépendance à l'écran ni de risque de crash
offscreen), mais la logique de gating exercée telle quelle."""
from __future__ import annotations

from types import SimpleNamespace


class _FakeScreen:
    """Satisfait le contrat `ProjectScreen` (a `load_project`) et compte ses
    appels ; `refresh` est le crochet optionnel de revisite."""
    def __init__(self):
        self.loaded = 0
        self.refreshed = 0

    def load_project(self, project):
        self.loaded += 1

    def refresh(self):
        self.refreshed += 1


class _Recorder:
    def __init__(self):
        self.calls = 0

    def clear(self):
        self.calls += 1

    def setCurrentIndex(self, index):
        self.calls += 1


def _make_window(screen):
    """Un stub portant exactement ce que les trois méthodes touchent, avec les
    deux méthodes auxiliaires RÉELLES liées dessus — c'est bien la logique de
    gating de `_show_screen` qu'on exerce, pas une réimplémentation."""
    from window import MainWindow

    win = SimpleNamespace(
        project=object(),                      # un projet ouvert (truthy)
        _project_loaded_screen_indices=set(),
        _screen_widgets=[screen],
        _screens=[SimpleNamespace(name="TestScreen", plugin=False)],
        _screen_stack=_Recorder(),
        _history=_Recorder(),
        _bus=_Recorder(),
    )
    win._ensure_screen = lambda index: screen   # déjà construit
    win._load_screen_for_project = MainWindow._load_screen_for_project.__get__(win)
    win._refresh_screen_for_project = MainWindow._refresh_screen_for_project.__get__(win)
    return win


def test_refresh_appele_en_revisite_pas_a_la_premiere_visite():
    from window import MainWindow

    screen = _FakeScreen()
    win = _make_window(screen)

    # Première visite : load_project peuple, pas de refresh.
    MainWindow._show_screen(win, 0)
    assert (screen.loaded, screen.refreshed) == (1, 0)

    # Visite suivante : load_project court-circuité, refresh appelé.
    MainWindow._show_screen(win, 0)
    assert (screen.loaded, screen.refreshed) == (1, 1)

    # Et encore une : toujours refresh, jamais un second load.
    MainWindow._show_screen(win, 0)
    assert (screen.loaded, screen.refreshed) == (1, 2)


def test_pas_de_refresh_sans_projet():
    from window import MainWindow

    screen = _FakeScreen()
    win = _make_window(screen)
    win.project = None

    MainWindow._show_screen(win, 0)
    MainWindow._show_screen(win, 0)
    assert (screen.loaded, screen.refreshed) == (0, 0)
