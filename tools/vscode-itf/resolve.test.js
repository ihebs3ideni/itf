const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const resolver = path.join(__dirname, "resolve.py");

test("indexes customized factories, actions, and state contracts without importing the module", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "itf-definition-"));
  const source = path.join(directory, "providers.py");
  fs.writeFileSync(
    source,
    [
      "from score.itf import capability, state",
      "@capability('exec.command', label='execute')",
      "def make_command():",
      "    raise RuntimeError('must not execute')",
      "@state('platform.up', also=('device.ready', 'network.reachable'), label='start_platform')",
      "def start():",
      "    raise RuntimeError('must not execute')",
      "",
    ].join("\n"),
  );
  try {
    const result = spawnSync("python3", [resolver], {
      encoding: "utf8",
      input: JSON.stringify({
        sources: [{ pack: "demo", path: source }],
      }),
    });
    assert.equal(result.status, 0, result.stderr);
    const records = JSON.parse(result.stdout);
    assert.ok(records.some((record) => record.kind === "factory" && record.label === "demo.execute" && record.line === 1));
    assert.ok(records.some((record) => record.kind === "action" && record.label === "demo.start_platform" && record.line === 4));
    assert.ok(records.some((record) => record.kind === "state" && record.label === "platform.up" && record.line === 4));
    assert.ok(records.some((record) => record.kind === "state" && record.label === "device.ready" && record.line === 4));
    assert.ok(records.some((record) => record.kind === "state" && record.label === "network.reachable" && record.line === 4));
    assert.ok(records.every((record) => record.path === source));
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
