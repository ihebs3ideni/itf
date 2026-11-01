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
"""`itf_target`: a composition, validated during the build.

    load("@score_itf//:defs.bzl", "itf_target", "py_itf_test")

    itf_target(
        name = "ecu",
        src = "ecu.itf.yaml",
        overrides = ["lab2.itf.yaml"],
        packs = ["@score_itf//score/itf/packs/docker", "@score_itf//score/itf/packs/ssh"],
    )

    py_itf_test(name = "smoke", srcs = ["test_smoke.py"], target = ":ecu")

`bazel build :ecu` loads the packs, compiles the composition exactly as a test run does (both gates, strict
shapes, nothing constructed), writes `ecu.plan.json` and fails, printing ITF's diagnostics, when the composition
does not compile or when a factory label names a pack that is not in `packs`. `py_itf_test(target = ":ecu")` runs
tests against it; its pack dependencies are the `packs` listed here.
"""

load("@rules_python//python:defs.bzl", "PyInfo", "py_binary")
load("@score_itf//bazel:py_itf_plugin.bzl", "PyItfPluginInfo")
load("@score_itf//bazel:target_info.bzl", "ItfTargetInfo")

def _pack_name(module):
    """`score.itf.packs.docker.plugin` -> `docker`: the pack is the package of its plugin module."""
    parts = module.split(".")
    return parts[-2] if len(parts) >= 2 and parts[-1] == "plugin" else parts[-1]

def _file_of(target, name):
    files = target[DefaultInfo].files.to_list()
    if len(files) != 1:
        fail("itf_target files: {} ({}) must be exactly one file, got {}".format(name, target.label, len(files)))
    return files[0]

def _placeholder(label):
    """The label as a plain path (`examples/docker/image_load`): what `${NAME}` reads while compiling."""
    parts = [p for p in [label.workspace_root, label.package, label.name] if p]
    return "/".join(parts)

def _itf_target_impl(ctx):
    out = ctx.actions.declare_file(ctx.label.name + ".plan.json")
    files = {name: _file_of(target, name) for target, name in ctx.attr.files.items()}
    names = []
    for pack in ctx.attr.packs:
        for module in pack[PyItfPluginInfo].enabled_plugins:
            if module.endswith(".plugin") and _pack_name(module) not in names:
                names.append(_pack_name(module))

    args = ctx.actions.args()
    args.add("--target", ctx.file.src)
    args.add_all(ctx.files.overrides, before_each = "--override")
    args.add_all(names, before_each = "--pack")
    conftests = [f for f in ctx.files.srcs if f.basename == "conftest.py"]
    args.add_all(conftests, before_each = "--conftest")
    args.add_all(ctx.files.contracts, before_each = "--contracts")
    args.add("--out", out)

    # The compile constructs nothing and never opens these files, so `${NAME}` is the file's label there: checking
    # a composition never builds or downloads what it points at. Only a test run pulls the files in.
    compile_env = dict(ctx.attr.env)
    compile_env.update({name: _placeholder(target.label) for target, name in ctx.attr.files.items()})
    ctx.actions.run(
        executable = ctx.attr.planner[DefaultInfo].files_to_run,
        arguments = [args],
        env = compile_env,
        inputs = [ctx.file.src] + ctx.files.overrides + ctx.files.data + conftests + ctx.files.contracts,
        outputs = [out],
        mnemonic = "ItfTarget",
        progress_message = "Compiling the ITF composition %{label}",
    )

    runfiles = ctx.runfiles(files = [ctx.file.src, out] + ctx.files.overrides + ctx.files.data + files.values())
    for target in ctx.attr.files:
        runfiles = runfiles.merge(target[DefaultInfo].default_runfiles)
    test_env = dict(ctx.attr.env)
    test_env.update({name: f.short_path for name, f in files.items()})
    for pack in ctx.attr.packs:
        runfiles = runfiles.merge(pack[PyItfPluginInfo].plugin_runfiles).merge(pack[DefaultInfo].default_runfiles)
    packs_py = [p[PyInfo] for p in ctx.attr.packs if PyInfo in p]
    return [
        DefaultInfo(files = depset([out]), runfiles = runfiles),
        ItfTargetInfo(
            document = ctx.file.src,
            overrides = ctx.files.overrides,
            packs = ctx.attr.packs,
            plan = out,
            runfiles = runfiles,
            env = test_env,
        ),
        PyInfo(
            transitive_sources = depset(transitive = [p.transitive_sources for p in packs_py]),
            imports = depset(transitive = [p.imports for p in packs_py]),
        ),
    ]

_itf_target = rule(
    doc = "Compiles a composition during the build; see itf_target.",
    implementation = _itf_target_impl,
    attrs = {
        "src": attr.label(mandatory = True, allow_single_file = [".yaml", ".yml", ".json"], cfg = "exec"),
        "overrides": attr.label_list(allow_files = [".yaml", ".yml", ".json"], cfg = "exec"),
        "data": attr.label_list(allow_files = True, cfg = "exec"),
        "packs": attr.label_list(providers = [PyItfPluginInfo], cfg = "exec"),
        "srcs": attr.label_list(allow_files = [".py"], cfg = "exec"),
        "contracts": attr.label_list(allow_files = True, cfg = "exec"),
        "env": attr.string_dict(),
        "files": attr.label_keyed_string_dict(allow_files = True),
        "planner": attr.label(mandatory = True, executable = True, cfg = "exec"),
    },
)

def itf_target(name, src, overrides = [], packs = [], data = [], srcs = [], contracts = [], env = {}, files = {}, **kwargs):
    """A composition, compiled at build time: `<name>.plan.json`.

    Args:
        name: Target name; `py_itf_test(target = ":<name>")` uses it.
        src: The composition (YAML).
        overrides: Override files: compositions holding only what changes, merged by role in this order.
        packs: Pack targets (`py_itf_plugin`) the composition's factory labels may name; a label naming another
            pack fails the build.
        data: Files the composition includes (`include:`), relative to `src`.
        srcs: A test's sources; the `conftest.py` among them is loaded as a root, so the project's own
            capabilities and actions take part in the plan.
        contracts: Directories of contract definitions (optional; loaded for deprecation warnings).
        env: Values for the composition's `${NAME}` references that are not built files; used when compiling
            and passed to every test of this target.
        files: Built files the composition refers to, as `{"NAME": "//label"}`: every test of this target gets the
            file in its runfiles and `${NAME}` set to its path. This is the one place a composition's built files
            are named; tests need no `data` or `$(location)`. While compiling, `${NAME}` is the label written as a
            path (nothing is opened), so the check never builds the file; a target whose files cannot be built on this host still
            cannot be requested explicitly, as for its tests.
        **kwargs: Forwarded to the rule (visibility, tags, ...).
    """
    py_binary(
        name = name + ".planner",
        srcs = [Label("@score_itf//bazel:itf_plan.py")],
        main = Label("@score_itf//bazel:itf_plan.py"),
        deps = [Label("@score_itf//:itf")] + packs,
        tags = ["manual"],
        visibility = ["//visibility:private"],
        testonly = kwargs.get("testonly", False),
    )
    _itf_target(
        name = name,
        src = src,
        overrides = overrides,
        packs = packs,
        data = data,
        srcs = srcs,
        contracts = contracts,
        env = env,
        files = _by_label(files),
        planner = ":" + name + ".planner",
        **kwargs
    )

def _by_label(files):
    """`{"NAME": label}` as the rule attribute wants it, `{label: "NAME"}`; one label serves one name."""
    by_label = {}
    for name, label in files.items():
        if label in by_label:
            fail("itf_target files: {} names {} and {}; give each built file one name".format(label, by_label[label], name))
        by_label[label] = name
    return by_label
