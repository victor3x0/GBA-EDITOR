"""ui/scene_manager/canvas/ — le canvas de scène, découpé par responsabilité.

`scene_canvas.py` (5 227 lignes) part ici en modules frères `canvas_*.py`, du bas
vers le haut : rasterisation → items graphiques → scène → vue → barre d'outils →
contrôleurs. `scene_canvas.py` reste la façade (l'orchestrateur `SceneEditor` +
`CanvasContainer`) et ré-exporte l'API publique (`SceneEditor`, `GBAView`,
`SpriteItem`). Cf. TodoTechnique, A3 (suite).
"""
