"""Sound Mixer screen — import/preview SFX + Music."""

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSplitter, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QMenu, QFileDialog,
    QSlider, QSpinBox, QCheckBox, QScrollArea, QInputDialog,
)
from PyQt6.QtMultimedia import (
    QMediaPlayer, QAudioOutput, QSoundEffect,
    QAudioSink, QAudioFormat, QMediaDevices, QAudio,
)
from PyQt6.QtGui import QFont, QColor, QShortcut, QKeySequence
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QBuffer, QByteArray, QIODevice

from ui.theme import T
from ui.widgets import W
from ui.icons import get as _ico, COLOR_SFX, COLOR_MUSIC

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.project import Project, Sfx, Music
from core.mod_file import load_mod
from core.mod_render import render_mod, GBA_MIX_RATE

SPLITTER_STYLE = (
    "QSplitter::handle{background:#2a2a2a;}"
    "QSplitter::handle:horizontal{width:3px;}"
    "QSplitter::handle:hover{background:#4a8a5a;}"
)

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
      - Rendu maison (core.mod_render) + QAudioSink pour les .mod : Qt
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
        self._lbl.setFont(QFont(T.MONO, T.SM))
        self._lbl.setStyleSheet("color:#888;")
        layout.addWidget(self._lbl, 1)

        self._btn = QPushButton("▶")
        self._btn.setFixedSize(28, 22)
        self._btn.setFont(QFont(T.MONO, T.MD))
        self._btn.setStyleSheet(
            "QPushButton{background:#2a3a2a;color:#4caf78;border:1px solid #3a4a3a;"
            "border-radius:3px;}"
            "QPushButton:hover{background:#3a4a3a;}"
        )
        self._btn.clicked.connect(self._toggle)
        layout.addWidget(self._btn)

        self._stop_btn = QPushButton("■")
        self._stop_btn.setFixedSize(28, 22)
        self._stop_btn.setFont(QFont(T.MONO, T.MD))
        self._stop_btn.setStyleSheet(
            "QPushButton{background:#2a2a2a;color:#888;border:1px solid #333;"
            "border-radius:3px;}"
            "QPushButton:hover{background:#3a2a2a;color:#ff6b6b;}"
        )
        self._stop_btn.clicked.connect(self._stop)
        layout.addWidget(self._stop_btn)

        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100); self._vol.setValue(80); self._vol.setFixedWidth(70)
        self._vol.setStyleSheet("QSlider::groove:horizontal{height:4px;background:#333;border-radius:2px;}"
                          "QSlider::handle:horizontal{width:10px;height:10px;margin:-3px 0;"
                          "background:#4caf78;border-radius:5px;}")
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
                self._lbl.setText(f"{path.name}  (vide / illisible)")
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
        self._lbl.setText(f"{self._current.name if self._current else '—'}  (aperçu indisponible : {error_string})")


# ──────────────────────────────────────────────────────────────────
#  Inspector d'un Sfx
# ──────────────────────────────────────────────────────────────────
class SfxInspector(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sfx: Optional[Sfx] = None
        self._project: Optional[Project] = None
        self._blocking = False
        self.setStyleSheet("background:#1a1a1a;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._empty = QLabel("Selectionne un SFX")
        self._empty.setFont(QFont(T.MONO, T.MD))
        self._empty.setStyleSheet("color:#444; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        def row(label, widget):
            r = QHBoxLayout()
            l = QLabel(label); l.setFont(QFont(T.MONO, T.SM))
            l.setStyleSheet("color:#888;"); l.setFixedWidth(70)
            r.addWidget(l); r.addWidget(widget, 1); cl.addLayout(r); return widget

        from ui.widgets import AssetHeaderBar
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_renamed)
        cl.addWidget(self._header)

        self._file_lbl = QLabel("Aucun")
        self._file_lbl.setFont(QFont(T.MONO, T.SM))
        self._file_lbl.setStyleSheet("color:#555;")
        cl.addWidget(self._file_lbl)

        btn_import = QPushButton("Importer WAV…")
        btn_import.setFont(QFont(T.MONO, T.MD))
        btn_import.clicked.connect(self._import)
        cl.addWidget(btn_import)

        self._vol = QSpinBox(); self._vol.setRange(0, 255)
        self._vol.setFont(QFont(T.MONO, T.MD))
        self._vol.setStyleSheet(
            "QSpinBox{background:#222;color:#ccc;border:1px solid #333;border-radius:3px;padding:2px;}"
        )
        self._vol.setToolTip("Volume (0–255)")
        self._vol.valueChanged.connect(self._on_vol)
        row("Volume", self._vol)

        cl.addStretch()
        layout.addWidget(self._content)
        layout.addStretch()
        self._content.setVisible(False)

    def load(self, sfx: Sfx, project: Project):
        self._sfx = sfx; self._project = project
        if not sfx:
            self._content.setVisible(False); self._empty.setVisible(True); return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._blocking = True
        self._header.set_header("sfx", "SFX", sfx.name)
        ap = project.asset_abs(sfx.asset) if sfx.asset else None
        self._file_lbl.setText(ap.name if ap else "Aucun fichier")
        self._vol.setValue(getattr(sfx, "volume", 255))
        self._blocking = False

    def _on_renamed(self, new_name: str):
        if self._blocking or not self._sfx or not self._project: return
        new_name = new_name.strip()
        if new_name and new_name != self._sfx.name:
            self._project.sfx.rename(self._sfx, new_name)
            self.changed.emit()

    def _on_vol(self, v):
        if self._blocking or not self._sfx: return
        self._sfx.volume = v
        self._project.save_sfx(self._sfx)
        self.changed.emit()

    def _import(self):
        if not self._project or not self._sfx: return
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer SFX", "", "Audio (*.wav *.ogg);;Tous (*)"
        )
        if path:
            dst = self._project.import_asset(Path(path), "sfx")
            self._sfx.asset = self._project.asset_rel(dst)
            self._project.save_sfx(self._sfx)
            self._file_lbl.setText(dst.name)
            self.changed.emit()


# ──────────────────────────────────────────────────────────────────
#  Inspector d'une Music
# ──────────────────────────────────────────────────────────────────
class MusicInspector(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._music: Optional[Music] = None
        self._project: Optional[Project] = None
        self._blocking = False
        self.setStyleSheet("background:#1a1a1a;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._empty = QLabel("Selectionne une piste")
        self._empty.setFont(QFont(T.MONO, T.MD))
        self._empty.setStyleSheet("color:#444; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        def row(label, widget):
            r = QHBoxLayout()
            l = QLabel(label); l.setFont(QFont(T.MONO, T.SM))
            l.setStyleSheet("color:#888;"); l.setFixedWidth(70)
            r.addWidget(l); r.addWidget(widget, 1); cl.addLayout(r); return widget

        from ui.widgets import AssetHeaderBar
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_renamed)
        cl.addWidget(self._header)

        self._file_lbl = QLabel("Aucun")
        self._file_lbl.setFont(QFont(T.MONO, T.SM))
        self._file_lbl.setStyleSheet("color:#555;")
        cl.addWidget(self._file_lbl)

        btn_import = QPushButton("Importer MOD/WAV…")
        btn_import.setFont(QFont(T.MONO, T.MD))
        btn_import.clicked.connect(self._import)
        cl.addWidget(btn_import)

        self._loop = QCheckBox("Boucle")
        self._loop.setFont(QFont(T.MONO, T.MD))
        self._loop.setStyleSheet("color:#ccc;")
        self._loop.toggled.connect(self._on_loop)
        cl.addWidget(self._loop)

        self._vol = QSpinBox(); self._vol.setRange(0, 255)
        self._vol.setFont(QFont(T.MONO, T.MD))
        self._vol.setStyleSheet(
            "QSpinBox{background:#222;color:#ccc;border:1px solid #333;border-radius:3px;padding:2px;}"
        )
        self._vol.setToolTip("Volume (0–255)")
        self._vol.valueChanged.connect(self._on_vol)
        row("Volume", self._vol)

        cl.addStretch()
        layout.addWidget(self._content)
        layout.addStretch()
        self._content.setVisible(False)

    def load(self, music: Music, project: Project):
        self._music = music; self._project = project
        if not music:
            self._content.setVisible(False); self._empty.setVisible(True); return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._blocking = True
        self._header.set_header("music", "MUSIC", music.name)
        ap = project.asset_abs(music.asset) if music.asset else None
        self._file_lbl.setText(ap.name if ap else "Aucun fichier")
        self._loop.setChecked(getattr(music, "loop", True))
        self._vol.setValue(getattr(music, "volume", 255))
        self._blocking = False

    def _on_renamed(self, new_name: str):
        if self._blocking or not self._music or not self._project: return
        new_name = new_name.strip()
        if new_name and new_name != self._music.name:
            self._project.music.rename(self._music, new_name)
            self.changed.emit()

    def _on_loop(self, v):
        if self._blocking or not self._music: return
        self._music.loop = v
        self._project.save_music(self._music)
        self.changed.emit()

    def _on_vol(self, v):
        if self._blocking or not self._music: return
        self._music.volume = v
        self._project.save_music(self._music)
        self.changed.emit()

    def _import(self):
        if not self._project or not self._music: return
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer Music",
            "", "Tracker/Audio (*.mod *.xm *.s3m *.it *.wav);;Tous (*)"
        )
        if path:
            dst = self._project.import_asset(Path(path), "music")
            self._music.asset = self._project.asset_rel(dst)
            self._project.save_music(self._music)
            self._file_lbl.setText(dst.name)
            self.changed.emit()


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
        self.setStyleSheet("background:#141414;")
        self.setMinimumWidth(180)
        self.setMaximumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Bandeau "finder" (identité du panneau, cohérent avec les
        #    autres écrans : Assets finder / Sprite finder / Script finder) ──
        finder_hdr = QFrame()
        finder_hdr.setFixedHeight(20)
        finder_hdr.setStyleSheet("background:#141414; border-bottom:1px solid #232323;")
        fl = QHBoxLayout(finder_hdr)
        fl.setContentsMargins(8, 0, 0, 0)
        finder_lbl = QLabel("SOUND FINDER")
        finder_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        finder_lbl.setStyleSheet("color:#555; letter-spacing:1px;")
        fl.addWidget(finder_lbl)
        root.addWidget(finder_hdr)

        # SFX section — add/supprimer remontés dans le header (style asset finder)
        self._sfx_section = self._make_section(
            "SFX", "#c48b3c", self._add_sfx, "Ajouter un SFX", self._del_sfx, "Supprimer le SFX sélectionné")
        root.addWidget(self._sfx_section)
        self._sfx_list = QTreeWidget()
        self._sfx_list.setHeaderHidden(True)
        self._sfx_list.setFont(QFont(T.MONO, T.MD))
        self._sfx_list.setStyleSheet(
            "QTreeWidget{background:#161616;color:#ccc;border:none;}"
            "QTreeWidget::item:selected{background:#3a2a1a;}"
            "QTreeWidget::item:hover{background:#252010;}"
        )
        self._sfx_list.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._sfx_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sfx_list.currentItemChanged.connect(self._on_sfx_selected)
        self._sfx_list.itemDoubleClicked.connect(self._play_sfx)
        self._sfx_list.itemChanged.connect(self._on_sfx_item_text_changed)
        self._sfx_list.customContextMenuRequested.connect(self._on_sfx_ctx_menu)
        root.addWidget(self._sfx_list, 1)

        # Espace : preview rapide du SFX sélectionné (sans repasser par un
        # double-clic). Contexte limité à la liste elle-même pour ne pas
        # intercepter la barre espace ailleurs dans l'écran (boutons +/×...).
        sc_sfx = QShortcut(QKeySequence(Qt.Key.Key_Space), self._sfx_list)
        sc_sfx.setContext(Qt.ShortcutContext.WidgetShortcut)
        sc_sfx.activated.connect(self._play_selected_sfx)

        # Music section
        self._music_section = self._make_section(
            "MUSIC", "#9b7bd5", self._add_music, "Ajouter une Music", self._del_music, "Supprimer la Music sélectionnée")
        root.addWidget(self._music_section)
        self._music_list = QTreeWidget()
        self._music_list.setHeaderHidden(True)
        self._music_list.setFont(QFont(T.MONO, T.MD))
        self._music_list.setStyleSheet(
            "QTreeWidget{background:#161616;color:#ccc;border:none;}"
            "QTreeWidget::item:selected{background:#2a1a3a;}"
            "QTreeWidget::item:hover{background:#201030;}"
        )
        self._music_list.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._music_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._music_list.currentItemChanged.connect(self._on_music_selected)
        self._music_list.itemDoubleClicked.connect(self._play_music)
        self._music_list.itemChanged.connect(self._on_music_item_text_changed)
        self._music_list.customContextMenuRequested.connect(self._on_music_ctx_menu)
        root.addWidget(self._music_list, 1)

        sc_music = QShortcut(QKeySequence(Qt.Key.Key_Space), self._music_list)
        sc_music.setContext(Qt.ShortcutContext.WidgetShortcut)
        sc_music.activated.connect(self._play_selected_music)

    # ── Utilitaires ───────────────────────────────────────────────

    def _make_section(self, title: str, color: str, on_add, add_tooltip: str,
                       on_del, del_tooltip: str) -> QFrame:
        """En-tête de section — titre + boutons Ajouter/Supprimer intégrés,
        même emplacement/style que les autres asset finders (assets_finder_panel.py)."""
        f = QFrame()
        f.setFixedHeight(28)
        f.setStyleSheet(f"background:#1e1e1e; border-bottom:1px solid #2a2a2a;")
        hl = QHBoxLayout(f)
        hl.setContentsMargins(8, 0, 4, 0)
        hl.setSpacing(2)
        lbl = QLabel(title)
        lbl.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{color};")
        hl.addWidget(lbl, 1)

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
        self._refresh_sfx()
        self._refresh_music()

    def _refresh_sfx(self):
        self._sfx_list.blockSignals(True)
        self._sfx_list.clear()
        if self._project:
            for sfx in self._project.sfx:
                ap = self._project.asset_abs(sfx.asset) if sfx.asset else None
                icon_key = "sfx" if ap and ap.exists() else "asset_missing"
                item = QTreeWidgetItem([sfx.name])
                item.setIcon(0, _ico(icon_key, COLOR_SFX))
                item.setData(0, Qt.ItemDataRole.UserRole, sfx)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self._sfx_list.addTopLevelItem(item)
        self._sfx_list.blockSignals(False)

    def _refresh_music(self):
        self._music_list.blockSignals(True)
        self._music_list.clear()
        if self._project:
            for m in self._project.music:
                ap = self._project.asset_abs(m.asset) if m.asset else None
                icon_key = "music" if ap and ap.exists() else "asset_missing"
                item = QTreeWidgetItem([m.name])
                item.setIcon(0, _ico(icon_key, COLOR_MUSIC))
                item.setData(0, Qt.ItemDataRole.UserRole, m)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self._music_list.addTopLevelItem(item)
        self._music_list.blockSignals(False)

    # ── Sélection ─────────────────────────────────────────────────

    def _on_sfx_selected(self, current: QTreeWidgetItem, _prev):
        self._music_list.clearSelection()
        sfx = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        if isinstance(sfx, Sfx):
            self.sfx_selected.emit(sfx)

    def _on_music_selected(self, current: QTreeWidgetItem, _prev):
        self._sfx_list.clearSelection()
        music = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        if isinstance(music, Music):
            self.music_selected.emit(music)

    def _play_sfx(self, item: QTreeWidgetItem):
        sfx = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(sfx, Sfx):
            self.sfx_play_requested.emit(sfx)

    def _play_music(self, item: QTreeWidgetItem):
        music = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(music, Music):
            self.music_play_requested.emit(music)

    def _play_selected_sfx(self):
        item = self._sfx_list.currentItem()
        if item:
            self._play_sfx(item)

    def _play_selected_music(self):
        item = self._music_list.currentItem()
        if item:
            self._play_music(item)

    # ── Renommage en place ───────────────────────────────────────────

    def _on_sfx_item_text_changed(self, item: QTreeWidgetItem, _col: int):
        sfx = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(sfx, Sfx):
            return
        new_name = item.text(0).strip()
        if not new_name or new_name == sfx.name:
            self._sfx_list.blockSignals(True)
            item.setText(0, sfx.name)
            self._sfx_list.blockSignals(False)
            return
        self._project.sfx.rename(sfx, new_name)
        self._sfx_list.blockSignals(True)
        item.setText(0, sfx.name)
        self._sfx_list.blockSignals(False)
        self.sfx_selected.emit(sfx)

    def _on_music_item_text_changed(self, item: QTreeWidgetItem, _col: int):
        music = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(music, Music):
            return
        new_name = item.text(0).strip()
        if not new_name or new_name == music.name:
            self._music_list.blockSignals(True)
            item.setText(0, music.name)
            self._music_list.blockSignals(False)
            return
        self._project.music.rename(music, new_name)
        self._music_list.blockSignals(True)
        item.setText(0, music.name)
        self._music_list.blockSignals(False)
        self.music_selected.emit(music)

    # ── Menus contextuels ────────────────────────────────────────────

    def _on_sfx_ctx_menu(self, pos):
        item = self._sfx_list.itemAt(pos)
        if not item:
            return
        self._sfx_list.setCurrentItem(item)
        menu = QMenu(self)
        delete_a = menu.addAction("Supprimer")
        if menu.exec(self._sfx_list.viewport().mapToGlobal(pos)) == delete_a:
            self._del_sfx()

    def _on_music_ctx_menu(self, pos):
        item = self._music_list.itemAt(pos)
        if not item:
            return
        self._music_list.setCurrentItem(item)
        menu = QMenu(self)
        delete_a = menu.addAction("Supprimer")
        if menu.exec(self._music_list.viewport().mapToGlobal(pos)) == delete_a:
            self._del_music()

    # ── Ajout / suppression ───────────────────────────────────────

    def _add_sfx(self):
        if not self._project: return
        name, ok = QInputDialog.getText(self, "Nouveau SFX", "Nom :")
        if ok and name.strip():
            sfx = Sfx(name=name.strip())
            self._project.sfx.append(sfx)
            self._project.save_sfx(sfx)
            self._refresh_sfx()
            last = self._sfx_list.topLevelItem(self._sfx_list.topLevelItemCount() - 1)
            if last:
                self._sfx_list.setCurrentItem(last)

    def _del_sfx(self):
        item = self._sfx_list.currentItem()
        sfx = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not self._project or not isinstance(sfx, Sfx):
            return
        self._project.sfx.delete(sfx)   # supprime le .json sur disque
        self._refresh_sfx()
        self.sfx_deleted.emit()

    def _add_music(self):
        if not self._project: return
        name, ok = QInputDialog.getText(self, "Nouvelle piste", "Nom :")
        if ok and name.strip():
            music = Music(name=name.strip())
            self._project.music.append(music)
            self._project.save_music(music)
            self._refresh_music()
            last = self._music_list.topLevelItem(self._music_list.topLevelItemCount() - 1)
            if last:
                self._music_list.setCurrentItem(last)

    def _del_music(self):
        item = self._music_list.currentItem()
        music = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not self._project or not isinstance(music, Music):
            return
        self._project.music.delete(music)  # supprime le .json sur disque
        self._refresh_music()
        self.music_deleted.emit()


# ──────────────────────────────────────────────────────────────────
#  SoundMixerScreen
# ──────────────────────────────────────────────────────────────────
class SoundMixerScreen(QWidget):
    """Écran complet Sound Mixer : SFX + Music (via SoundFinderPanel) + preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self.setStyleSheet("background:#181818;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setFixedHeight(32)
        hdr.setStyleSheet("background:#1a1a1a; border-bottom:1px solid #2a2a2a;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        lbl = QLabel("SOUND MIXER")
        lbl.setFont(QFont(T.MONO, T.MD2, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#c48b3c;")
        hl.addWidget(lbl)
        hl.addStretch()
        root.addWidget(hdr)

        # Player bar
        self._player = AudioPlayer()
        self._player.setStyleSheet("background:#141414; border-bottom:1px solid #2a2a2a;")
        self._player.setFixedHeight(34)
        root.addWidget(self._player)

        # Splitter principal
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setStyleSheet(SPLITTER_STYLE)
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

        empty_w = QWidget(); empty_w.setStyleSheet("background:#1a1a1a;")
        el = QVBoxLayout(empty_w)
        hint = QLabel("Selectionne ou cree\nun SFX ou une piste\npour editer ses proprietes")
        hint.setFont(QFont(T.MONO, T.MD))
        hint.setStyleSheet("color:#333;")
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
