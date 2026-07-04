"""
Système de plugins GBA Editor.

Un plugin est un dossier dans plugins/ contenant un fichier editor.py.
Il est chargé automatiquement au démarrage via load_all_plugins().

Structure minimale d'un plugin :
    plugins/
      mon_plugin/
        editor.py          ← doit appeler register() et enrichir COMPONENT_REGISTRY

Exemple complet dans plugins/example_path/editor.py.
"""
import importlib
import importlib.util
from pathlib import Path


def load_all_plugins():
    """Charge tous les editor.py trouvés dans les sous-dossiers de plugins/."""
    plugins_dir = Path(__file__).parent
    loaded = []
    errors = []
    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
            continue
        entry = plugin_dir / "editor.py"
        if not entry.exists():
            continue
        module_name = f"plugins.{plugin_dir.name}.editor"
        try:
            spec = importlib.util.spec_from_file_location(module_name, entry)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            loaded.append(plugin_dir.name)
        except Exception as exc:
            errors.append((plugin_dir.name, exc))
    return loaded, errors
