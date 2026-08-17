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
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import SFX, MUSIC
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
    _HEADER_LABEL = "Music"
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
class SoundMixerScreen(QWidget):
    """Écran complet Sound Mixer : SFX + Music (via AssetFinder) + preview."""

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
        # Deux familles dans un seul finder partagé ; c'est le TYPE de l'asset
        # reçu qui dit quel inspecteur montrer, pas un signal par famille.
        self._finder = AssetFinder("Sound finder", [SFX, MUSIC],
                                   min_width=180, max_width=360)
        self._finder.selected.connect(lambda _kind, a: self._on_asset_selected(a))
        self._finder.emptied.connect(lambda _kind: self._right_stack.setCurrentIndex(0))
        # Double-clic ou Espace : écouter. Le finder ne sait pas ce qu'« activer »
        # veut dire, l'écran si.
        self._finder.activated.connect(lambda _kind, a: self._play_asset(a))
        sc_play = QShortcut(QKeySequence(Qt.Key.Key_Space), self._finder)
        sc_play.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_play.activated.connect(self._finder.activate_current)
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

    def _on_asset_selected(self, asset):
        """Un seul point d'entrée pour les deux familles — le type de l'asset
        choisit l'inspecteur."""
        if isinstance(asset, Sfx):
            self._on_sfx_selected(asset)
        elif isinstance(asset, Music):
            self._on_music_selected(asset)

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
