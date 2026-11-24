const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

function document(file, text) {
  return {
    fileName: file,
    uri: { scheme: "file", fsPath: file },
    getText: () => text,
    offsetAt: (position) => position,
  };
}

function harness(documents) {
  let provider;
  const errors = [];
  const event = () => ({ dispose() {} });
  const vscode = {
    workspace: {
      textDocuments: documents,
      workspaceFolders: [],
      getWorkspaceFolder: (uri) => vscode.workspace.workspaceFolders.find((folder) => uri.fsPath.startsWith(`${folder.uri.fsPath}${path.sep}`)),
      getConfiguration: () => ({ get: () => "python3" }),
      createFileSystemWatcher: () => ({ onDidChange: event, onDidCreate: event, onDidDelete: event }),
      onDidChangeWorkspaceFolders: event,
      onDidChangeConfiguration: event,
      onDidChangeTextDocument: event,
    },
    window: { createOutputChannel: () => ({ appendLine: (line) => errors.push(line) }) },
    languages: { registerDefinitionProvider: (_, value) => { provider = value; } },
    Position: class { constructor(line, character) { Object.assign(this, { line, character }); } },
    Range: class { constructor(start, end) { Object.assign(this, { start, end }); } },
    Location: class { constructor(uri, range) { Object.assign(this, { uri, range }); } },
    Uri: { file: (file) => ({ fsPath: file }) },
  };
  const module = { exports: {} };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "extension.js"), "utf8"), {
    require: (name) => name === "vscode" ? vscode : require(name),
    module, __dirname, setTimeout, clearTimeout,
  });
  module.exports.activate({ subscriptions: [] });
  return { lookup: (doc, label) => provider.provideDefinition(doc, doc.getText().indexOf(label)), errors, vscode };
}

test("provider resolves policies from unsaved target and included document buffers", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "itf-provider-"));
  try {
    const target = path.join(directory, "target.itf.yaml");
    const included = path.join(directory, "parts.yaml");
    const policy = path.join(directory, "policy.py");
    fs.writeFileSync(target, "capabilities: {}\n");
    fs.writeFileSync(included, "policies: []\n");
    fs.writeFileSync(policy, "@capability('exec.command')\ndef command(): pass\n");
    const doc = document(target, "include: parts.yaml\ncapabilities:\n  command: local.command\n");
    const host = harness([doc, document(included, "policies: [policy.py]\n")]);
    const locations = await host.lookup(doc, "local.command");
    assert.equal(locations.length, 1);
    assert.equal(locations[0].uri.fsPath, policy);
    assert.deepEqual(host.errors, []);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("provider prefers the target workspace and falls back only when its pack is absent", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "itf-roots-"));
  try {
    const folders = ["other", "owner"].map((name) => ({ uri: { fsPath: path.join(directory, name) } }));
    const sources = folders.map((folder) => path.join(folder.uri.fsPath, "score/itf/packs/demo/providers.py"));
    for (const source of sources) {
      fs.mkdirSync(path.dirname(source), { recursive: true });
      fs.writeFileSync(source, "@capability('exec.command')\ndef command(): pass\n");
    }
    const doc = document(path.join(folders[1].uri.fsPath, "target.itf.yaml"), "capabilities:\n  command: demo.command\n");
    const host = harness([doc]);
    host.vscode.workspace.workspaceFolders = folders;
    host.vscode.RelativePattern = class { constructor(folder, pattern) { Object.assign(this, { folder, pattern }); } };
    let ownerHasPack = true;
    host.vscode.workspace.findFiles = async ({ folder, pattern }) => {
      if (pattern === "**/pack.yaml") return [];
      if (folder === folders[1] && !ownerHasPack) return [];
      return [{ fsPath: sources[folders.indexOf(folder)] }];
    };
    const locations = await host.lookup(doc, "demo.command");
    assert.equal(locations.length, 1);
    assert.equal(locations[0].uri.fsPath, sources[1]);
    const fallback = harness([doc]);
    Object.assign(fallback.vscode.workspace, host.vscode.workspace);
    fallback.vscode.RelativePattern = host.vscode.RelativePattern;
    ownerHasPack = false;
    assert.equal((await fallback.lookup(doc, "demo.command"))[0].uri.fsPath, sources[0]);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("an unresolved explicit module never falls back to an unrelated manifest pack", async () => {
  const doc = document("/workspace/target.itf.yaml", "packs:\n  demo: missing.plugin\ncapabilities:\n  command: demo.command\n");
  const host = harness([doc]);
  host.vscode.workspace.workspaceFolders = [{ uri: { fsPath: "/workspace" } }];
  host.vscode.RelativePattern = class { constructor(folder, pattern) { Object.assign(this, { folder, pattern }); } };
  host.vscode.workspace.findFiles = async ({ pattern }) => {
    assert.notEqual(pattern, "**/pack.yaml");
    return [];
  };
  assert.equal(await host.lookup(doc, "demo.command"), undefined);
  assert.deepEqual(host.errors, []);
});

test("provider does not launch a resolver in an untrusted workspace", async () => {
  const doc = document("/workspace/target.itf.yaml", "capabilities:\n  command: local.command\n");
  const host = harness([doc]);
  host.vscode.workspace.isTrusted = false;
  assert.equal(await host.lookup(doc, "local.command"), undefined);
  assert.deepEqual(host.errors, []);
});

test("provider reports missing Python and retries with a corrected interpreter", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "itf-python-"));
  try {
    const policy = path.join(directory, "policy.py");
    fs.writeFileSync(policy, "@capability('exec.command')\ndef command(): pass\n");
    const doc = document(path.join(directory, "target.itf.yaml"), "policies: [policy.py]\ncapabilities:\n  command: local.command\n");
    const host = harness([doc]);
    let python = path.join(directory, "missing-python");
    host.vscode.workspace.getConfiguration = (_, uri) => {
      assert.equal(uri.fsPath, doc.uri.fsPath);
      return { get: () => python };
    };
    assert.equal(await host.lookup(doc, "local.command"), undefined);
    assert.ok(host.errors.some((line) => line.includes("ENOENT")));
    python = "python3";
    assert.equal((await host.lookup(doc, "local.command"))[0].uri.fsPath, policy);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});