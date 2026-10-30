# YAML recipes

`load_setup(ctx, source)` and `load_init(ctx, source)` translate a document into the same `ctx`
calls a Python recipe makes; `source` is a path, a dict, or inline YAML/JSON text. `--itf-config`
(or `ITF_CONFIG`) hands a path or text to a recipe that reads `os.environ["ITF_CONFIG"]`.

```yaml
extends:                              # relative to this file; ancestors first, this file last
  - base.yaml
setup:
  contracts:                          # rarely needed: packs publish their own
    - token: <token>
      gives: <members>
      needs: <slots>
  nodes:                              # root scope: shared bench resources
    - name: platform                  # target.platform in tests
      contract: itf.capabilities.platform.instance
      using: docker.instance          # provider name (catalog: v_capability_providers)
      bind:                           # only when a slot has several candidates in the scope
        <slot>: <node name>
      config:                         # provider_config; flat scalars only
        image: ubuntu:24.04
  aliases:                            # target: ".name" (root) or "scope.name"
    - name: <name>
      target: <target>
  rebinds:
    - name: <name>
      slots:
        <slot>: <node name>
  scopes:
    gw:                               # a device scope: target.gw.<node>, states gw:<token>
      nodes:
        - name: <name>                # same shape as the root nodes
      aliases:                        # share a root node; nothing falls back
        - name: capture
          target: .capture
init:
  states:                             # pick the action delivering a token when several are loaded
    - token: <token>
      using: <action>
  goals:
    - itf.states.shell.open
  relations:                          # add to the producing action's own requires/invalidates
    - state: itf.states.platform.up
      requires:                       # open the console before booting: records the boot
        - itf.states.console.open
      invalidates:
        - gw:itf.states.shell.open
  assumptions:                        # visible bypass of a producer; prefer a probe
    - token: <token>
      owner: <who>
      reason: <why>
  scopes:
    gw:
      goals:
        - <state>
      relations:
        - <relation>
      assumptions:
        - <assumption>
```

- References: `token` = own scope, `:token` = root, `gw:token` = device scope `gw`.
- A slot fills itself when its scope has exactly one node of that contract (aliases count).
- Merge: dicts key by key; `nodes`, `contracts`, `aliases`, `rebinds`, `assumptions`, `states` by
  name/token (override one field of one entry); `goals` and `relations` concatenate. To remove an
  inherited entry, copy the file instead of extending it.
- Config values expand `${NAME}` and `${NAME:-default}` from the environment (`$${` is a literal);
  a value that is exactly one reference is read as a YAML scalar (`port: ${PORT}` is an int). Under
  Bazel, set them with `py_itf_test(env = {"NAME": "$(location //label)"})`.
- Relative paths in config resolve against the directory pytest runs in (the runfiles root under
  Bazel): pass Bazel-built files through `$(location)` and `${ENV}`.
