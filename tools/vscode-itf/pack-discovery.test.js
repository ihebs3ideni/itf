const assert = require("node:assert/strict");
const { mkdtempSync, mkdirSync, rmSync, writeFileSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");
const test = require("node:test");
const YAML = require("yaml");
const { packRootsFromManifests } = require("./pack-discovery");

test("discovers custom pack roots from workspace pack.yaml manifests", () => {
  const directory = mkdtempSync(path.join(tmpdir(), "itf-pack-discovery-"));
  const first = path.join(directory, "vendor-a");
  const second = path.join(directory, "nested", "vendor-a");
  mkdirSync(first);
  mkdirSync(second, { recursive: true });
  const firstManifest = path.join(first, "pack.yaml");
  const secondManifest = path.join(second, "pack.yaml");
  writeFileSync(firstManifest, "name: acme\nversion: 1.0\n");
  writeFileSync(secondManifest, "name: acme\nversion: 2.0\n");
  try {
    const roots = packRootsFromManifests([firstManifest, secondManifest], (file) => require("node:fs").readFileSync(file, "utf8"), YAML.parse);
    assert.deepEqual(roots.get("acme"), [first, second]);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("ignores malformed manifests and manifests without a pack name", () => {
  const directory = mkdtempSync(path.join(tmpdir(), "itf-pack-discovery-"));
  const malformed = path.join(directory, "broken", "pack.yaml");
  const unnamed = path.join(directory, "unnamed", "pack.yaml");
  mkdirSync(path.dirname(malformed));
  mkdirSync(path.dirname(unnamed));
  writeFileSync(malformed, "name: [not: valid\n");
  writeFileSync(unnamed, "version: 1.0\n");
  try {
    const roots = packRootsFromManifests([malformed, unnamed], (file) => require("node:fs").readFileSync(file, "utf8"), YAML.parse);
    assert.equal(roots.size, 0);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
