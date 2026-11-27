const test = require("node:test");
const assert = require("node:assert/strict");
const YAML = require("yaml");
const { findItfReference } = require("./yaml-target");

function referenceAt(text, needle) {
  const document = YAML.parseDocument(text);
  return findItfReference(document, text.indexOf(needle) + Math.floor(needle.length / 2));
}

test("finds short and long capability factory references", () => {
  assert.deepEqual(referenceAt("capabilities:\n  command: docker.exec\n", "docker.exec"), {
    kind: "factory",
    label: "docker.exec",
  });
  assert.deepEqual(referenceAt("capabilities:\n  platform:\n    factory: docker.platform\n", "docker.platform"), {
    kind: "factory",
    label: "docker.platform",
  });
});

test("finds factory references inside scopes", () => {
  const yaml = "scopes:\n  gw:\n    capabilities:\n      command: ssh.exec\n";
  assert.deepEqual(referenceAt(yaml, "ssh.exec"), { kind: "factory", label: "ssh.exec" });
});

test("finds action references in actions and goals", () => {
  const yaml = "goals:\n  - state: service.ready\n    by: local.start_service\nactions:\n  local.start_service:\n";
  assert.deepEqual(referenceAt(yaml, "local.start_service"), { kind: "action", label: "local.start_service" });
  assert.deepEqual(referenceAt(yaml, "service.ready"), { kind: "state", label: "service.ready" });
});

test("finds action references in scoped goals", () => {
  const yaml = "scopes:\n  gateway:\n    goals:\n      - state: shell.open\n        by: ssh.open\n";
  assert.deepEqual(referenceAt(yaml, "ssh.open"), { kind: "action", label: "ssh.open" });
});

test("finds state contracts in goals, relations, and assumptions", () => {
  const yaml = [
    "goals:",
    "  - platform.up",
    "relations:",
    "  - state: shell.open",
    "    after:",
    "      - platform.up",
    "    breaks:",
    "      - network.reachable",
    "assume:",
    "  - state: rack.ready",
    "    owner: lab",
  ].join("\n");
  for (const state of ["platform.up", "shell.open", "network.reachable", "rack.ready"]) {
    assert.deepEqual(referenceAt(yaml, state), { kind: "state", label: state });
  }
});

test("finds state contracts inside scoped relations", () => {
  const yaml = "scopes:\n  gateway:\n    relations:\n      - state: shell.open\n        after:\n          - platform.up\n";
  assert.deepEqual(referenceAt(yaml, "platform.up"), { kind: "state", label: "platform.up" });
});

test("does not treat unrelated strings as ITF references", () => {
  assert.deepEqual(referenceAt("capabilities:\n  platform:\n    with:\n      image: docker.io/example:latest\n", "docker.io/example:latest"), undefined);
});
