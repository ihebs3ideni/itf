const path = require("node:path");

function packRootsFromManifests(manifests, readText, parseYaml) {
  const roots = new Map();
  for (const manifest of manifests) {
    try {
      const metadata = parseYaml(readText(manifest));
      if (typeof metadata?.name !== "string" || !metadata.name) continue;
      const packRoots = roots.get(metadata.name) || [];
      packRoots.push(path.dirname(manifest));
      roots.set(metadata.name, packRoots);
    } catch {
      continue;
    }
  }
  for (const [name, packRoots] of roots) {
    roots.set(name, [...new Set(packRoots.map((root) => path.resolve(root)))]);
  }
  return roots;
}

module.exports = { packRootsFromManifests };
