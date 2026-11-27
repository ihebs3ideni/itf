#!/usr/bin/env bash
set -euo pipefail

extension_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
code_cli="${ITF_VSCODE_CLI:-code}"
python_cli="${ITF_EXTENSION_PYTHON:-python3}"

if ! command -v npm >/dev/null 2>&1; then
    printf 'npm is required to package the ITF YAML Navigation extension.\n' >&2
    exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 1)'; then
    printf 'Node.js 22 or newer is required to package the extension.\n' >&2
    exit 1
fi
if ! command -v "$python_cli" >/dev/null 2>&1; then
    printf 'Python 3.8 or newer is required on the extension host. Set ITF_EXTENSION_PYTHON to its executable.\n' >&2
    exit 1
fi
if ! "$python_cli" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
    printf 'Python 3.8 or newer is required on the extension host. Set ITF_EXTENSION_PYTHON to its executable.\n' >&2
    exit 1
fi
if ! command -v "$code_cli" >/dev/null 2>&1; then
    printf 'VS Code CLI %s was not found. Set ITF_VSCODE_CLI to the desired code executable.\n' "$code_cli" >&2
    exit 1
fi

cd "$extension_dir"
npm ci

package_dir="$(mktemp -d)"
trap 'rm -rf "$package_dir"' EXIT
npm exec -- vsce package --dependencies --allow-missing-repository --out "$package_dir/itf-yaml-navigation.vsix"
"$code_cli" --install-extension "$package_dir/itf-yaml-navigation.vsix" --force
printf 'Installed ITF YAML Navigation into the VS Code environment selected by %s.\n' "$code_cli"
