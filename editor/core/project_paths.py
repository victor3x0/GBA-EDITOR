"""core/project_paths.py — où chaque chose vit sur le disque.

Toutes les propriétés dérivent de `self.root` et rien d'autre : ce sont des
chemins CANONIQUES, la seule réponse à « où est-ce rangé ». Il n'y en a jamais
deux pour la même chose : les anciens emplacements ne sont plus lus nulle part
(cf. `core/project.py`, « Aucune migration de format »), donc ils ne se nomment
plus ici.

Une TRANCHE de la classe `Project`, pas un module autonome : les méthodes
ci-dessous s'appellent `self.…` entre elles et avec le reste de `Project`. La
découpe sert la lecture — chaque responsabilité dans son fichier — sans ajouter
le moindre saut d'appel : un mixin est résolu à la construction de la classe,
`project.src_dir` s'écrit exactement comme avant.

**Ce fichier n'importe jamais `core.project`** : ce serait un cycle immédiat,
puisque `project.py` l'importe pour composer la classe.
"""

from pathlib import Path


class ProjectPathsMixin:
    # ── Chemins canoniques ────────────────────────────────────────

    @property
    def assets_dir(self) -> Path:
        """Espace libre utilisateur — PNGs bruts, sons..."""
        return self.root / "assets"

    @property
    def project_dir(self) -> Path:
        """Objets moteur (scenes, actors, sprites, tilesets, backgrounds, scripts)."""
        return self.root / "project"

    @property
    def scenes_dir(self) -> Path:
        return self.project_dir / "scenes"

    @property
    def prefab_dir(self) -> Path:
        return self.project_dir / "prefab"

    @property
    def variables_file(self) -> Path:
        """Globals + constants du projet — project/variables.json (pas de dépendance externe)."""
        return self.project_dir / "variables.json"

    @property
    def texts_file(self) -> Path:
        """Table des textes du joueur — project/texts.json.

        Un seul fichier plutôt qu'un par entrée (contrairement aux palettes) :
        on parle de centaines d'entrées courtes, et un traducteur veut tout voir
        d'un coup. La v0.8 ajoutera `texts.<langue>.json` à côté."""
        return self.project_dir / "texts.json"

    @property
    def ui_layouts_dir(self) -> Path:
        """Mises en page d'UI — project/ui_layouts/*.json.

        Un fichier par mise en page (contrairement aux textes, monolithiques) :
        une mise en page est un objet qu'on renomme, duplique et partage entre
        scènes, donc qui mérite une identité de fichier — comme une palette."""
        return self.project_dir / "ui_layouts"

    @property
    def music_boxes_dir(self) -> Path:
        """MusicBox — project/music_boxes/*.json.

        Avec les données propres au projet, comme les caméras : une boîte
        sonore ne dérive d'aucun fichier importé (ROADMAP v0.8.7)."""
        return self.project_dir / "music_boxes"

    @property
    def jingle_boxes_dir(self) -> Path:
        """JingleBox — project/jingle_boxes/*.json."""
        return self.project_dir / "jingle_boxes"

    @property
    def sound_boxes_dir(self) -> Path:
        """SoundBox — project/sound_boxes/*.json."""
        return self.project_dir / "sound_boxes"

    @property
    def legacy_sound_states_dir(self) -> Path:
        """L'ancien dossier des boîtes à trois machines (avant 2026-08-18).

        Lu une seule fois, à l'ouverture, pour être découpé en trois — puis
        renommé afin que la migration ne se rejoue pas par-dessus le travail
        qui a suivi (cf. Project._migrate_sound_states)."""
        return self.project_dir / "sound_states"

    @property
    def data_tables_dir(self) -> Path:
        """Tables de données — project/data/*.json.

        Un fichier par table, avec les données propres au projet : une table ne
        dérive d'aucun fichier importé. Le dossier porte le mot que le script
        écrit (`data.Objets`) — une seule grammaire du disque au Lua."""
        return self.project_dir / "data"

    @property
    def palettes_dir(self) -> Path:
        """Catalogue de palettes unifié (illimité, partagé OBJ/BG) — project/palettes/*.json."""
        return self.project_dir / "palettes"

    @property
    def sprites_dir(self) -> Path:
        return self.assets_dir / "sprites"

    @property
    def backgrounds_dir(self) -> Path:
        """Dossier des sidecars BackgroundAsset (JSON) — co-localisé avec le PNG
        source dans assets/backgrounds/, même modèle que SpriteAsset
        (assets/sprites/)."""
        return self.assets_dir / "backgrounds"

    @property
    def background_images_dir(self) -> Path:
        """Dossier des images brutes PNG background."""
        return self.assets_dir / "backgrounds"

    @property
    def sfx_dir(self) -> Path:
        return self.assets_dir / "sfx"

    @property
    def music_dir(self) -> Path:
        return self.assets_dir / "music"

    @property
    def fonts_dir(self) -> Path:
        return self.assets_dir / "fonts"

    @property
    def scripts_dir(self) -> Path:
        return self.assets_dir / "scripts"

    @property
    def scripts_actors_dir(self) -> Path:
        return self.scripts_dir / "actors"

    @property
    def scripts_behaviors_dir(self) -> Path:
        return self.scripts_dir / "behaviors"

    @property
    def scripts_scenes_dir(self) -> Path:
        return self.scripts_dir / "scenes"

    @property
    def scripts_cameras_dir(self) -> Path:
        """Un dossier par famille de propriétaire, comme actors/ et scenes/ :
        c'est le CHEMIN qui dit à l'éditeur de script quels points d'entrée
        proposer (cf. ScriptEditor._detect_context)."""
        return self.scripts_dir / "cameras"

    @property
    def build_dir(self) -> Path:
        return self.root / "build"

    @property
    def grit_out_dir(self) -> Path:
        return self.build_dir / "grit_out"

    @property
    def src_dir(self) -> Path:
        return self.build_dir / "src"

    @property
    def obj_dir(self) -> Path:
        return self.build_dir / "obj"

    @property
    def makefile_path(self) -> Path:
        return self.build_dir / "Makefile"

    @property
    def rom_path(self) -> Path:
        return self.build_dir / "rom.gba"

    @property
    def project_file(self) -> Path:
        return self.root / "project.json"
