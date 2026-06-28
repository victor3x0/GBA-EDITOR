"""Sound Mixer screen — import/preview SFX + Music."""

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSplitter, QListWidget, QListWidgetItem, QFileDialog,
    QSlider, QSpinBox, QCheckBox, QScrollArea, QInputDialog,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QSoundEffect
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, QUrl, pyqtSignal

from ui.theme import T

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.project import Project, Sfx, Music

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
    """Barre de lecture minimale (lecture seule, pas de scrub)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer()
        self._audio  = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(0.8)
        self._current: Optional[Path] = None

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

        vol = QSlider(Qt.Orientation.Horizontal)
        vol.setRange(0, 100); vol.setValue(80); vol.setFixedWidth(70)
        vol.setStyleSheet("QSlider::groove:horizontal{height:4px;background:#333;border-radius:2px;}"
                          "QSlider::handle:horizontal{width:10px;height:10px;margin:-3px 0;"
                          "background:#4caf78;border-radius:5px;}")
        vol.valueChanged.connect(lambda v: self._audio.setVolume(v / 100.0))
        layout.addWidget(vol)

        self._player.playbackStateChanged.connect(self._on_state)

    def load(self, path: Path):
        self._current = path
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._lbl.setText(path.name)
        self._btn.setText("▶")

    def play(self, path: Path):
        self.load(path)
        self._player.play()

    def _toggle(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _stop(self):
        self._player.stop()

    def _on_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._btn.setText("⏸" if playing else "▶")


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

        self._name_lbl = QLabel("")
        self._name_lbl.setFont(QFont(T.MONO, T.MD2, QFont.Weight.Bold))
        self._name_lbl.setStyleSheet("color:#ccc;")
        cl.addWidget(self._name_lbl)

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
        self._name_lbl.setText(sfx.name)
        ap = project.asset_abs(sfx.asset) if sfx.asset else None
        self._file_lbl.setText(ap.name if ap else "Aucun fichier")
        self._vol.setValue(getattr(sfx, "volume", 255))
        self._blocking = False

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

        self._name_lbl = QLabel("")
        self._name_lbl.setFont(QFont(T.MONO, T.MD2, QFont.Weight.Bold))
        self._name_lbl.setStyleSheet("color:#ccc;")
        cl.addWidget(self._name_lbl)

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
        self._name_lbl.setText(music.name)
        ap = project.asset_abs(music.asset) if music.asset else None
        self._file_lbl.setText(ap.name if ap else "Aucun fichier")
        self._loop.setChecked(getattr(music, "loop", True))
        self._vol.setValue(getattr(music, "volume", 255))
        self._blocking = False

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
class SoundMixerScreen(QWidget):
    """Écran complet Sound Mixer : SFX + Music + preview."""

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

        # ── Panneau gauche : listes ───────────────────────────────
        left = QWidget()
        left.setStyleSheet("background:#141414;")
        left.setMinimumWidth(180)
        left.setMaximumWidth(360)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        split.addWidget(left)

        # SFX section
        self._sfx_section = self._make_section("SFX", "#c48b3c")
        ll.addWidget(self._sfx_section)
        self._sfx_list = QListWidget()
        self._sfx_list.setFont(QFont(T.MONO, T.MD))
        self._sfx_list.setStyleSheet(
            "QListWidget{background:#161616;color:#ccc;border:none;}"
            "QListWidget::item:selected{background:#3a2a1a;}"
            "QListWidget::item:hover{background:#252010;}"
        )
        self._sfx_list.currentRowChanged.connect(self._on_sfx_selected)
        self._sfx_list.itemDoubleClicked.connect(self._play_sfx)
        ll.addWidget(self._sfx_list)

        sfx_btns = QFrame()
        sfx_btns.setStyleSheet("background:#141414; border-top:1px solid #2a2a2a;")
        sb = QHBoxLayout(sfx_btns)
        sb.setContentsMargins(4, 2, 4, 2); sb.setSpacing(4)
        btn_add_sfx = QPushButton("+ SFX")
        btn_add_sfx.setFont(QFont(T.MONO, T.SM))
        btn_add_sfx.setFixedHeight(22)
        btn_add_sfx.clicked.connect(self._add_sfx)
        btn_del_sfx = QPushButton("Suppr")
        btn_del_sfx.setFont(QFont(T.MONO, T.SM))
        btn_del_sfx.setFixedHeight(22)
        btn_del_sfx.clicked.connect(self._del_sfx)
        sb.addWidget(btn_add_sfx); sb.addWidget(btn_del_sfx); sb.addStretch()
        ll.addWidget(sfx_btns)

        # Music section
        self._music_section = self._make_section("MUSIC", "#9b7bd5")
        ll.addWidget(self._music_section)
        self._music_list = QListWidget()
        self._music_list.setFont(QFont(T.MONO, T.MD))
        self._music_list.setStyleSheet(
            "QListWidget{background:#161616;color:#ccc;border:none;}"
            "QListWidget::item:selected{background:#2a1a3a;}"
            "QListWidget::item:hover{background:#201030;}"
        )
        self._music_list.currentRowChanged.connect(self._on_music_selected)
        self._music_list.itemDoubleClicked.connect(self._play_music)
        ll.addWidget(self._music_list)

        music_btns = QFrame()
        music_btns.setStyleSheet("background:#141414; border-top:1px solid #2a2a2a;")
        mb_l = QHBoxLayout(music_btns)
        mb_l.setContentsMargins(4, 2, 4, 2); mb_l.setSpacing(4)
        btn_add_music = QPushButton("+ Music")
        btn_add_music.setFont(QFont(T.MONO, T.SM))
        btn_add_music.setFixedHeight(22)
        btn_add_music.clicked.connect(self._add_music)
        btn_del_music = QPushButton("Suppr")
        btn_del_music.setFont(QFont(T.MONO, T.SM))
        btn_del_music.setFixedHeight(22)
        btn_del_music.clicked.connect(self._del_music)
        mb_l.addWidget(btn_add_music); mb_l.addWidget(btn_del_music); mb_l.addStretch()
        ll.addWidget(music_btns)

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

    # ── Utilitaires ───────────────────────────────────────────────

    def _make_section(self, title: str, color: str) -> QFrame:
        f = QFrame()
        f.setFixedHeight(28)
        f.setStyleSheet(f"background:#1e1e1e; border-bottom:1px solid #2a2a2a;")
        hl = QHBoxLayout(f)
        hl.setContentsMargins(8, 0, 8, 0)
        lbl = QLabel(title)
        lbl.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{color};")
        hl.addWidget(lbl)
        return f

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._refresh_sfx()
        self._refresh_music()
        self._right_stack.setCurrentIndex(0)

    def _refresh_sfx(self):
        self._sfx_list.blockSignals(True)
        self._sfx_list.clear()
        if self._project:
            for sfx in self._project.sfx:
                ap = self._project.asset_abs(sfx.asset) if sfx.asset else None
                icon = "♪" if ap and ap.exists() else "○"
                self._sfx_list.addItem(f"{icon}  {sfx.name}")
        self._sfx_list.blockSignals(False)

    def _refresh_music(self):
        self._music_list.blockSignals(True)
        self._music_list.clear()
        if self._project:
            for m in self._project.music:
                ap = self._project.asset_abs(m.asset) if m.asset else None
                icon = "♫" if ap and ap.exists() else "○"
                self._music_list.addItem(f"{icon}  {m.name}")
        self._music_list.blockSignals(False)

    # ── Sélection ─────────────────────────────────────────────────

    def _on_sfx_selected(self, row: int):
        self._music_list.clearSelection()
        if self._project and 0 <= row < len(list(self._project.sfx)):
            sfx = list(self._project.sfx)[row]
            self._sfx_insp.load(sfx, self._project)
            self._right_stack.setCurrentIndex(1)

    def _on_music_selected(self, row: int):
        self._sfx_list.clearSelection()
        if self._project and 0 <= row < len(list(self._project.music)):
            music = list(self._project.music)[row]
            self._music_insp.load(music, self._project)
            self._right_stack.setCurrentIndex(2)

    def _play_sfx(self, item: QListWidgetItem):
        row = self._sfx_list.row(item)
        if self._project and 0 <= row < len(list(self._project.sfx)):
            sfx = list(self._project.sfx)[row]
            ap = self._project.asset_abs(sfx.asset) if sfx.asset else None
            if ap and ap.exists():
                self._player.play(ap)

    def _play_music(self, item: QListWidgetItem):
        row = self._music_list.row(item)
        if self._project and 0 <= row < len(list(self._project.music)):
            music = list(self._project.music)[row]
            ap = self._project.asset_abs(music.asset) if music.asset else None
            if ap and ap.exists():
                self._player.play(ap)

    # ── Ajout / suppression ───────────────────────────────────────

    def _add_sfx(self):
        if not self._project: return
        name, ok = QInputDialog.getText(self, "Nouveau SFX", "Nom :")
        if ok and name.strip():
            sfx = Sfx(name=name.strip())
            self._project.sfx.append(sfx)
            self._project.save_sfx(sfx)
            self._refresh_sfx()
            self._sfx_list.setCurrentRow(self._sfx_list.count() - 1)

    def _del_sfx(self):
        row = self._sfx_list.currentRow()
        if not self._project or row < 0: return
        sfxs = list(self._project.sfx)
        if row < len(sfxs):
            sfx = sfxs[row]
            self._project.sfx.delete(sfx)   # supprime le .json sur disque
            self._refresh_sfx()
            self._right_stack.setCurrentIndex(0)

    def _add_music(self):
        if not self._project: return
        name, ok = QInputDialog.getText(self, "Nouvelle piste", "Nom :")
        if ok and name.strip():
            music = Music(name=name.strip())
            self._project.music.append(music)
            self._project.save_music(music)
            self._refresh_music()
            self._music_list.setCurrentRow(self._music_list.count() - 1)

    def _del_music(self):
        row = self._music_list.currentRow()
        if not self._project or row < 0: return
        musics = list(self._project.music)
        if row < len(musics):
            music = musics[row]
            self._project.music.delete(music)  # supprime le .json sur disque
            self._refresh_music()
            self._right_stack.setCurrentIndex(0)

    def _on_changed(self):
        self._refresh_sfx()
        self._refresh_music()
