"""Plugin discovery and loading for ITF."""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PluginLoader:
    """Discovers and loads ITF plugins dynamically."""

    @staticmethod
    def load_plugin_class(module_path: str) -> type:
        """Load a plugin class from a module path.

        Args:
            module_path: Dotted module path (e.g., "score.itf.plugins.mock_target")
                        or "module.path:ClassName" format

        Returns:
            The plugin class

        Raises:
            ImportError: If module or class cannot be loaded
        """
        # Handle "module.path:ClassName" format
        if ":" in module_path:
            module_name, class_name = module_path.rsplit(":", 1)
        else:
            # Assume last component is the class name (PascalCase + "Plugin")
            module_name = module_path
            parts = module_path.split(".")
            class_name = "".join(p.capitalize() for p in parts[-1].split("_")) + "Plugin"

        logger.debug(f"Loading plugin: {module_name}:{class_name}")

        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ImportError(f"Cannot import module '{module_name}': {exc}")

        try:
            plugin_class = getattr(module, class_name)
        except AttributeError:
            raise ImportError(
                f"Module '{module_name}' has no attribute '{class_name}'"
            )

        return plugin_class

    @staticmethod
    def load_plugins_from_list(plugin_specs: list[str]) -> dict[str, Any]:
        """Load multiple plugins from a list of module paths.

        Args:
            plugin_specs: List of module paths or "module:Class" specs

        Returns:
            Dictionary mapping plugin name to plugin instance

        Example:
            plugins = PluginLoader.load_plugins_from_list([
                "score.itf.plugins.mock_target",
                "score.itf.plugins.mock_ssh",
                "custom.plugin:CustomPlugin",
            ])
        """
        plugins = {}

        for spec in plugin_specs:
            try:
                plugin_class = PluginLoader.load_plugin_class(spec)

                # Instantiate plugin
                plugin_instance = plugin_class()

                # Use contract name as key, or fall back to class name
                if hasattr(plugin_instance, "__contract__"):
                    plugin_name = plugin_instance.__contract__.name.split(".")[-1]
                else:
                    plugin_name = plugin_class.__name__

                plugins[plugin_name] = plugin_instance
                logger.info(f"Loaded plugin: {plugin_name} from {spec}")

            except Exception as exc:
                logger.error(f"Failed to load plugin {spec}: {exc}")
                raise

        return plugins

    @staticmethod
    def load_plugins_from_directory(plugin_dir: Path) -> dict[str, Any]:
        """Load all plugins from a directory.

        Scans for Python files with classes named "*Plugin" and having __contract__.

        Args:
            plugin_dir: Directory containing plugin modules

        Returns:
            Dictionary mapping plugin name to plugin instance
        """
        plugins = {}
        plugin_dir = Path(plugin_dir)

        if not plugin_dir.exists():
            logger.warning(f"Plugin directory does not exist: {plugin_dir}")
            return plugins

        logger.info(f"Scanning plugin directory: {plugin_dir}")

        # Add directory to sys.path so imports work
        plugin_dir_str = str(plugin_dir)
        if plugin_dir_str not in sys.path:
            sys.path.insert(0, plugin_dir_str)

        # Scan for .py files
        for py_file in plugin_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            module_name = py_file.stem

            try:
                module = importlib.import_module(module_name)

                # Look for classes with __contract__
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)

                    if (isinstance(attr, type) and
                        attr_name.endswith("Plugin") and
                        hasattr(attr, "__contract__")):

                        # Instantiate and register
                        plugin_instance = attr()
                        plugin_name = attr.__contract__.name.split(".")[-1]
                        plugins[plugin_name] = plugin_instance

                        logger.info(f"Loaded plugin from directory: {plugin_name}")

            except Exception as exc:
                logger.warning(f"Error loading plugin from {py_file}: {exc}")

        return plugins

    @staticmethod
    def load_plugins_from_entry_points(group: str = "itf.plugins") -> dict[str, Any]:
        """Load plugins registered via entry points.

        Plugins can register themselves by adding to setup.py/pyproject.toml:

        [project.entry-points."itf.plugins"]
        my_plugin = "my_package.plugins:MyPlugin"

        Args:
            group: Entry point group name

        Returns:
            Dictionary mapping plugin name to plugin instance
        """
        plugins = {}

        try:
            if sys.version_info >= (3, 10):
                from importlib.metadata import entry_points
                eps = entry_points()
                if hasattr(eps, "select"):
                    # Python 3.10+
                    group_eps = eps.select(group=group)
                else:
                    # Python 3.9
                    group_eps = eps.get(group, [])
            else:
                import importlib_metadata
                group_eps = importlib_metadata.entry_points().get(group, [])

        except (ImportError, AttributeError):
            logger.debug(f"Entry points not available; skipping {group}")
            return plugins

        logger.debug(f"Loading plugins from entry point group: {group}")

        for ep in group_eps:
            try:
                plugin_class = ep.load()
                plugin_instance = plugin_class()

                if hasattr(plugin_instance, "__contract__"):
                    plugin_name = plugin_instance.__contract__.name.split(".")[-1]
                else:
                    plugin_name = ep.name

                plugins[plugin_name] = plugin_instance
                logger.info(f"Loaded entry point plugin: {plugin_name}")

            except Exception as exc:
                logger.warning(f"Failed to load entry point {ep.name}: {exc}")

        return plugins


def register_plugins(pm: Any, plugins: dict[str, Any]) -> None:
    """Register loaded plugins with a PluginManager.

    Args:
        pm: pluggy PluginManager instance
        plugins: Dictionary mapping plugin name to plugin instance
    """
    for plugin_name, plugin_instance in plugins.items():
        pm.register(plugin_instance, name=plugin_name)
        logger.info(f"Registered plugin: {plugin_name}")
