# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""ITF recipes in Starlark (DR-003): itf_setup/itf_init as data, declared as a Bazel target.

    load("@score_itf//bazel:recipe.bzl", "itf_recipe", "location", "node")

    itf_recipe(
        name = "bench",
        nodes = [node("platform", "itf.capabilities.platform.instance", using = "docker.instance",
                      config = {"image": "ubuntu:24.04", "bootstrap": location("//images:load")})],
        goals = ["itf.states.platform.up"],
        plugins = ["@score_itf//score/itf/packs/docker"],
    )

    py_itf_test(name = "test", srcs = ["test_x.py"], recipe = ":bench")

The recipe stands in for the declarative hooks only. A conftest in the test's srcs keeps
`itf_verify`, `itf_teardown`, fixtures and bench-local actions, and may add to or override the
recipe with its own `itf_setup`/`itf_init` (the root conftest outranks every plugin).
`itf_recipe` also defines `<name>_plan`, a test resolving both gates without constructing anything.
"""

load("@rules_python//python:defs.bzl", "PyInfo")
load("@score_itf//bazel:py_itf_plugin.bzl", "PyItfPluginInfo")
load("@score_itf//bazel:py_itf_test.bzl", "py_itf_test")
load("@score_itf//bazel:recipe_info.bzl", "ItfRecipeInfo")

def location(label):
    """A config value naming a Bazel-built file: its runfiles path, the file in the test's runfiles."""
    return struct(itf_location = label)

def node(name, contract = None, using = None, bind = None, config = None):
    """One node: `name` is how tests reach it (`target.<name>`)."""
    entry = {"name": name}
    for key, value in [("contract", contract), ("using", using), ("bind", bind), ("config", config)]:
        if value != None:
            entry[key] = value
    return entry

def relation(state, requires = [], invalidates = []):
    """Adds `requires`/`invalidates` to the action producing `state`."""
    return {"state": state, "requires": requires, "invalidates": invalidates}

def assumption(token, owner = "", reason = ""):
    """A state taken as holding, visibly: prefer a probe."""
    return {"token": token, "owner": owner, "reason": reason}

def state(token, using):
    """Which loaded action delivers `token` when several could."""
    return {"token": token, "using": using}

def scope(nodes = [], aliases = {}, rebinds = [], goals = [], relations = [], assumptions = []):
    """A device scope: tests reach it as `target.<scope name>`. `aliases`: {name: ".root_node"}."""
    return struct(
        setup = {"nodes": nodes, "aliases": [{"name": k, "target": v} for k, v in aliases.items()], "rebinds": rebinds},
        init = {"goals": goals, "relations": relations, "assumptions": assumptions},
    )

def _located(value, data):
    """Replace location() structs in a config value by $(rootpath) and collect their labels."""
    if type(value) == "struct" and hasattr(value, "itf_location"):
        label = str(native.package_relative_label(value.itf_location))
        if label not in data:
            data.append(label)
        return "$(rootpath %s)" % label
    return value

def _pruned(mapping):
    return {k: v for k, v in mapping.items() if v}

def _itf_recipe_impl(ctx):
    targets = list(ctx.attr.data) + list(ctx.attr.extends)
    document = ctx.actions.declare_file(ctx.label.name + ".itf.json")
    ctx.actions.write(document, ctx.expand_location(ctx.attr.document, targets = targets))

    plugins = list(ctx.attr.plugins)
    runfiles = ctx.runfiles(files = [document] + ctx.files.data)
    for target in ctx.attr.data + ctx.attr.plugins:
        runfiles = runfiles.merge(target[DefaultInfo].default_runfiles)
    for base in ctx.attr.extends:
        info = base[ItfRecipeInfo]
        runfiles = runfiles.merge(info.runfiles)
        plugins += [p for p in info.plugins if p not in plugins]

    py_infos = [p[PyInfo] for p in plugins if PyInfo in p]
    return [
        DefaultInfo(files = depset([document]), runfiles = runfiles),
        ItfRecipeInfo(document = document, plugins = plugins, runfiles = runfiles),
        # So py_itf_test's binary imports the packs the recipe names.
        PyInfo(
            transitive_sources = depset(transitive = [i.transitive_sources for i in py_infos]),
            imports = depset(transitive = [i.imports for i in py_infos]),
        ),
    ]

_itf_recipe = rule(
    doc = "Writes a recipe document and carries the packs and files it needs; see itf_recipe.",
    implementation = _itf_recipe_impl,
    attrs = {
        "document": attr.string(mandatory = True),
        "data": attr.label_list(allow_files = True),
        "extends": attr.label_list(providers = [ItfRecipeInfo]),
        "plugins": attr.label_list(providers = [PyItfPluginInfo]),
    },
)

def itf_recipe(
        name,
        nodes = [],
        aliases = {},
        rebinds = [],
        scopes = {},
        goals = [],
        relations = [],
        assumptions = [],
        states = [],
        extends = [],
        plugins = [],
        conftest = None,
        plan_test = True,
        visibility = None,
        **kwargs):
    """A recipe: what exists (`nodes`, `aliases`, `scopes`) and what must hold (`goals`, ...).

    Args:
        name: Target name; `py_itf_test(recipe = ":<name>")` uses it.
        nodes: node(...) entries of the root scope.
        aliases: {name: "scope.node"} aliases in the root scope.
        rebinds: [{"name": ..., "slots": {...}}] entries.
        scopes: {scope name: scope(...)} device scopes.
        goals: States the root scope must reach.
        relations: relation(...) entries.
        assumptions: assumption(...) entries.
        states: state(...) entries choosing a deliverer.
        extends: itf_recipe targets this one derives from (merged like YAML `extends`).
        plugins: py_itf_plugin targets (packs) the recipe's providers and actions come from.
        conftest: A conftest whose hooks join the `<name>_plan` check (bench-local actions).
        plan_test: False for an incomplete base that only other recipes extend.
        visibility: Visibility of the recipe and its plan test.
        **kwargs: Forwarded to the `<name>_plan` test (tags, target_compatible_with, ...).
    """
    data = []
    root_nodes = [dict(n, config = {k: _located(v, data) for k, v in n["config"].items()}) if "config" in n else n for n in nodes]
    setup_scopes = {}
    init_scopes = {}
    for scope_name, s in scopes.items():
        setup_scopes[scope_name] = _pruned(dict(
            s.setup,
            nodes = [dict(n, config = {k: _located(v, data) for k, v in n["config"].items()}) if "config" in n else n for n in s.setup["nodes"]],
        ))
        init_scopes[scope_name] = _pruned(s.init)
    parents = [str(native.package_relative_label(e)) for e in extends]
    document = _pruned({
        "extends": ["$(rootpath %s)" % p for p in parents],
        "setup": _pruned({
            "nodes": root_nodes,
            "aliases": [{"name": k, "target": v} for k, v in aliases.items()],
            "rebinds": rebinds,
            "scopes": _pruned(setup_scopes),
        }),
        "init": _pruned({
            "goals": goals,
            "relations": relations,
            "assumptions": assumptions,
            "states": states,
            "scopes": _pruned(init_scopes),
        }),
    })
    _itf_recipe(
        name = name,
        document = json.encode_indent(document, indent = "  "),
        data = data,
        extends = parents,
        plugins = plugins,
        visibility = visibility,
    )
    if not plan_test:
        return
    py_itf_test(
        name = name + "_plan",
        srcs = [Label("@score_itf//bazel:recipe_plan_test.py")] + ([conftest] if conftest else []),
        args = ["--itf-plan", "--itf-strict-shapes"],
        recipe = ":" + name,
        visibility = visibility,
        **kwargs
    )
