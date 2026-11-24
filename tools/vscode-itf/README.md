# ITF YAML Navigation (Experimental)

A small VS Code extension that adds Go to Definition for provider/factory labels, action labels, and state-contract references in `*.itf.yaml` files.

## Try it

Requirements: VS Code 1.85+, a trusted file-based workspace, and Python 3.8+ on the extension host.
The installer checks Python, Bash, Node.js 22+, npm, and the selected VS Code CLI before packaging.
`ITF_EXTENSION_PYTHON` selects the Python executable checked by the installer; set the matching
`itf.definition.python` VS Code setting if it differs from `python3`. Installing from source also requires
access to the npm registry. JavaScript dependencies are declared in `package.json` and pinned by
`package-lock.json`; the Python resolver uses only the standard library, so no Python package requirements
file is needed.
The installer supports Linux/macOS terminals and Linux Remote-SSH hosts. Native Windows PowerShell/cmd
installation is not supported by this script; a packaged VSIX can be installed using VS Code's
**Extensions: Install from VSIX** command instead.

From the ITF repository root, install the extension into the VS Code environment selected by the `code` CLI:

```sh
bash tools/vscode-itf/install.sh
```

Run this in a local terminal to install into local VS Code, or in the integrated terminal of a Remote-SSH window to install into that remote host. Set `ITF_VSCODE_CLI` if the intended `code` executable is not on `PATH`.

From the ITF workspace root, press F5 and choose **Launch ITF YAML Navigation**.
This opens an Extension Development Host on the ITF workspace; the remote `code` CLI does not support
`--extensionDevelopmentPath`.

Open an ITF target YAML and use F12 or Ctrl/Cmd-click on a factory label such as `docker.platform`, an action label such as `docker.start`, or a state such as `platform.up` in `goals:` or `relations:`.

Set `itf.definition.python` if `python3` is not the interpreter that can read the workspace's Python sources.
The interpreter must also support any Python syntax used by those sources. Lookup failures are logged in
the **ITF YAML Navigation** output channel. Indexing times out after 10 seconds.

## Scope

- Built-in and custom packs discovered from workspace `pack.yaml` manifests.
- Custom pack modules selected by target `packs:` entries; explicit module mappings take precedence over manifest discovery.
- `local.*` parts listed in the target YAML or its recursively included YAML files.
- Factory labels, including `label=` overrides, action labels, and state names from `@state(...)` and `also=`.
- Unsaved target and included YAML buffers are used for pack mappings and policies.
- Pack discovery prefers the target's workspace folder; other roots are fallbacks, not merged copies.
	Explicit custom module mappings never fall back to a differently named module's manifest.

The resolver parses saved Python sources with the standard-library AST and does not import provider modules.
Source lists and AST indexes are cached; Python file changes, manifest edits, workspace-folder changes,
and interpreter settings invalidate the relevant caches. Explicit include and policy paths may point
outside workspace folders, as permitted by the target format; only use trusted projects.
This MVP does not discover installed pack sources outside the workspace, Bazel-generated/external source
trees, or policies supplied only through separately selected override files. YAML aliases/merge keys,
unsaved Python changes, and module imports/re-exports are not resolved. It is not a full YAML schema
validator or standalone LSP server. OCTO integration and completion are not implemented.

## Development

```sh
npm ci
npm test
```

Tests exercise the registered definition provider through a VS Code API stub, including a real Python
resolver subprocess. They are not Extension Development Host UI tests. PR checks run the suite and
verify the packaged VSIX contains the runtime YAML dependency, resolver, and license notices.
