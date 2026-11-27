const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const vscode = require("vscode");
const YAML = require("yaml");
const { findItfReference } = require("./yaml-target");
const { packRootsFromManifests } = require("./pack-discovery");

const EXCLUDE = "{**/.git/**,**/node_modules/**,**/.venv/**,**/bazel-*/**}";
const sourceCache = new Map();
const indexCache = new Map();
const packRootsCache = new Map();

function asList(value) {
  if (value === undefined || value === null) return [];
  return Array.isArray(value) ? value : [value];
}

function readText(filePath) {
  const open = vscode.workspace.textDocuments.find((document) =>
    document.uri.scheme === "file" && path.resolve(document.uri.fsPath) === path.resolve(filePath));
  return open ? open.getText() : fs.readFileSync(filePath, "utf8");
}

async function collectTargetInfo(filePath, visited = new Set()) {
  const absolute = path.resolve(filePath);
  if (visited.has(absolute)) return { packs: {}, policies: [], providers: [] };
  visited.add(absolute);
  let document;
  try {
    document = YAML.parse(readText(absolute)) || {};
  } catch {
    return { packs: {}, policies: [], providers: [] };
  }

  const result = { packs: {}, policies: [], providers: [] };
  for (const include of asList(document.include)) {
    if (typeof include !== "string") continue;
    const child = await collectTargetInfo(path.resolve(path.dirname(absolute), include), visited);
    Object.assign(result.packs, child.packs);
    result.policies.push(...child.policies);
    result.providers.push(...child.providers);
  }
  if (document.packs && typeof document.packs === "object" && !Array.isArray(document.packs)) {
    Object.assign(result.packs, document.packs);
  }
  for (const capabilities of [document.capabilities, ...Object.values(document.scopes || {}).map((scope) => scope?.capabilities)]) {
    if (!capabilities || typeof capabilities !== "object") continue;
    for (const entry of Object.values(capabilities)) {
      const factory = typeof entry === "string" ? entry : entry?.factory;
      if (typeof factory === "string" && factory.includes(".")) result.providers.push(factory.split(".", 1)[0]);
    }
  }
  for (const policy of asList(document.policies)) {
    if (typeof policy === "string" && policy.trim()) {
      result.policies.push(path.resolve(path.dirname(absolute), policy));
    }
  }
  result.policies = [...new Set(result.policies)];
  result.providers = [...new Set(result.providers)];
  return result;
}

async function findWorkspaceFiles(pattern, folders = vscode.workspace.workspaceFolders || []) {
  const files = [];
  for (const folder of folders) {
    const found = await vscode.workspace.findFiles(new vscode.RelativePattern(folder, pattern), EXCLUDE, 3000);
    files.push(...found.map((uri) => uri.fsPath));
  }
  return files;
}

async function findPythonFilesUnder(directory) {
  const files = [];
  for (const folder of vscode.workspace.workspaceFolders || []) {
    const relative = path.relative(folder.uri.fsPath, directory);
    if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) continue;
    const prefix = relative ? `${relative.split(path.sep).join("/")}/` : "";
    const found = await vscode.workspace.findFiles(new vscode.RelativePattern(folder, `${prefix}**/*.py`), EXCLUDE, 5000);
    files.push(...found.map((uri) => uri.fsPath));
  }
  return files;
}

async function workspacePackRoots(folder) {
  const key = folder.uri.fsPath;
  if (!packRootsCache.has(key)) {
    packRootsCache.set(key, findWorkspaceFiles("**/pack.yaml", [folder]).then((manifests) =>
      packRootsFromManifests(manifests, readText, YAML.parse),
    ));
  }
  return packRootsCache.get(key);
}

async function sourceFilesForPack(pack, targetInfo) {
  if (pack === "local") {
    return targetInfo.policies.map((file) => ({ pack, path: file }));
  }

  const module = targetInfo.packs[pack];
  const folders = [...(vscode.workspace.workspaceFolders || [])];
  const owner = vscode.workspace.getWorkspaceFolder(targetInfo.uri);
  if (owner) folders.sort((left, right) => Number(right === owner) - Number(left === owner));
  const key = `${pack}\n${module || ""}\n${folders.map((folder) => folder.uri.fsPath).join("\n")}`;
  if (sourceCache.has(key)) return sourceCache.get(key);

  let files = [];
  const explicit = typeof module === "string" && module !== `score.itf.packs.${pack}.plugin`;
  if (explicit && !/^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$/.test(module)) return [];
  for (const folder of folders) {
    if (explicit) {
      const modulePath = module.replaceAll(".", "/");
      const packagePath = module.split(".").slice(0, -1).join("/");
      files = await findWorkspaceFiles(`**/${modulePath}.py`, [folder]);
      const packages = await findWorkspaceFiles(`**/${modulePath}/__init__.py`, [folder]);
      files.push(...packages);
      if (files.length && packagePath) files.push(...(await findWorkspaceFiles(`**/${packagePath}/**/*.py`, [folder])));
    } else {
      const roots = (await workspacePackRoots(folder)).get(pack) || [];
      files = (await Promise.all(roots.map(findPythonFilesUnder))).flat();
      if (!files.length) files = await findWorkspaceFiles(`score/itf/packs/${pack}/**/*.py`, [folder]);
    }
    if (files.length) break;
  }
  const sources = [...new Set(files)].map((file) => ({ pack, path: file }));
  sourceCache.set(key, sources);
  return sources;
}

function buildIndex(sources, output, uri) {
  const python = vscode.workspace.getConfiguration("itf.definition", uri).get("python", "python3");
  const key = `${python}\n${sources.map((source) => `${source.pack}:${source.path}`).sort().join("\n")}`;
  if (indexCache.has(key)) return indexCache.get(key);
  const resolver = path.join(__dirname, "resolve.py");
  const pending = new Promise((resolve, reject) => {
    const process = spawn(python, [resolver], { stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      process.kill("SIGKILL");
    }, 10000);
    process.stdout.setEncoding("utf8").on("data", (chunk) => (stdout += chunk));
    process.stderr.setEncoding("utf8").on("data", (chunk) => (stderr += chunk));
    process.on("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    process.stdin.on("error", reject);
    process.on("close", (code) => {
      clearTimeout(timeout);
      if (timedOut) {
        reject(new Error("Python resolver timed out after 10 seconds"));
        return;
      }
      if (code !== 0) {
        reject(new Error(stderr || `resolver exited with status ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (error) {
        reject(error);
      }
    });
    process.stdin.end(JSON.stringify({ sources }));
  });
  indexCache.set(key, pending);
  pending.catch((error) => {
    indexCache.delete(key);
    output.appendLine(`ITF definition index failed: ${error}`);
  });
  return pending;
}

async function sourcesForReference(reference, targetInfo) {
  if (reference.kind !== "state") return sourceFilesForPack(reference.label.split(".", 1)[0], targetInfo);
  const packs = new Set([...targetInfo.providers, ...Object.keys(targetInfo.packs), "local"]);
  const sources = await Promise.all([...packs].map((pack) => sourceFilesForPack(pack, targetInfo)));
  return sources.flat();
}

async function provideDefinition(document, position, output) {
  if (vscode.workspace.isTrusted === false) return undefined;
  if (!document.fileName.endsWith(".itf.yaml")) return undefined;
  const parsed = YAML.parseDocument(document.getText());
  const reference = findItfReference(parsed, document.offsetAt(position));
  if (!reference) return undefined;

  try {
    const targetInfo = await collectTargetInfo(document.uri.fsPath);
    targetInfo.uri = document.uri;
    const sources = await sourcesForReference(reference, targetInfo);
    if (sources.length === 0) return undefined;
    const index = await buildIndex(sources, output, document.uri);
    const locations = index.filter((item) => item.kind === reference.kind && item.label === reference.label);
    return locations.map((location) => {
      const start = new vscode.Position(location.line, location.character);
      const end = new vscode.Position(location.endLine, location.endCharacter);
      return new vscode.Location(vscode.Uri.file(location.path), new vscode.Range(start, end));
    });
  } catch (error) {
    output.appendLine(`ITF definition lookup failed: ${error}`);
    return undefined;
  }
}

function activate(context) {
  const output = vscode.window.createOutputChannel("ITF YAML Navigation");
  const watcher = vscode.workspace.createFileSystemWatcher("**/*.py");
  const manifestWatcher = vscode.workspace.createFileSystemWatcher("**/pack.yaml");
  const invalidate = () => {
    sourceCache.clear();
    indexCache.clear();
  };
  const invalidateSources = () => {
    packRootsCache.clear();
    invalidate();
  };
  context.subscriptions.push(
    watcher,
    watcher.onDidChange(invalidate),
    watcher.onDidCreate(invalidate),
    watcher.onDidDelete(invalidate),
    manifestWatcher,
    manifestWatcher.onDidChange(invalidateSources),
    manifestWatcher.onDidCreate(invalidateSources),
    manifestWatcher.onDidDelete(invalidateSources),
    vscode.workspace.onDidChangeWorkspaceFolders(invalidateSources),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("itf.definition")) invalidate();
    }),
    vscode.workspace.onDidChangeTextDocument(({ document }) => {
      if (path.basename(document.uri.fsPath) === "pack.yaml") invalidateSources();
    }),
  );
  const provider = {
    provideDefinition: (document, position) => provideDefinition(document, position, output),
  };
  context.subscriptions.push(
    output,
    vscode.languages.registerDefinitionProvider({ language: "yaml", scheme: "file" }, provider),
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
