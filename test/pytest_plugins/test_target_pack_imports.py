"""Target-selected pack imports and their shared runfiles reach the pytest launcher."""


def test_target_selected_packs_with_shared_dependencies_are_importable():
    import score.itf.core
    import score.itf.packs.localhost.plugin as localhost_plugin
    import score.itf.packs.sim.plugin as sim_plugin

    assert score.itf.core.Session
    assert localhost_plugin.__name__ == "score.itf.packs.localhost.plugin"
    assert sim_plugin.__name__ == "score.itf.packs.sim.plugin"
