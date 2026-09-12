"""Geste commun des champs numériques : scroll du panneau et drag horizontal."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QScrollArea, QSpinBox, QWidget

from ui.common.numeric_drag import install_numeric_drag_behavior


def _mouse(kind, point, button=Qt.MouseButton.NoButton, buttons=Qt.MouseButton.NoButton):
    pos = QPointF(point)
    return QMouseEvent(kind, pos, pos, pos, button, buttons, Qt.KeyboardModifier.NoModifier)


def test_drag_horizontal_modifie_la_valeur(qapp):
    install_numeric_drag_behavior(qapp)
    spin = QSpinBox(); spin.setRange(0, 100); spin.setValue(10); spin.resize(120, 28); spin.show()
    edit = spin.lineEdit()
    origin = QPoint(20, 12)

    qapp.sendEvent(edit, _mouse(QMouseEvent.Type.MouseButtonPress, origin,
                                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    qapp.sendEvent(edit, _mouse(QMouseEvent.Type.MouseMove, QPoint(44, 12),
                                buttons=Qt.MouseButton.LeftButton))
    qapp.sendEvent(edit, _mouse(QMouseEvent.Type.MouseButtonRelease, QPoint(44, 12),
                                Qt.MouseButton.LeftButton))

    assert spin.value() == 13


def test_molette_defile_le_conteneur_sans_changer_le_champ(qapp):
    install_numeric_drag_behavior(qapp)
    scroll = QScrollArea(); body = QWidget(); body.resize(120, 600)
    spin = QSpinBox(body); spin.move(0, 400); spin.setValue(10)
    scroll.setWidget(body); scroll.resize(120, 100); scroll.show()
    event = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)

    qapp.sendEvent(spin.lineEdit(), event)

    assert spin.value() == 10
    assert scroll.verticalScrollBar().value() > 0
