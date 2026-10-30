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
"""Recipe building blocks: composition is Starlark functions, not copied files."""

load("//bazel:recipe.bzl", "location", "node")

def sshd_container(image, user, mount):
    """A container running sshd: SSH/SFTP for commands and files, the Docker API for the platform.
    Mirrors docker_ssh.yaml, so both recipes resolve to the same plan."""
    return [
        node("platform", "itf.capabilities.platform.instance", using = "docker.instance", config = {
            "image": image,
            "command": None,
            "init": False,
            "environment": "PASSWORD_ACCESS=true,USER_NAME=%s,USER_PASSWORD=%s" % (user, user),
            "ports": "2222/tcp",
            "volumes": "%s:/extra/mount:ro" % mount,
        }),
        node("endpoint", "itf.capabilities.descriptor.endpoint", using = "docker.endpoint", config = {"port": 2222}),
        node("creds", "itf.capabilities.descriptor.credentials", using = "password.credentials", config = {
            "user": user,
            "password": user,
        }),
        node("shell", "itf.capabilities.exec.shell", using = "ssh.shell", config = {"n_retries": 20}),
        node("command", "itf.capabilities.exec.command", using = "ssh.exec"),
        node("process", "itf.capabilities.exec.process", using = "ssh.process"),
        node("files", "itf.capabilities.files.transfer", using = "sftp.files"),
    ]

def dlt_container(image, image_load):
    """A container running dlt-daemon (dlt_base.yaml); `image_load` is the label of the image's oci_load.
    The patched DLT build listens on TCP 13490; the host port is left to the daemon."""
    return [
        node("platform", "itf.capabilities.platform.instance", using = "docker.instance", config = {
            "image": image,
            "bootstrap": location(image_load),
            "ports": "13490/tcp",
        }),
        node("command", "itf.capabilities.exec.command", using = "docker.exec"),
        node("process", "itf.capabilities.exec.process", using = "docker.process"),
        node("files", "itf.capabilities.files.transfer", using = "docker.files"),
        node("dlt_endpoint", "itf.capabilities.descriptor.endpoint", using = "docker.endpoint", config = {"port": 13490}),
    ]
