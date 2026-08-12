"""Sound Mixer screen — import/preview SFX + Music."""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSplitter, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QMenu, QFileDialog,
    QSlider, QSpinBox, QCheckBox, QScrollArea, QInputDialog, QMessageBox,
)
from PyQt6.QtMultimedia import (
    QMediaPlayer, QAudioOutput, QSoundEffect,
    QAudioSink, QAudioFormat, QMediaDevices, QAudio,
)
from PyQt6.QtGui import QFont, QColor, QShortcut, QKeySequence
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QBuffer, QByteArray, QIODevice

from ui.common.theme import C, T, QSS
from ui.common.widgets import W
from ui.common.icons import get as _ico, COLOR_DEFAULT

from core.models.audio import Music, Sfx
from core.project import Project
from core.engine_emulation.mod_file import load_mod
from core.engine_emulation.mod_render import render_mod, GBA_MIX_RATE
from core.history import get_history, DeleteResourceCmd

SFX_EXTS   = "*.wav *.ogg"
MUSIC_EXTS = "*.mod *.xm *.s3m *.it *.wav"


# ──────────────────────────────────────────────────────────────────
#  Lecteur audio partagé
# ──────────────────────────────────────────────────────────────────
class AudioPlayer(QWidget):
    """
    Barre de lecture minimale (lecture seule, pas de scrub).

    Deux moteurs selon le format :
      - QMediaPlayer (Qt Multimedia) pour tout ce qu'il sait décoder nativement
        (wav/ogg/mp3…).
      - Rendu maison (core.engine_emulation.mod_render) + QAudioSink pour les .mod : Qt
        Multimedia n'a aucun décodeur tracker (FormatError à l'ouverture), et
        le rendu maison simule en plus le mixeur logiciel Maxmod du GBA (taux
        réduit, pas d'interpolation) pour une preview fidèle au rendu en jeu.
    """

    # Cache {chemin: pcm} pour ne pas re-render à chaque clic play/pause sur
    # le même morceau (le rendu prend jusqu'à ~1s pour un morceau long).
    _mod_cache: dict = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer()
        self._audio  = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(0.8)
        self._player.errorOccurred.connect(self._on_player_error)
        self._current: Optional[Path] = None

        self._sink: Optional[QAudioSink] = None
        self._buffer: Optional[QBuffer] = None
        self._is_mod = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._lbl = QLabel("—")
        self._lbl.setFont(QFont(T.UI, T.SM))
        self._lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        layout.addWidget(self._lbl, 1)

        self._btn = QPushButton("▶")
        self._btn.setFixedSize(28, 22)
        self._btn.setFont(QFont(T.MONO, T.MD))
        self._btn.setStyleSheet(
            f"QPushButton{{background:{C.BG_SEL};color:{C.ACCENT};border:1px solid #3a3a5a;"
            "border-radius:3px;}"
            "QPushButton:hover{background:#2e2e3d;}"
        )
        self._btn.clicked.connect(self._toggle)
        layout.addWidget(self._btn)

        self._stop_btn = QPushButton("■")
        self._stop_btn.setFixedSize(28, 22)
        self._stop_btn.setFont(QFont(T.MONO, T.MD))
        self._stop_btn.setStyleSheet(
            f"QPushButton{{background:{C.BORDER};color:{C.TEXT_DIM};border:1px solid {C.BORDER_MID};"
            "border-radius:3px;}"
            f"QPushButton:hover{{background:#3a2a2a;color:{C.ACCENT_RED};}}"
        )
        self._stop_btn.clicked.connect(self._stop)
        layout.addWidget(self._stop_btn)

        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100); self._vol.setValue(80); self._vol.setFixedWidth(70)
        self._vol.setStyleSheet(f"QSlider::groove:horizontal{{height:4px;background:{C.BORDER_MID};border-radius:2px;}}"
                          "QSlider::handle:horizontal{width:10px;height:10px;margin:-3px 0;"
                          f"background:{C.ACCENT};border-radius:5px;}}")
        self._vol.valueChanged.connect(self._on_volume)
        layout.addWidget(self._vol)

        self._player.playbackStateChanged.connect(self._on_state)

    def load(self, path: Path):
        self._teardown_sink()
        self._current = path
        self._is_mod = path.suffix.lower() == ".mod"
        self._lbl.setText(path.name)
        self._btn.setText("▶")

        if self._is_mod:
            self._player.stop()
            self._player.setSource(QUrl())
            self._prepare_mod_sink(path)
        else:
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(str(path)))

    def play(self, path: Path):
        self.load(path)
        if self._is_mod:
            if self._sink is not None:
                self._buffer.seek(0)
                self._sink.start(self._buffer)
                self._btn.setText("⏸")
        else:
            self._player.play()

    def _prepare_mod_sink(self, path: Path):
        try:
            pcm = self._mod_cache.get(path)
            if pcm is None:
                pcm = render_mod(load_mod(path))
                self._mod_cache[path] = pcm
            if pcm.shape[0] == 0:
                self._lbl.setText(f"{path.name}  (empty / unreadable)")
                return
            fmt = QAudioFormat()
            fmt.setSampleRate(GBA_MIX_RATE)
            fmt.setChannelCount(2)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            device = QMediaDevices.defaultAudioOutput()
            self._sink = QAudioSink(device, fmt)
            self._sink.setVolume(self._vol.value() / 100.0)
            self._sink.stateChanged.connect(self._on_sink_state)
            self._buffer = QBuffer()
            self._buffer.setData(QByteArray(pcm.tobytes()))
            self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        except Exception as e:
            self._lbl.setText(f"{path.name}  (erreur de lecture MOD : {e})")
            self._sink = None

    def _teardown_sink(self):
        if self._sink is not None:
            self._sink.stop()
            self._sink = None
        if self._buffer is not None:
            self._buffer.close()
            self._buffer = None

    def _toggle(self):
        if self._is_mod:
            if self._sink is None:
                return
            if self._sink.state() == QAudio.State.ActiveState:
                self._sink.suspend()
            elif self._sink.state() == QAudio.State.SuspendedState:
                self._sink.resume()
            else:
                self._buffer.seek(0)
                self._sink.start(self._buffer)
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _stop(self):
        if self._is_mod:
            if self._sink is not None:
                self._sink.stop()
            self._btn.setText("▶")
            return
        self._player.stop()

    def _on_state(self, state):
        if self._is_mod:
            return
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._btn.setText("⏸" if playing else "▶")

    def _on_sink_state(self, state):
        if not self._is_mod:
            return
        self._btn.setText("⏸" if state == QAudio.State.ActiveState else "▶")

    def _on_volume(self, v: int):
        vol = v / 100.0
        self._audio.setVolume(vol)
        if self._sink is not None:
            self._sink.setVolume(vol)

    def _on_player_error(self, error, error_string: str):
        if self._is_mod or error == QMediaPlayer.Error.NoError:
            return
        self._lbl.setText(f"{self._current.name if self._current else '—'}  (preview unavailable: {error_string})")


# ──────────────────────────────────────────────────────────────────
#  Inspector d'un Sfx
# ──────────────────────────────────────────────────────────────────
class _AssetInspectorBase(QWidget):
    """Base commune à SfxInspector/MusicInspector : header renommable,
    import de fichier, volume 0-255. Les sous-classes ne fournissent que
    leurs textes/filtres spécifiques et le manager de persistence."""
    changed = pyqtSignal()

    _EMPTY_TEXT = ""
    _HEADER_KIND = ""
    _HEADER_LABEL = ""
    _IMPORT_BTN_TEXT = ""
    _IMPORT_DIALOG_TITLE = ""
    _IMPORT_FILTER = ""
    _IMPORT_FOLDER = ""
    _HAS_LOOP = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self._asset = None
        self._project: Optional[Project] = None
        self._blocking = False
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._empty = QLabel(self._EMPTY_TEXT)
        self._empty.setFont(QFont(T.UI, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        def row(label, widget):
            r = QHBoxLayout()
            l = QLabel(label); l.setFont(QFont(T.UI, T.SM))
            l.setStyleSheet(f"color:{C.TEXT_DIM};"); l.setFixedWidth(70)
            r.addWidget(l); r.addWidget(widget, 1); cl.addLayout(r); return widget

        from ui.common.widgets import AssetHeaderBar
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_renamed)
        cl.addWidget(self._header)

        self._file_lbl = QLabel("None")
        self._file_lbl.setFont(QFont(T.UI, T.SM))
        self._file_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        cl.addWidget(self._file_lbl)

        btn_import = QPushButton(self._IMPORT_BTN_TEXT)
        btn_import.setFont(QFont(T.UI, T.MD))
        btn_import.clicked.connect(self._import)
        cl.addWidget(btn_import)

        if self._HAS_LOOP:
            self._loop = QCheckBox("Loop")
            self._loop.setFont(QFont(T.UI, T.MD))
            self._loop.setStyleSheet(f"color:{C.TEXT_NORM};")
            self._loop.toggled.connect(self._on_loop)
            cl.addWidget(self._loop)

        self._vol = QSpinBox(); self._vol.setRange(0, 255)
        self._vol.setFont(QFont(T.MONO, T.MD))
        self._vol.setStyleSheet(
            f"QSpinBox{{background:{C.BG_INPUT};color:{C.TEXT_NORM};border:1px solid {C.BORDER_MID};"
            "border-radius:3px;padding:2px;}"
        )
        self._vol.setToolTip("Volume (0–255)")
        self._vol.valueChanged.connect(self._on_vol)
        row("Volume", self._vol)

        cl.addStretch()
        layout.addWidget(self._content)
        layout.addStretch()
        self._content.setVisible(False)

    def _manager(self):
        raise NotImplementedError

    def _save(self):
        raise NotImplementedError

    def load(self, asset, project: Project):
        self._asset = asset; self._project = project
        if not asset:
            self._content.setVisible(False); self._empty.setVisible(True); return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._blocking = True
        self._header.set_header(self._HEADER_KIND, self._HEADER_LABEL, asset.name)
        ap = project.asset_abs(asset.asset) if asset.asset else None
        self._file_lbl.setText(ap.name if ap else "Aucun fichier")
        if self._HAS_LOOP:
            self._loop.setChecked(getattr(asset, "loop", True))
        self._vol.setValue(getattr(asset, "volume", 255))
        self._blocking = False

    def _on_renamed(self, new_name: str):
        if self._blocking or not self._asset or not self._project: return
        new_name = new_name.strip()
        if new_name and new_name != self._asset.name:
            # Passe par le projet (pas le ResourceStore brut) : il met aussi
            # à jour les sfx.play()/music.play() des scripts.
            self._project.rename_sound(self._asset, new_name)
            self.changed.emit()

    def _on_loop(self, v):
        if self._blocking or not self._asset: return
        self._asset.loop = v
        self._save()
        self.changed.emit()

    def _on_vol(self, v):
        if self._blocking or not self._asset: return
        self._asset.volume = v
        self._save()
        self.changed.emit()

    def _import(self):
        if not self._project or not self._asset: return
        path, _ = QFileDialog.getOpenFileName(
            self, self._IMPORT_DIALOG_TITLE, "", self._IMPORT_FILTER
        )
        if path:
            dst = self._project.import_asset(Path(path), self._IMPORT_FOLDER)
            self._asset.asset = self._project.asset_rel(dst)
            self._save()
            self._file_lbl.setText(dst.name)
            self.changed.emit()


class SfxInspector(_AssetInspectorBase):
    _EMPTY_TEXT = "Select an SFX"
    _HEADER_KIND = "sfx"
    _HEADER_LABEL = "SFX"
    _IMPORT_BTN_TEXT = "Importer WAV…"
    _IMPORT_DIALOG_TITLE = "Importer SFX"
    _IMPORT_FILTER = "Audio (*.wav *.ogg);;Tous (*)"
    _IMPORT_FOLDER = "sfx"

    def _manager(self):
        return self._project.sfx

    def _save(self):
        self._project.save_sfx(self._asset)


# ──────────────────────────────────────────────────────────────────
#  Inspector d'une Music
# ──────────────────────────────────────────────────────────────────
class MusicInspector(_AssetInspectorBase):
    _EMPTY_TEXT = "Select a track"
    _HEADER_KIND = "music"
    _HEADER_LABEL = "MUSIC"
    _IMPORT_BTN_TEXT = "Importer MOD/WAV…"
    _IMPORT_DIALOG_TITLE = "Importer Music"
    _IMPORT_FILTER = "Tracker/Audio (*.mod *.xm *.s3m *.it *.wav);;Tous (*)"
    _IMPORT_FOLDER = "music"
    _HAS_LOOP = True

    def _manager(self):
        return self._project.music

    def _save(self):
        self._project.save_music(self._asset)


# ──────────────────────────────────────────────────────────────────
#  SoundMixerScreen
# ──────────────────────────────────────────────────────────────────
class SoundFinderPanel(QWidget):
    """
    Panneau gauche du Sound Mixer : listes SFX + Music (ajout/renommage en
    place/suppression), même comportement que les autres finders (Assets
    finder / Sprite finder / Script finder). Ne connaît pas l'inspector ni
    le lecteur audio — il notifie l'écran parent via des signaux.
    """

    sfx_selected       = pyqtSignal(object)   # Sfx
    music_selected     = pyqtSignal(object)   # Music
    sfx_deleted        = pyqtSignal()
    music_deleted      = pyqtSignal()
    sfx_play_requested   = pyqtSignal(object)   # Sfx
    music_play_requested = pyqtSignal(object)   # Music

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self.setMinimumWidth(180)
        self.setMaximumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Bandeau "finder" (identité du panneau, cohérent avec les
        #    autres écrans : Assets finder / Sprite finder / Script finder) ──
        root.addWidget(W.finder_bar("SOUND FINDER"))

        # SFX section — add/supprimer remontés dans le header (style asset finder)
        self._sfx_section = self._make_section(
            "SFX", C.TEXT_NORM, lambda: self._add(Sfx), "Add an SFX",
            lambda: self._del(Sfx), "Delete selected SFX")
        root.addWidget(self._sfx_section)
        self._sfx_list = QTreeWidget()
        self._sfx_list.setHeaderHidden(True)
        self._sfx_list.setFont(QFont(T.UI, T.MD))
        self._sfx_list.setStyleSheet(QSS.tree_widget)
        self._sfx_list.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._sfx_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sfx_list.currentItemChanged.connect(lambda cur, prev: self._on_selected(Sfx, cur, prev))
        self._sfx_list.itemDoubleClicked.connect(lambda item: self._play(Sfx, item))
        self._sfx_list.itemChanged.connect(lambda item, col: self._on_item_text_changed(Sfx, item, col))
        self._sfx_list.customContextMenuRequested.connect(lambda pos: self._on_ctx_menu(Sfx, pos))
        root.addWidget(self._sfx_list, 1)

        # Espace : preview rapide du SFX sélectionné (sans repasser par un
        # double-clic). Contexte limité à la liste elle-même pour ne pas
        # intercepter la barre espace ailleurs dans l'écran (boutons +/×...).
        sc_sfx = QShortcut(QKeySequence(Qt.Key.Key_Space), self._sfx_list)
        sc_sfx.setContext(Qt.ShortcutContext.WidgetShortcut)
        sc_sfx.activated.connect(lambda: self._play_selected(Sfx))

        # Music section
        self._music_section = self._make_section(
            "MUSIC", C.TEXT_NORM, lambda: self._add(Music), "Add a track",
            lambda: self._del(Music), "Delete selected track")
        root.addWidget(self._music_section)
        self._music_list = QTreeWidget()
        self._music_list.setHeaderHidden(True)
        self._music_list.setFont(QFont(T.UI, T.MD))
        self._music_list.setStyleSheet(QSS.tree_widget)
        self._music_list.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._music_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._music_list.currentItemChanged.connect(lambda cur, prev: self._on_selected(Music, cur, prev))
        self._music_list.itemDoubleClicked.connect(lambda item: self._play(Music, item))
        self._music_list.itemChanged.connect(lambda item, col: self._on_item_text_changed(Music, item, col))
        self._music_list.customContextMenuRequested.connect(lambda pos: self._on_ctx_menu(Music, pos))
        root.addWidget(self._music_list, 1)

        sc_music = QShortcut(QKeySequence(Qt.Key.Key_Space), self._music_list)
        sc_music.setContext(Qt.ShortcutContext.WidgetShortcut)
        sc_music.activated.connect(lambda: self._play_selected(Music))

    # ── Utilitaires ───────────────────────────────────────────────

    def _make_section(self, title: str, color: str, on_add, add_tooltip: str,
                       on_del, del_tooltip: str) -> QFrame:
        """En-tête de section — titre + boutons Ajouter/Supprimer intégrés,
        même emplacement/style que les autres asset finders (assets_finder_panel.py)."""
        f = W.section_bar(title, color)
        hl = f.layout()

        btn_add = W.btn_add(add_tooltip)
        btn_add.clicked.connect(on_add)
        hl.addWidget(btn_add)

        btn_del = W.btn_danger(del_tooltip)
        btn_del.clicked.connect(on_del)
        hl.addWidget(btn_del)

        return f

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self.refresh()

    def refresh(self):
        self._refresh_kind(Sfx)
        self._refresh_kind(Music)

    # ── Table de dispatch sfx/music ──────────────────────────────────
    # Chaque méthode ci-dessous est paramétrée par le type (Sfx/Music) au
    # lieu de dupliquer sa logique une fois par liste ; ce dict fournit
    # les éléments qui diffèrent réellement entre les deux (liste Qt,
    # collection projet, icône, signaux, libellés de dialogue).

    def _kind_info(self, kind: type):
        if kind is Sfx:
            return dict(
                list=self._sfx_list, other_list=self._music_list,
                manager=self._project.sfx if self._project else None,
                icon_key="sfx", icon_color=COLOR_DEFAULT,
                selected=self.sfx_selected, play_requested=self.sfx_play_requested,
                deleted=self.sfx_deleted,
                add_title="New SFX", del_label="the SFX",
                save=self._project.save_sfx if self._project else None,
            )
        return dict(
            list=self._music_list, other_list=self._sfx_list,
            manager=self._project.music if self._project else None,
            icon_key="music", icon_color=COLOR_DEFAULT,
            selected=self.music_selected, play_requested=self.music_play_requested,
            deleted=self.music_deleted,
            add_title="New track", del_label="the track",
            save=self._project.save_music if self._project else None,
        )

    def _refresh_kind(self, kind: type):
        info = self._kind_info(kind)
        lst = info["list"]
        lst.blockSignals(True)
        lst.clear()
        if self._project:
            for asset in info["manager"]:
                ap = self._project.asset_abs(asset.asset) if asset.asset else None
                icon_key = info["icon_key"] if ap and ap.exists() else "asset_missing"
                item = QTreeWidgetItem([asset.name])
                item.setIcon(0, _ico(icon_key, info["icon_color"]))
                item.setData(0, Qt.ItemDataRole.UserRole, asset)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                lst.addTopLevelItem(item)
        lst.blockSignals(False)

    # ── Sélection ─────────────────────────────────────────────────

    def _on_selected(self, kind: type, current: QTreeWidgetItem, _prev):
        info = self._kind_info(kind)
        info["other_list"].clearSelection()
        asset = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        if isinstance(asset, kind):
            info["selected"].emit(asset)

    def _play(self, kind: type, item: QTreeWidgetItem):
        asset = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(asset, kind):
            self._kind_info(kind)["play_requested"].emit(asset)

    def _play_selected(self, kind: type):
        item = self._kind_info(kind)["list"].currentItem()
        if item:
            self._play(kind, item)

    # ── Renommage en place ───────────────────────────────────────────

    def _on_item_text_changed(self, kind: type, item: QTreeWidgetItem, _col: int):
        asset = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(asset, kind):
            return
        info = self._kind_info(kind)
        lst = info["list"]
        new_name = item.text(0).strip()
        if not new_name or new_name == asset.name:
            lst.blockSignals(True)
            item.setText(0, asset.name)
            lst.blockSignals(False)
            return
        # Via le projet : met aussi à jour les sfx.play()/music.play() des scripts.
        if self._project:
            self._project.rename_sound(asset, new_name)
        else:
            info["manager"].rename(asset, new_name)
        lst.blockSignals(True)
        item.setText(0, asset.name)
        lst.blockSignals(False)
        info["selected"].emit(asset)

    # ── Menus contextuels ────────────────────────────────────────────

    def _on_ctx_menu(self, kind: type, pos):
        lst = self._kind_info(kind)["list"]
        item = lst.itemAt(pos)
        if not item:
            return
        lst.setCurrentItem(item)
        menu = QMenu(self)
        delete_a = menu.addAction("Delete")
        if menu.exec(lst.viewport().mapToGlobal(pos)) == delete_a:
            self._del(kind)

    # ── Ajout / suppression ───────────────────────────────────────

    def _add(self, kind: type):
        if not self._project: return
        info = self._kind_info(kind)
        name, ok = QInputDialog.getText(self, info["add_title"], "Name:")
        if ok and name.strip():
            asset = kind(name=name.strip())
            info["manager"].append(asset)
            info["save"](asset)
            self._refresh_kind(kind)
            lst = info["list"]
            last = lst.topLevelItem(lst.topLevelItemCount() - 1)
            if last:
                lst.setCurrentItem(last)

    def _del(self, kind: type):
        info = self._kind_info(kind)
        item = info["list"].currentItem()
        asset = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not self._project or not isinstance(asset, kind):
            return
        if QMessageBox.question(
            self, "Delete",
            f"Delete {info['del_label']} “{asset.name}”?\n(Ctrl+Z to undo)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        def _refresh():
            self._refresh_kind(kind)
            info["deleted"].emit()

        get_history().push(DeleteResourceCmd(info["manager"], asset, _refresh))


# ──────────────────────────────────────────────────────────────────
#  SoundMixerScreen
# ──────────────────────────────────────────────────────────────────
class SoundMixerScreen(QWidget):
    """Écran complet Sound Mixer : SFX + Music (via SoundFinderPanel) + preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Pas de bandeau-titre d'écran : la nav du haut indique déjà où on est
        # (décision refonte thème 2026-08).

        # Player bar
        self._player = AudioPlayer()
        self._player.setStyleSheet(f"background:{C.BG_BASE}; border-bottom:1px solid {C.BORDER};")
        self._player.setFixedHeight(34)
        root.addWidget(self._player)

        # Splitter principal
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setStyleSheet(QSS.splitter)
        root.addWidget(split, 1)

        # ── Panneau gauche : Sound finder ──────────────────────────
        self._finder = SoundFinderPanel()
        self._finder.sfx_selected.connect(self._on_sfx_selected)
        self._finder.music_selected.connect(self._on_music_selected)
        self._finder.sfx_deleted.connect(lambda: self._right_stack.setCurrentIndex(0))
        self._finder.music_deleted.connect(lambda: self._right_stack.setCurrentIndex(0))
        self._finder.sfx_play_requested.connect(self._play_asset)
        self._finder.music_play_requested.connect(self._play_asset)
        split.addWidget(self._finder)

        # ── Panneau droit : inspector ─────────────────────────────
        from PyQt6.QtWidgets import QStackedWidget
        self._right_stack = QStackedWidget()
        self._right_stack.setMinimumWidth(200)

        empty_w = QWidget(); empty_w.setStyleSheet(f"background:{C.BG_PANEL};")
        el = QVBoxLayout(empty_w)
        hint = QLabel("Select or create\nan SFX or a track\nto edit its properties")
        hint.setFont(QFont(T.UI, T.MD))
        hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addStretch(); el.addWidget(hint); el.addStretch()
        self._right_stack.addWidget(empty_w)      # 0

        self._sfx_insp = SfxInspector()
        self._sfx_insp.changed.connect(self._on_changed)
        self._right_stack.addWidget(self._sfx_insp)   # 1

        self._music_insp = MusicInspector()
        self._music_insp.changed.connect(self._on_changed)
        self._right_stack.addWidget(self._music_insp)  # 2

        split.addWidget(self._right_stack)
        split.setSizes([220, 500])

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._finder.load_project(project)
        self._right_stack.setCurrentIndex(0)

    # ── Sélection / lecture (relayées depuis le Sound finder) ──────

    def _on_sfx_selected(self, sfx: Sfx):
        self._sfx_insp.load(sfx, self._project)
        self._right_stack.setCurrentIndex(1)
        self._load_asset(sfx)

    def _on_music_selected(self, music: Music):
        self._music_insp.load(music, self._project)
        self._right_stack.setCurrentIndex(2)
        self._load_asset(music)

    def _load_asset(self, obj):
        """
        Charge l'asset dans la barre de preview sans lancer la lecture — pour
        que le bouton ▶ (ou Espace) fonctionne dès la sélection, sans devoir
        d'abord double-cliquer l'entrée.
        """
        ap = self._project.asset_abs(obj.asset) if self._project and obj.asset else None
        if ap and ap.exists():
            self._player.load(ap)

    def _play_asset(self, obj):
        ap = self._project.asset_abs(obj.asset) if self._project and obj.asset else None
        if ap and ap.exists():
            self._player.play(ap)

    def _on_changed(self):
        self._finder.refresh()
