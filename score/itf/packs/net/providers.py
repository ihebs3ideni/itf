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
"""Static descriptor providers: where a service listens and how to log in."""

from score.itf.core import provides

from .descriptors import Credentials, Endpoint, KeyCredentials, PasswordCredentials


@provides("itf.capabilities.descriptor.endpoint", name="static.endpoint", config_schema=Endpoint)
def static_endpoint(config: dict[str, object]) -> Endpoint:
    return Endpoint(config["host"], config["port"])


@provides("itf.capabilities.descriptor.credentials", name="key.credentials", config_schema=KeyCredentials)
def key_credentials(config: dict[str, object]) -> Credentials:
    return Credentials(config["user"], key_path=config["key_path"])


@provides("itf.capabilities.descriptor.credentials", name="password.credentials", config_schema=PasswordCredentials)
def password_credentials(config: dict[str, object]) -> Credentials:
    """An empty password is a valid login on many images (e.g. root on a development build)."""
    return Credentials(config["user"], password=config.get("password", ""))
