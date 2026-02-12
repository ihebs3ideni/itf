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
"""Bazel interface for running SCTF tests via pytest"""

load("@itf_pip//:requirements.bzl", "requirement")
load("@rules_python//python:defs.bzl", "py_test")

def py_sctf_test(
        name,
        srcs,
        main = None,
        data = None,
        deps = None,
        extra_tags = None,
        args = None,
        env = None,
        timeout = "moderate",
        flaky = False,
        backend = "bwrap"):
    """Bazel macro for running SCTF tests.

    Args:
      name: Name of the test target.
      srcs: List of source files for the test.
      main: Main entry point for the test (optional).
      data: Data files needed for the test.
      deps: List of additional dependencies for the test.
      extra_tags: Additional tags to add to the test target.
      args: Additional arguments to pass to SCTF.
      env: Environment variables to set for the test.
      timeout: Timeout setting for the test.
      flaky: If true, marks the test as flaky.
      backend: Sandbox backend: "bwrap" (default), "docker", or "none".
    """
    pytest_ini = Label("@score_itf//score/sctf:pytest.ini")

    data = [] if data == None else data

    # User provided dependencies, extended by the framework itself
    deps = [] if deps == None else [native.package_relative_label(d) for d in deps]

    deps.append(Label("@score_itf//score/sctf:sctf"))

    args = [] if args == None else args
    args = args + ["--sctf-backend=%s" % backend]

    plugins = ["score.sctf.plugins.basic_sandbox"]
    plugin_args = ["-p %s" % name for name in plugins]

    extra_env = {}
    if env:
        extra_env.update(env)

    tags = ["sctf"]

    # Bazel default to one core per test, whereas SCTF tests spawn several processes
    # Increasing reserved cores seems to reduce flakiness in CI
    tags.append("cpu:2")

    if backend == "docker":
        tags.append("requires-docker")

    if extra_tags:
        tags.extend(extra_tags)

    py_test(
        name = name,
        srcs = srcs,
        main = main,
        data = [pytest_ini] + data,
        deps = deps + [
            requirement("pytest"),
            requirement("psutil"),
            requirement("rpdb"),
            requirement("tenacity"),
            requirement("pytest_timeout"),
        ]
        if backend == "docker":
            deps = deps + [requirement("docker")],
        args = ["-c $(location %s)" % pytest_ini] + args + plugin_args,
        env = extra_env,
        size = "large",
        timeout = timeout,
        tags = tags,
        flaky = flaky,
    )
