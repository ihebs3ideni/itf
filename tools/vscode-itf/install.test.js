const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

function runInstaller({ failPackage = false, pythonCommand } = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "itf-install-"));
  const record = path.join(directory, "installed.json");
  const npm = path.join(directory, "npm");
  const cli = path.join(directory, "code-stub");
  fs.writeFileSync(npm, `#!${process.execPath}
const fs = require("node:fs");
if (process.argv[2] === "exec") {
  if (process.env.ITF_TEST_FAIL_PACKAGE === "1") process.exit(7);
  fs.writeFileSync(process.argv[process.argv.indexOf("--out") + 1], "test VSIX");
}
`, { mode: 0o755 });
  fs.writeFileSync(cli, `#!${process.execPath}
const assert = require("node:assert/strict");
const fs = require("node:fs");
const args = process.argv.slice(2);
assert.equal(args.length, 3);
assert.equal(args[0], "--install-extension");
assert.equal(args[2], "--force");
assert.ok(fs.existsSync(args[1]));
fs.writeFileSync(process.env.ITF_TEST_RECORD, JSON.stringify(args));
`, { mode: 0o755 });
  const result = spawnSync("bash", [path.join(__dirname, "install.sh")], {
    cwd: os.tmpdir(),
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: `${directory}${path.delimiter}${process.env.PATH}`,
      ITF_VSCODE_CLI: cli,
      ITF_TEST_RECORD: record,
      ITF_TEST_FAIL_PACKAGE: failPackage ? "1" : "0",
      ...(pythonCommand ? { ITF_EXTENSION_PYTHON: pythonCommand } : {}),
    },
  });
  return { directory, record, result };
}

test("installer dispatches an existing VSIX from any working directory and cleans it up", () => {
  const { directory, record, result } = runInstaller();
  try {
    assert.equal(result.status, 0, result.stderr);
    const args = JSON.parse(fs.readFileSync(record, "utf8"));
    assert.equal(fs.existsSync(path.dirname(args[1])), false);
    assert.match(result.stdout, /Installed ITF YAML Navigation/);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});


test("installer never invokes VS Code when packaging fails", () => {
  const { directory, record, result } = runInstaller({ failPackage: true });
  try {
    assert.equal(result.status, 7, result.stderr);
    assert.equal(fs.existsSync(record), false);
    assert.doesNotMatch(result.stdout, /Installed ITF YAML Navigation/);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("installer fails early when its Python runtime is missing", () => {
  const missingPython = path.join(os.tmpdir(), `missing-python-${process.pid}`);
  const { directory, record, result } = runInstaller({ pythonCommand: missingPython });
  try {
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Python 3\.8 or newer is required/);
    assert.equal(fs.existsSync(record), false);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});