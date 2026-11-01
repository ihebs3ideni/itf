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
"""ITF: `import score.itf as itf` is the public API of `score.itf.core`.

One difference: `Session` here loads the optional contract definitions when the library finds any, so a plan
can warn about a deprecated contract. `score.itf.core.Session` is the bare engine; neither needs definitions.
"""

from .core import *  # noqa: F401,F403
from .core import __all__  # noqa: F401
from .core import Session as _Engine
from .core.adapters.definitions import definitions as _definitions


class Session(_Engine):
    """`score.itf.core.Session` with the installed contract definitions; pass `definitions=` to use others."""

    def __init__(self, *args, definitions=None, **options):
        super().__init__(*args, definitions=_definitions() if definitions is None else definitions, **options)
