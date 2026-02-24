# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
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
"""Bazel interface for running pytest"""

load("@rules_python//python:defs.bzl", "py_test")
load("@score_itf//bazel/rules:run_as_exec.bzl", "test_as_exec")

def py_itf_test(name, srcs, args = [], data = [], data_as_exec = [], plugins = [], deps = [], tags = [], size = None, timeout = None, flaky = False, env = {}, **kwargs):
    """Bazel macro for running ITF tests.

    This is the single entry point for all ITF test types — standard ITF
    integration tests, SCTF Docker tests, QEMU tests, etc.  Test behavior
    is determined entirely by the *plugins* list.

    Args:
      name: Name of the test target.
      srcs: List of source files for the test.
      args: Additional arguments to pass to ITF.
      data: Data files that will be built for target config.
      data_as_exec: Data files that will be built for exec(host) config.
      plugins: List of py_itf_plugin structs that determine test behavior.
      deps: Additional python dependencies needed for the test.
      tags: Tags forwarded to the test target.
      size: Bazel test size (default: None → Bazel default "medium").
      timeout: Bazel test timeout (default: None → derived from size).
      flaky: Whether the test is flaky.
      env: Environment variables for the test.
      **kwargs: Forwarded to test_as_exec.
    """
    pytest_bootstrap = Label("@score_itf//:main.py")
    pytest_ini = Label("@score_itf//:pytest.ini")

    plugin_deps = []
    for plugin in plugins:
        plugin_deps.append(plugin.py_library)

    plugin_tags = []
    for plugin in plugins:
        plugin_tags.extend(plugin.tags)

    py_test(
        name = "_" + name,
        srcs = [
            pytest_bootstrap,
        ] + srcs,
        main = pytest_bootstrap,
        deps = [
            # Only core ITF dep allowed, rest is resolved by plugins
            "@score_itf//:itf",
        ] + deps + plugin_deps,
        tags = ["manual"] + tags + plugin_tags,
    )

    plugin_enable_args = ["-p score.itf.plugins.core"]
    for plugin in plugins:
        for enabled_plugin in plugin.enabled_plugins:
            plugin_enable_args.append("-p %s" % enabled_plugin)

    plugin_args = []
    for plugin in plugins:
        plugin_args.extend(plugin.args)

    plugin_data = []
    for plugin in plugins:
        plugin_data.extend(plugin.data)

    plugin_data_as_exec = []
    for plugin in plugins:
        plugin_data_as_exec.extend(plugin.data_as_exec)

    data_as_exec = [pytest_ini] + srcs + data_as_exec + plugin_data_as_exec

    test_env = {"PYTHONDONOTWRITEBYTECODE": "1"}
    test_env.update(env)

    test_as_exec_kwargs = {
        "name": name,
        "executable": "_" + name,
        "data_as_exec": data_as_exec,
        "data": data + plugin_data,
        "args": args +
               ["-c $(location %s)" % pytest_ini] +
               [
                   "-p no:cacheprovider",
                   "--show-capture=no",
               ] +
               plugin_enable_args +
               plugin_args +
               ["$(location %s)" % x for x in srcs],
        "env": test_env,
        "tags": tags + plugin_tags,
    }

    if size:
        test_as_exec_kwargs["size"] = size
    if timeout:
        test_as_exec_kwargs["timeout"] = timeout
    if flaky:
        test_as_exec_kwargs["flaky"] = flaky

    test_as_exec_kwargs.update(kwargs)

    test_as_exec(**test_as_exec_kwargs)
