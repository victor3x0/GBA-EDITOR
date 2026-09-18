"""Le primitif de surlignage partagé (project viewer ET Scene Tree)."""
from __future__ import annotations


def _tree(qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
    tree = QTreeWidget()
    tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
    objs = {}
    for name in ("A", "B", "C"):
        it = QTreeWidgetItem(tree)
        it.setText(0, name)
        it.setData(0, Qt.ItemDataRole.UserRole, name)
        objs[name] = it
    return tree, objs


def test_highlight_matching_selectionne_le_predicat(qapp):
    from PyQt6.QtCore import Qt
    from ui.common.tree_selection import highlight_matching

    tree, _objs = _tree(qapp)
    role = Qt.ItemDataRole.UserRole
    highlight_matching(tree, lambda n: n.data(0, role) in {"A", "C"})

    assert {i.text(0) for i in tree.selectedItems()} == {"A", "C"}


def test_highlight_matching_ne_reemet_pas(qapp):
    from PyQt6.QtCore import Qt
    from ui.common.tree_selection import highlight_matching

    tree, _objs = _tree(qapp)
    fired = []
    tree.itemSelectionChanged.connect(lambda: fired.append(1))
    highlight_matching(tree, lambda n: n.data(0, Qt.ItemDataRole.UserRole) == "B")

    assert {i.text(0) for i in tree.selectedItems()} == {"B"}
    assert fired == []          # blockSignals : aucune réémission (anti-boucle)


def test_highlight_matching_remplace_la_selection(qapp):
    from PyQt6.QtCore import Qt
    from ui.common.tree_selection import highlight_matching

    tree, objs = _tree(qapp)
    objs["A"].setSelected(True)
    highlight_matching(tree, lambda n: n.data(0, Qt.ItemDataRole.UserRole) == "C")

    assert {i.text(0) for i in tree.selectedItems()} == {"C"}   # A déselectionné
