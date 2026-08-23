"""
GBA Editor — gestion de projet

Structure de projet :

  assets/              ← géré par l'utilisateur
    sprites/           ← PNG + JSON sidecar (auto-créé au dépôt)
    backgrounds/       ← PNG + JSON sidecar
    sounds/            ← WAV, MOD
    sfx/               ← effets sonores
    music/             ← musiques
    fonts/             ← polices
    scripts/           ← Lua (pas de sidecar)
      actors/
      scenes/
      cameras/
      behaviors/

  project/             ← géré exclusivement par l'éditeur
    scenes/            ← une scène par JSON (actors inline)
    prefab/            ← templates d'actors (jamais compilés directement)
    cameras/           ← une caméra par JSON (réutilisable entre scènes)

  project.json         ← settings globaux (nom, scène de démarrage, auteur)
  build/               ← 100 % jetable (regénéré à chaque build)

Ce module porte la classe `Project` : ses registres d'assets, la scène active,
les recherches, et l'orchestration save/load. Quatre responsabilités
volumineuses en sont des TRANCHES, chacune dans son fichier — `project_paths`,
`project_variables`, `project_texts`, `project_renames` (cf. la classe).

Autour : le modèle de domaine dans `core.models.*`, l'I/O générique de
collection dans `core.resource_store`, l'orchestration d'encodage d'assets dans
`core.asset_encoding`.

**Une seule forme ÉCRITE, deux formes LUES — et seulement pour la v0.24.**
La règle est longtemps restée « on ne lit qu'UNE forme de chaque fichier, celle
d'aujourd'hui » : sans version diffusée, un changement de format se propageait
en cassant, et un `core/project_migrations.py` a été retiré avec les anciennes
formes qu'il absorbait.

Ce qui a changé (ROADMAP v0.24) : à plusieurs, l'ancienne forme n'est pas dans
le passé, elle est **dans la branche d'à côté**. Un coéquipier qui rebase sur
un fichier écrit avant la bascule doit pouvoir l'ouvrir. Les trois formes
touchées par ce chantier se relisent donc dans les deux écritures, pour de
bon — les couleurs (`#RRGGBB` ou entier BGR555, cf. `core/gba_color.py`) et
les grilles (en rangées ou à plat, cf. `core/project_json.py`). L'écriture,
elle, n'a jamais qu'UNE forme : la nouvelle. Aucun convertisseur à lancer, le
premier enregistrement d'un fichier le réécrit.

Ce n'est pas une porte ouverte à un système de migration : c'est une paire de
lecteurs tolérants, à l'endroit précis où le travail à plusieurs l'exige.

**Ce module ne ré-exporte plus le modèle.** Chaque nom s'importe du fichier qui
le définit — `from core.models.scene import Scene`, jamais à travers ce
module-ci.
"""

import json
import shutil
import copy
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Optional

from core.events import EventEmitter
from core import project_json
from core import asset_encoding
from core.app_paths import IS_FROZEN
from core.resource_store import ResourceStore, atomic_write
from core.palette_presets import seed_default_palettes
from core.project_paths import ProjectPathsMixin
from core.project_variables import ProjectVariablesMixin
from core.project_texts import ProjectTextsMixin
from core.project_renames import ProjectRenameMixin

# ── Le modèle, importé pour l'usage de CE fichier ────────────────────────
# Rien de plus. Ce bloc a longtemps ré-exporté tout le domaine, si bien que
# trente fichiers écrivaient `from core.project import Scene` pour une classe
# définie dans `core/models/scene.py` : deux adresses valides pour un même nom,
# et un lecteur qui ouvrait ce fichier pour trouver `Scene` n'y voyait qu'une
# ligne d'import. **Chaque nom s'importe désormais du module où il est
# DÉFINI** — y compris quand un module voisin se trouve l'avoir sous la main
# (`core.models.scene` importe `OWN_PAL_BANK` pour son propre usage ; il ne
# faut pas le lui emprunter).
from core.models.settings import ProjectSettings, GlobalVar, Constant
from core.models.text import Text
from core.models.palette import PaletteBank, OWN_PAL_BANK
from core.models.sprite import SpriteAsset
from core.models.background import BackgroundAsset
from core.models.audio import Sfx, Music
from core.models.font import Font
from core.models.ui_region import UILayout
from core.models.camera import Camera
from core.models.sound_box import MusicBox, JingleBox, SoundBox
from core.models.data_table import DataTable
from core.models.scene import Prefab, Actor, Scene


# ── Ce qu'une colonne de RÉFÉRENCE peut citer ─────────────────────────────
# Une entrée par type de colonne de `core.models.data_table.COLUMN_REFERENCES`.
# Une table plutôt qu'une suite de `if` : le build compare les deux listes
# (`validator._check_data_column_types`), ce qu'une chaîne de conditions ne
# permet pas. Elle ne dit QUE les noms citables — l'index de chacun en ROM
# appartient à l'émetteur, qui seul connaît l'ordre de ses tables.
DATA_COLUMN_SOURCES = {
    "text":    lambda p: [t.key for t in p.texts],
    "sfx":     lambda p: [s.name for s in p.sfx],
    "music":   lambda p: [m.name for m in p.music],
    "scene":   lambda p: [s.name for s in p.scenes],
    "camera":  lambda p: [c.name for c in p.cameras],
    "font":    lambda p: [f.name for f in p.fonts],
    "palette": lambda p: [b.name for b in p.palettes],
    "region":  lambda p: p.region_names(),
    "image":   lambda p: p.image_names(),
}


# ──────────────────────────────────────────────────────────────────
#  Project — conteneur principal
# ──────────────────────────────────────────────────────────────────

class Project(ProjectPathsMixin, ProjectVariablesMixin, ProjectTextsMixin,
              ProjectRenameMixin):
    """
    Représente un projet GBA ouvert.

    Reste ici ce qui fait de `Project` un tout : ses registres d'assets, la
    scène active, la résolution des chemins d'assets, les recherches, et
    l'orchestration `save`/`load`/`create`/`open`. Quatre responsabilités
    volumineuses vivent dans leur propre fichier, sous forme de TRANCHES de
    cette classe et non de collaborateurs :

      - `core.project_paths`     — où chaque chose vit sur le disque
      - `core.project_variables` — globals et constantes
      - `core.project_texts`     — la table de textes du joueur
      - `core.project_renames`   — renommer et réparer ce qui cite

    Des mixins plutôt que des objets délégués : `project.rename_scene(...)`
    s'écrit exactement comme avant chez ses vingt-deux appelants, et rien n'a
    gagné un saut d'appel — la résolution se fait une fois, à la construction de
    la classe. Le prix assumé : ces fichiers ne sont pas autonomes, ils
    supposent le reste de `Project`.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.settings = ProjectSettings(name=root.name)

        # Ce que le projet ANNONCE, et à quoi il se laisse ENTOURER.
        #
        # Un projet ne connaît pas l'application : il ne sait ni écrire dans une
        # barre de statut, ni suspendre un surveillant de fichiers. Il énonce
        # donc des faits — « ceci a été renommé, tant de références réécrites » —
        # et c'est l'application qui décide de la formulation et du
        # rafraîchissement. Sans abonné (build en ligne de commande, test), tout
        # est silencieux, sans qu'aucun repli n'ait à être écrit.
        #
        # `rename_scope` est l'exception qui ne peut pas être un événement : un
        # renommage doit se dérouler ENTOURÉ de quelque chose (la frappe en cours
        # persistée, le surveillant suspendu), pas suivi d'une notification. Un
        # appelable rendant un gestionnaire de contexte, que l'application
        # remplace ; par défaut il n'entoure rien.
        self.events = EventEmitter()
        self.rename_scope = nullcontext

        self.backgrounds: ResourceStore[BackgroundAsset] = ResourceStore(self.backgrounds_dir, BackgroundAsset)
        self.sprites:     ResourceStore[SpriteAsset]     = ResourceStore(self.sprites_dir, SpriteAsset)
        self.prefabs:     ResourceStore[Prefab]      = ResourceStore(self.prefab_dir, Prefab)
        self.scenes:      ResourceStore[Scene]       = ResourceStore(self.scenes_dir, Scene)
        self.sfx:         ResourceStore[Sfx]         = ResourceStore(self.sfx_dir, Sfx)
        self.music:       ResourceStore[Music]       = ResourceStore(self.music_dir, Music)
        self.fonts:       ResourceStore[Font]        = ResourceStore(self.fonts_dir, Font)
        self.palettes: ResourceStore[PaletteBank] = ResourceStore(self.palettes_dir, PaletteBank)
        self.ui_layouts: ResourceStore[UILayout] = ResourceStore(self.ui_layouts_dir, UILayout)
        self.cameras: ResourceStore[Camera] = ResourceStore(self.cameras_dir, Camera)
        # Trois registres et non un : les trois couches du matériel ne se
        # coordonnent pas, et un appel Lua nomme la boîte à qui il parle.
        self.music_boxes: ResourceStore[MusicBox] = ResourceStore(
            self.music_boxes_dir, MusicBox)
        self.jingle_boxes: ResourceStore[JingleBox] = ResourceStore(
            self.jingle_boxes_dir, JingleBox)
        self.sound_boxes: ResourceStore[SoundBox] = ResourceStore(
            self.sound_boxes_dir, SoundBox)
        self.data_tables: ResourceStore[DataTable] = ResourceStore(self.data_tables_dir, DataTable)

        # Variables globales déclarées explicitement dans le projet
        self.globals:     list[GlobalVar] = []

        # Constantes déclarées explicitement dans le projet (lecture seule)
        self.constants:   list[Constant] = []

        # Table des textes destinés au joueur (traduisibles, cf. models/text.py)
        self.texts:       list[Text] = []

        # Scène active (index dans self.scenes)
        self._active_scene_idx: int = 0


    # ── Scène active ──────────────────────────────────────────────

    @property
    def active_scene(self) -> Optional[Scene]:
        if not self.scenes:
            return None
        idx = max(0, min(self._active_scene_idx, len(self.scenes) - 1))
        return self.scenes[idx]

    def set_active_scene(self, index: int):
        self._active_scene_idx = max(0, min(index, len(self.scenes) - 1))
        if self.active_scene and self.settings.last_scene != self.active_scene.name:
            # Mémorise la scène ouverte pour la prochaine session — surtout PAS
            # start_scene, qui est le point de départ du jeu choisi par l'auteur
            # (cf. ProjectInspector).
            self.settings.last_scene = self.active_scene.name
            self.save_settings()

    # ── Résolution des assets ─────────────────────────────────────

    def asset_abs(self, rel: Optional[str]) -> Optional[Path]:
        if not rel:
            return None
        p = Path(rel)
        return (self.root / p).resolve() if not p.is_absolute() else p

    def asset_rel(self, abs_path: Path) -> str:
        try:
            return str(abs_path.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return f"assets/{abs_path.name}"

    def import_asset(self, src: Path, subdir: str = "") -> Path:
        """
        Copie un fichier dans assets/{subdir}/.
        Retourne le chemin absolu dans le projet.
        """
        dst_dir = self.assets_dir / subdir if subdir else self.assets_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return dst

    # ── Encodage d'assets ───────────────────────────────────────────
    # L'orchestration vit dans `core/asset_encoding.py`, et ses appelants s'y
    # adressent DIRECTEMENT (`asset_encoding.sync_sprite_png(project, chemin)`).
    # Treize méthodes qui ne faisaient que rappeler ce module vivaient ici, au
    # motif qu'elles servaient « depuis plusieurs écrans et le ProjectWatcher » :
    # dix n'avaient aucun appelant et le watcher n'en appelait aucune. Un
    # passe-plat ne rend pas un appel plus lisible, il ajoute un endroit où
    # chercher.

    def commit_all_removals(self):
        """Efface définitivement tous les JSONs en attente (appeler à la fermeture)."""
        for mgr in (self.sprites, self.backgrounds, self.sfx, self.music,
                    self.fonts, self.scenes, self.prefabs, self.ui_layouts,
                    self.palettes, self.cameras, self.music_boxes,
                    self.jingle_boxes, self.sound_boxes):
            mgr.commit_deletes()

    # ── Helpers de lookup ────────────────────────────────────────

    def get_background(self, name: str) -> Optional[BackgroundAsset]:
        return self.backgrounds.get(name)

    def get_sprite(self, name: str) -> Optional[SpriteAsset]:
        return self.sprites.get(name)

    def get_prefab(self, name: str) -> Optional[Prefab]:
        return self.prefabs.get(name)

    def get_palette(self, name: str) -> Optional[PaletteBank]:
        return self.palettes.get(name)

    def get_ui_layout(self, name: str) -> Optional[UILayout]:
        return self.ui_layouts.get(name)

    def get_camera(self, name: str) -> Optional[Camera]:
        return self.cameras.get(name)

    def get_data_table(self, name: str) -> Optional[DataTable]:
        return self.data_tables.get(name)

    def data_column_choices(self, column_type: str) -> list[str]:
        """Les noms qu'une colonne de RÉFÉRENCE peut citer, pour ce projet.

        Ce que cette méthode NE dit pas : à quel index chacun se résout en ROM.
        Ce sont deux questions distinctes — l'éditeur a besoin de la liste à
        proposer, le build de la position dans SA table — et les confondre
        ferait dépendre l'éditeur des ordres d'émission.

        `DATA_COLUMN_SOURCES` couvre exactement `COLUMN_REFERENCES` (vérifié au
        build par `validator._check_data_column_types`) : un type de colonne
        ajouté sans source n'offrirait aucun choix, en silence."""
        source = DATA_COLUMN_SOURCES.get(column_type)
        return list(source(self)) if source else []

    def scene_camera(self, scene) -> Optional[Camera]:
        """Caméra de démarrage d'une scène, ou None si elle emploie la caméra
        par défaut (nom vide) — ou si la référence est cassée, auquel cas le
        validateur le dit et la scène retombe sur le défaut."""
        name = getattr(scene, "camera", "")
        return self.cameras.get(name) if name else None

    def ensure_scene_camera(self, scene) -> Camera:
        """La caméra de cette scène, MATÉRIALISÉE si elle emploie encore le
        défaut implicite.

        C'est le geste « je veux autre chose que l'origine » : personne ne crée
        de caméra d'avance, elle apparaît au premier réglage (cadrage déplacé
        dans le canvas, mode changé dans l'inspecteur). Sans ça, il faudrait
        soit créer une caméra par scène à la création — une liste d'assets
        remplie d'entrées jamais touchées — soit demander à l'auteur d'en créer
        une avant de pouvoir bouger le cadre."""
        cam = self.scene_camera(scene)
        if cam is not None:
            return cam
        base = (getattr(scene, "name", "") or "Camera").strip()
        name, n = base, 2
        while self.cameras.get(name) is not None:
            name, n = f"{base} {n}", n + 1
        cam = Camera(name=name)
        self.cameras.append(cam)
        self.cameras.save(cam)
        scene.camera = name
        return cam

    def camera_users(self, name: str) -> list:
        """Scènes qui DÉMARRENT sur cette caméra. Ne voit pas les activations
        faites par script : celles-là vivent dans le texte d'un `.lua`, comme
        toute citation écrite à la main."""
        return [s for s in self.scenes if getattr(s, "camera", "") == name]

    def ui_backgrounds(self, role: str = "") -> list[BackgroundAsset]:
        """Fonds d'INTERFACE du projet, éventuellement filtrés sur leur rôle
        (`UI_ROLE_NINE` / `UI_ROLE_BG`). C'est ce que propose le menu de fond
        d'un `UIPanel` — d'où le filtre : un cadre étirable et une image posée
        ne s'étalent pas pareil, les mélanger dans une liste unique laisserait
        choisir un cadre sans marges."""
        from core.models.background import KIND_UI
        return [b for b in self.backgrounds
                if b.kind == KIND_UI and (not role or b.ui_role == role)]

    def animated_backgrounds(self) -> list[BackgroundAsset]:
        from core.models.background import KIND_ANIMATED
        return [b for b in self.backgrounds if b.kind == KIND_ANIMATED]

    def scene_ui_layout(self, scene) -> Optional[UILayout]:
        """Mise en page d'une scène, ou None si elle n'en référence aucune (ou
        si la référence est cassée — un nom qui ne résout plus ne doit pas
        faire tomber le chargement, le validateur le signalera)."""
        name = getattr(scene, "ui_layout", "")
        return self.ui_layouts.get(name) if name else None

    def all_regions(self) -> list:
        """[(UILayout, élément de texte)] de tout le projet, ordre STABLE.

        C'est cet ordre qui devient l'index dans la table C `g_ui_regions` —
        même convention que les textes et les polices. Ordre des mises en page,
        puis des slots dans chacune."""
        return [(lay, r) for lay in self.ui_layouts for r in lay.slots]

    def all_images(self) -> list:
        """[(UILayout, UIImage)] de tout le projet — l'index de `g_ui_images`.

        Table séparée de `all_regions`, exactement comme les deux propriétés du
        modèle : un script qui vise une image et un script qui vise un texte ne
        parlent pas de la même chose, et un index partagé obligerait le runtime
        à trier."""
        return [(lay, im) for lay in self.ui_layouts for im in lay.images]

    def all_elements(self) -> list:
        """[(UILayout, élément)] de tout le projet, TOUS types confondus, ordre
        STABLE — l'index de la table de visibilité plate (`UIELEM_*`), la seule
        à couvrir aussi les panels-groupes purs (ni `REGION_*` ni `IMAGE_*`).
        Même convention que `all_regions`/`all_images` : ordre des mises en
        page, puis des éléments dans chacune."""
        return [(lay, e) for lay in self.ui_layouts for e in lay.elements]

    def region_names(self) -> list[str]:
        """Noms de slot de texte du projet entier — l'espace de nommage des
        constantes `REGION_*`, donc ce contre quoi vérifier l'unicité."""
        return [r.name for _, r in self.all_regions()]

    def image_names(self) -> list[str]:
        """Noms d'image du projet entier — l'espace des constantes `IMAGE_*`."""
        return [im.name for _, im in self.all_images()]

    def ui_element_names(self) -> list[str]:
        """TOUS les noms d'élément d'UI du projet. L'unicité se cherche ici et
        pas par type : les deux espaces de constantes (`REGION_*`, `IMAGE_*`)
        sont distincts côté C, mais l'auteur, lui, ne devrait jamais avoir à
        savoir que deux éléments homonymes de types différents sont légaux —
        il les verrait côte à côte dans l'arbre sans pouvoir les distinguer."""
        return [e.name for _lay, e in self.all_elements()]

    def _action_boxes(self, kind: str):
        """Le registre d'actions d'une famille, trié par nom."""
        from core.models.sound_box import KIND_JINGLE
        store = self.jingle_boxes if kind == KIND_JINGLE else self.sound_boxes
        return sorted(store, key=lambda b: b.name)

    def sound_action_names(self, kind: str) -> list[str]:
        """Les actions d'une famille, dans un ordre stable.

        L'espace est COMMUN au projet et non propre à une boîte : une frame
        d'animation cite une action par son nom (« pas »), et elle ne sait pas
        quelle boîte sera active quand elle se jouera. Deux boîtes qui
        déclarent `pas` doivent donc viser la même action — sinon la même
        animation sonnerait ou non selon la boîte, sans que rien ne le dise.

        L'ordre — boîtes par nom, puis l'ordre d'écriture de l'auteur dans
        chacune — devient l'index émis en C. Il est recalculé à chaque build et
        n'est jamais sérialisé : un index rangé dans un fichier est un index à
        tenir d'accord avec sa source (même règle que l'arbre de `UILayout`).
        """
        names: list[str] = []
        for box in self._action_boxes(kind):
            for action in box.actions:
                if action and action not in names:
                    names.append(action)
        return names

    def sound_state_names(self, kind: str) -> list[str]:
        """Les états d'une famille, dans un ordre stable.

        UN espace par famille, et non un espace commun : depuis que les trois
        boîtes sont trois assets, `sound_box.set_state("sable")` dit à qui il
        parle. Deux familles peuvent donc porter le même nom d'état sans que
        rien ne devienne ambigu — ce que le fichier unique interdisait.
        """
        from core.models.sound_box import KIND_MUSIC
        boxes = (sorted(self.music_boxes, key=lambda b: b.name)
                 if kind == KIND_MUSIC else self._action_boxes(kind))
        names: list[str] = []
        for box in boxes:
            for st in box.states:
                if st.name and st.name not in names:
                    names.append(st.name)
        return names

    def sound_trigger_names(self) -> list[str]:
        """Les déclencheurs cités par les arêtes musicales, dans un ordre stable.

        L'ordre devient l'entier que `music_box.trigger(...)` passe au runtime,
        et il est recalculé à chaque build : jamais sérialisé, donc jamais à
        tenir d'accord avec autre chose.
        """
        names: list[str] = []
        for box in sorted(self.music_boxes, key=lambda b: b.name):
            for tr in box.transitions:
                if tr.trigger and tr.trigger not in names:
                    names.append(tr.trigger)
        return names

    def _migrate_box_dirs(self):
        """Renomme les trois dossiers de boîtes vers leur nom au SINGULIER.

        Le pluriel (`musics_boxes`) est tombé avec la v0.8.6, qui aligne le nom
        de la boîte sur celui de l'appel Lua (`music_box.trigger`). Le CONTENU
        des fichiers ne change pas : seul le dossier est renommé, donc rien à
        relire ni à réécrire.

        Le dossier neuf ne l'est jamais avant ce passage — `load()` crée les
        sous-dossiers manquants juste après. S'il existe déjà avec du contenu,
        on ne touche à rien : deux dossiers pleins veulent dire que quelqu'un a
        déjà migré, et écraser serait choisir à sa place.
        """
        for old, new_dir in (("musics_boxes", self.music_boxes_dir),
                             ("jingles_boxes", self.jingle_boxes_dir),
                             ("sounds_boxes", self.sound_boxes_dir)):
            old_dir = self.project_dir / old
            if not old_dir.is_dir():
                continue
            if new_dir.exists() and any(new_dir.iterdir()):
                continue
            try:
                if new_dir.exists():
                    new_dir.rmdir()
                old_dir.rename(new_dir)
            except OSError:
                continue

    def _migrate_sound_states(self):
        """Découpe les anciennes boîtes à trois machines en trois assets.

        Un fichier `project/sound_states/X.json` d'avant le 2026-08-18 portait
        musique, effets et jingles ensemble. Il devient jusqu'à trois fichiers
        du même nom, un par famille — et seulement pour les familles qui
        avaient du contenu : une boîte vide créée par la migration serait un
        asset que personne n'a voulu.

        Le dossier d'origine est ensuite RENOMMÉ, pas effacé : la donnée de
        l'auteur reste sur le disque, et la migration ne se rejoue pas
        par-dessus le travail qui a suivi.
        """
        import json
        import time
        from core.models.sound_box import (
            MusicBox, JingleBox, SoundBox, MusicState, MusicTransition,
            ActionState,
        )
        old_dir = self.legacy_sound_states_dir
        if not old_dir.is_dir():
            return
        files = sorted(old_dir.glob("*.json"))
        for path in files:
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            name = d.get("name", path.stem)
            made = False
            if d.get("music_states"):
                box = MusicBox(
                    name=name, start=d.get("music_start", ""),
                    states=[MusicState(
                        name=s.get("name", "state"), music=s.get("music", ""),
                        loop=s.get("loop", True), level=int(s.get("level", 100)),
                        intensity_target=s.get("intensity_target", "volume"),
                        intensity=int(s.get("intensity", 100)),
                        x=int(s.get("x", 0)), y=int(s.get("y", 0)))
                        for s in d["music_states"]],
                    transitions=[MusicTransition(
                        src=t.get("src", ""), dst=t.get("dst", ""),
                        trigger=t.get("trigger", ""), kind=t.get("kind", "fade"),
                        frames=int(t.get("frames", 30)))
                        for t in d.get("music_transitions", [])])
                self.music_boxes.save(box)
                made = True
            for key, cls, store in (("sfx", SoundBox, self.sound_boxes),
                                    ("jingle", JingleBox, self.jingle_boxes)):
                m = d.get(key) or {}
                if not (m.get("slots") or m.get("states")):
                    continue
                made = True
                store.save(cls(
                    name=name, actions=list(m.get("slots", [])),
                    start=m.get("start", ""),
                    states=[ActionState(name=s.get("name", "state"),
                                        mapping=dict(s.get("mapping", {})))
                            for s in m.get("states", [])]))
            if not made:
                # Une boîte encore vide reste une boîte que l'auteur a créée et
                # NOMMÉE. La perdre en silence serait perdre une intention.
                self.music_boxes.save(MusicBox(name=name))
        if files:
            # Le projet énonce le fait ; c'est l'application qui décide de la
            # formulation et de l'endroit où elle s'affiche.
            self.events._emit(
                "status",
                f"{len(files)} boîte(s) à état découpée(s) en MusicBox / "
                f"JingleBox / SoundBox — ancien dossier conservé sous "
                f"« sound_states.migre »")
        target = old_dir.with_name("sound_states.migre")
        if target.exists():
            target = old_dir.with_name(f"sound_states.migre.{int(time.time())}")
        try:
            old_dir.rename(target)
        except OSError:
            pass

    def ui_layout_users(self, name: str) -> list:
        """Scènes qui référencent cette mise en page. Alimente le badge
        « partagée — N scènes » : éditer une région depuis le canvas modifie un
        objet commun, et le taire casserait N scènes en un geste."""
        return [s for s in self.scenes if getattr(s, "ui_layout", "") == name]

    def instantiate_actor_from_prefab(self, prefab: Prefab, name: str,
                                       x: int = 112, y: int = 72) -> Actor:
        """Crée un Actor inline depuis un Prefab — copie complète de son actor
        racine (composants, palette, réservation affine, notes ; aucun lien
        vivant après la création), reposé aux coordonnées données.

        Un prefab EST son actor racine (cf. core/models/scene.Prefab) :
        copier CET objet plutôt que de relister champ par champ, c'est ce qui
        évite l'ancien bug — `pal_bank`/`affine_transform`/`notes` du prefab
        n'étaient pas reportés sur l'instance, faute d'avoir pensé à les
        ajouter à cette liste."""
        actor = copy.deepcopy(prefab.actor)
        actor.name = name
        actor.prefab_name = prefab.name
        actor.active = True
        actor.x, actor.y = x, y
        return actor

    # ── Build ─────────────────────────────────────────────────────

    def prepare_build(self):
        # Les deux répertoires générés ne sont PLUS effacés ici (ROADMAP
        # v0.24). Le rmtree répondait au bon risque — le Makefile ramasse
        # `src/*.c` au glob, donc un asset retiré du projet laissait un `.c`
        # qui continuait d'être compilé — mais il datait à neuf 32 fichiers
        # identiques d'un build à l'autre, et `make` recompilait tout à chaque
        # itération. Le même risque est couvert en fin de génération par
        # `codegen.build_output.sweep`, qui retire ce que ce build-ci n'a pas
        # produit.
        for d in (self.grit_out_dir, self.src_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.obj_dir.mkdir(parents=True, exist_ok=True)
        self._anon_texts = self.collect_literal_texts()


    def scene_scripts(self, scene) -> tuple[list, bool]:
        """(scripts Lua qu'une scène peut exécuter, en reste-t-il d'opaques ?).

        Le script de la scène, celui de chacun de ses actors, et ceux de TOUS
        les prefabs : un prefab est poolé au niveau projet et `actor.spawn()`
        s'appelle de n'importe où, donc rien ne dit qu'il ne tournera pas ici.

        Le second booléen dit qu'un script échappe à l'analyse : introuvable sur
        disque, ou écrit en C natif (lequel peut appeler n'importe quelle
        fonction du moteur hors catalogue Lua). L'appelant doit en tirer « je ne
        sais pas », jamais « il n'y a rien »."""
        out, opaque = [], False

        def add(rel):
            nonlocal opaque
            if not rel:
                return
            ap = self.asset_abs(rel)
            if ap is None:
                return
            if ap.suffix.lower() == ".lua":
                if ap.exists():
                    out.append(ap)
                else:
                    opaque = True
            else:
                opaque = True      # .c natif : hors de portée de l'analyse

        add(getattr(scene, "script", ""))
        owners = list(getattr(scene, "actors", [])) + list(getattr(self, "prefabs", []))
        for owner in owners:
            comp = owner.get_component("script") if hasattr(owner, "get_component") else None
            if comp and getattr(comp, "active", True):
                add(getattr(comp, "script", ""))
        return out, opaque


    # ── I/O settings globaux ──────────────────────────────────────

    def save_settings(self):
        data = {
            "name":        self.settings.name,
            "start_scene": self.settings.start_scene,
            "last_scene":  self.settings.last_scene,
            "author":      self.settings.author,
            "version":     self.settings.version,
            "backdrop_color": self.settings.backdrop_color,
            "save_slots":  self.settings.save_slots,
            "transition_kind":   self.settings.transition_kind,
            "transition_frames": self.settings.transition_frames,
            "cartridge_mib":     self.settings.cartridge_mib,
            "sfx_sample_rate":   self.settings.sfx_sample_rate,
            "sound_channels":    self.settings.sound_channels,
            "debug_build":       self.settings.debug_build,
            "list_repeat_delay": self.settings.list_repeat_delay,
            "list_repeat_rate":  self.settings.list_repeat_rate,
            # Écrite seulement s'il y a des exceptions : un projet où tout se
            # heurte — le cas de tous ceux d'avant la v0.23 — ne gagne pas une clé.
            **({"collision_disabled_pairs": sorted(self.settings.collision_disabled_pairs)}
               if self.settings.collision_disabled_pairs else {}),
        }
        atomic_write(self.project_file, project_json.dumps(data))

    def load_settings(self):
        if not self.project_file.exists():
            return
        d = json.loads(self.project_file.read_text(encoding="utf-8"))
        self.settings.name        = d.get("name", self.root.name)
        self.settings.start_scene = d.get("start_scene", "")
        # Projets antérieurs à la séparation start_scene/last_scene : start_scene
        # y servait aussi de « dernière scène ouverte ».
        self.settings.last_scene  = d.get("last_scene", self.settings.start_scene)
        self.settings.author      = d.get("author", "")
        self.settings.version     = d.get("version", "0.1")
        # `palette_auto_import_enabled` des anciens project.json est ignoré :
        # le réservoir auto-import est abandonné (cf. ROADMAP.md v0.2), la clé
        # disparaît du fichier à la prochaine sauvegarde.
        self.settings.backdrop_color = d.get("backdrop_color", 0)
        # Un projet antérieur à la v0.5 n'a pas d'emplacement déclaré : il en
        # reçoit un, comme un projet neuf. Sans variable persistante, aucun ne
        # sera émis de toute façon.
        self.settings.save_slots = max(1, int(d.get("save_slots", 1)))
        # Un projet antérieur à la v0.6.2 n'a pas de transition : coupure franche,
        # exactement ce qu'il avait avant. Le fondu se demande, il ne s'impose pas.
        self.settings.transition_kind   = d.get("transition_kind", "none") or "none"
        self.settings.transition_frames = max(1, int(d.get("transition_frames", 16)))
        # Un projet antérieur à la v0.8.4 vise la plus petite cartouche et ne
        # ré-échantillonne rien : les deux défauts ne changent RIEN à ce qui
        # était construit avant.
        from codegen.rom_report import CARTRIDGE_SIZES_MIB, DEFAULT_CARTRIDGE_MIB
        cart = int(d.get("cartridge_mib", DEFAULT_CARTRIDGE_MIB))
        self.settings.cartridge_mib = cart if cart in CARTRIDGE_SIZES_MIB else DEFAULT_CARTRIDGE_MIB
        self.settings.sfx_sample_rate = max(0, int(d.get("sfx_sample_rate", 0)))
        # Antérieur à la v0.8.8 : les 8 canaux qui étaient en dur dans le
        # codegen. Borné par le matériel — le masque de canaux de maxmod est un
        # mot de 32 bits, et sous 4 canaux un module ordinaire ne tient pas.
        from core.models.audio import SOUND_CHANNELS_MIN, SOUND_CHANNELS_MAX
        self.settings.sound_channels = max(
            SOUND_CHANNELS_MIN,
            min(SOUND_CHANNELS_MAX, int(d.get("sound_channels", 8))))
        # Antérieur à la v0.14 : `debug.*` n'existait pas encore, donc rien ne
        # change de comportement pour un projet ancien — défaut à True.
        self.settings.debug_build = bool(d.get("debug_build", True))
        # Antérieur à la v0.22 : les valeurs qui étaient en dur dans
        # l'émetteur, donc aucun changement de comportement.
        self.settings.list_repeat_delay = max(0, int(d.get("list_repeat_delay", 10)))
        self.settings.list_repeat_rate  = max(0, int(d.get("list_repeat_rate", 4)))
        # Absente = aucune exception, donc tout se heurte : le comportement
        # d'avant la v0.23, à l'identique.
        self.settings.collision_disabled_pairs = list(
            d.get("collision_disabled_pairs") or [])







    # ── Raccourcis de sauvegarde par objet (delegue au ResourceStore) ──

    def save_scene(self, scene: Scene):                    self.scenes.save(scene)
    def save_prefab(self, prefab: Prefab):                 self.prefabs.save(prefab)
    def save_sprite(self, sprite: SpriteAsset):           self.sprites.save(sprite)
    def save_background(self, bg: BackgroundAsset):       self.backgrounds.save(bg)
    def save_sfx(self, sfx: Sfx):                         self.sfx.save(sfx)
    def save_music(self, music: Music):                   self.music.save(music)

    # ── Sauvegarde / chargement global ────────────────────────────

    def save(self):
        self.save_settings()
        self.save_variables()
        self.save_texts()
        self.sprites.save_all()
        self.sfx.save_all()
        self.music.save_all()
        self.fonts.save_all()
        self.ui_layouts.save_all()
        self.cameras.save_all()
        self.music_boxes.save_all()
        self.jingle_boxes.save_all()
        self.sound_boxes.save_all()
        self.data_tables.save_all()
        # `palettes` manquait ici — seule des quatorze collections. Sans
        # conséquence au quotidien (l'éditeur de palettes écrit chaque banque
        # dès l'édition, cf. palette_grid_panel), mais un « enregistrer le
        # projet » qui saute une collection est un piège à l'échelle d'une
        # équipe, et c'est ce qui a laissé les fichiers de palettes dans
        # l'ancienne forme écrite quand tout le reste avait basculé (v0.24).
        self.palettes.save_all()
        self.backgrounds.save_all()
        self.prefabs.save_all()
        self.scenes.save_all()

    def load_scenes(self):
        """Charge les scènes, puis rouvre sur la dernière éditée.

        Repli : la scène de démarrage du jeu, qui tenait ce rôle avant la
        séparation des deux champs."""
        self.scenes.load()
        restore = self.settings.last_scene or self.settings.start_scene
        if restore:
            for i, s in enumerate(self.scenes):
                if s.name == restore:
                    self._active_scene_idx = i
                    break

    def load(self):
        # S'assurer que tous les sous-dossiers existent
        for sub in ("project/scenes", "project/prefab",
                    "project/palettes", "project/ui_layouts",
                    "project/cameras",
                    "project/music_boxes",
                    "project/jingle_boxes",
                    "project/sound_boxes",
                    "assets/sprites", "assets/backgrounds",
                    "assets/scripts", "assets/scripts/actors",
                    "assets/scripts/scenes", "assets/scripts/behaviors",
                    "assets/scripts/cameras",
                    "assets/sfx", "assets/music", "assets/fonts"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

        # Chaque registre est suivi de son rattrapage (cf. asset_encoding,
        # section « Rattrapage à l'ouverture ») : un fichier déposé éditeur
        # fermé n'a été vu par aucun watcher, on repasse une fois ici.
        self.load_settings()
        self.load_variables()
        # Une variable ajoutée à la main dans variables.json n'a pas d'id, et
        # tout ce qui référence une variable en a besoin : attribution AVANT
        # que quoi que ce soit ne tente de résoudre.
        if self.assign_variable_ids():
            self.save_variables()
        self.load_texts()
        self.palettes.load()
        seed_default_palettes(self)
        self.sprites.load()
        asset_encoding.reconcile_sprites(self)
        self.backgrounds.load()
        asset_encoding.reconcile_backgrounds(self)
        self.sfx.load()
        self.music.load()
        asset_encoding.reconcile_sfx_and_music(self)
        self.fonts.load()
        asset_encoding.reconcile_fonts(self)
        # Avant les scènes : une scène référence sa mise en page et ses prefabs
        # par nom, et doit les trouver déjà chargés.
        self.ui_layouts.load()
        self.cameras.load()
        self._migrate_box_dirs()
        self._migrate_sound_states()
        self.music_boxes.load()
        self.jingle_boxes.load()
        self.sound_boxes.load()
        self.data_tables.load()
        self.prefabs.load()
        self.load_scenes()

    # ── Création / ouverture ──────────────────────────────────────

    @classmethod
    def create(cls, root: Path, name: str) -> "Project":
        """Crée un nouveau projet vide avec la structure de dossiers."""
        root.mkdir(parents=True, exist_ok=True)
        for sub in (
            "assets/sprites",
            "assets/backgrounds",
            "assets/sounds",
            "assets/sfx",
            "assets/music",
            "assets/fonts",
            "assets/scripts",
            "assets/scripts/actors",
            "assets/scripts/scenes",
            "assets/scripts/behaviors",
            "project/scenes",
            "project/prefab",
        ):
            (root / sub).mkdir(parents=True, exist_ok=True)

        proj = cls(root)
        proj.settings.name = name

        # Peupler le catalogue de palettes par défaut dès la création (sinon
        # le seeding n'a lieu qu'au prochain load() et les palettes n'apparaissent
        # qu'après un redémarrage).
        seed_default_palettes(proj)

        # Créer une scène de démarrage par défaut
        default_scene = Scene(name="Scene_01")
        proj.scenes.append(default_scene)
        proj.settings.start_scene = "Scene_01"
        proj.settings.last_scene  = "Scene_01"

        proj.save()

        # Launcher .bat — ouvre l'éditeur directement sur ce projet.
        # Figé (exe distribué) : appeler l'exe. Depuis les sources : passer
        # par l'interpréteur courant. L'ancienne version écrivait toujours
        # `python editor\main.py` depuis la racine du repo, ce qui ne peut
        # pas marcher chez quelqu'un qui n'a que l'exe.
        bat_path = root / f"{name}.bat"
        if IS_FROZEN:
            cmd = f"\"{Path(sys.executable)}\" --project \"{root}\""
        else:
            editor_root = Path(__file__).resolve().parents[2]
            cmd = (f"cd /d \"{editor_root}\"\r\n"
                   f"\"{Path(sys.executable)}\" editor\\main.py --project \"{root}\"")
        bat_path.write_text(
            f"@echo off\r\n{cmd}\r\n",
            encoding="utf-8"
        )

        return proj

    @classmethod
    def open(cls, root: Path) -> "Project":
        """Ouvre un projet existant."""
        proj = cls(root)
        proj.load()
        return proj
