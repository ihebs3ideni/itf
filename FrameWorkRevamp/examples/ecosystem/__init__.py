"""Independent ecosystem plugins.

Each module here is a self-contained pytest plugin. The target plugin knows
nothing about the capability plugins, and the capability plugins know nothing
about the target -- they agree ONLY on string contracts. The engine composes
them at runtime by matching ``requires``/``provides``.
"""
