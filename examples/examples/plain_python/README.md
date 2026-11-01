<!--
*******************************************************************************
Copyright (c) 2026 Contributors to the Eclipse Foundation
See the NOTICE file(s) distributed with this work for additional
information regarding copyright ownership.
This program and the accompanying materials are made available under the
terms of the Apache License Version 2.0 which is available at
https://www.apache.org/licenses/LICENSE-2.0
SPDX-License-Identifier: Apache-2.0
*******************************************************************************
-->

# Plain Python

A composition is a document; pytest is one of its consumers. This script composes a target and uses it without
a test runner:

```python
session = Session(target="target.itf.yaml", run_dir=run_dir)
session.resolve()        # the plan; nothing is built
session.bring_up()       # the planned actions run
session.target.command.exec("echo hello from a plain script")
session.close()          # unwind
```

- `target.itf.yaml` is the same document pytest and `itf` read: roles (`command: local.exec`), each with the
  factory that fills it. The pack comes from the label (`local.exec` loads the `local` pack).
- `Session(overrides=[...])` takes override files the same way.
- `from score.itf import Session` is the session with the installed contract definitions loaded;
  `score.itf.core.Session` is the bare engine and knows none. Neither needs any.
- The pack is the local host (`local`): it runs anywhere and needs no daemon.

```
bazel run //examples/plain_python:run      # from examples/
bazel test //examples/plain_python:run_test
```
