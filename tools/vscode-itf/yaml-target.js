const YAML = require("yaml");

function stringValue(node) {
  return YAML.isScalar(node) && typeof node.value === "string" ? node.value : undefined;
}

function mappingValue(node, name) {
  if (!YAML.isMap(node)) return undefined;
  const pair = node.items.find((item) => stringValue(item.key) === name);
  return pair?.value;
}

function entries(node) {
  return YAML.isMap(node) ? node.items : [];
}

function nodeAtOffset(node, offset) {
  if (!node) return undefined;
  if (YAML.isScalar(node) && node.range && node.range[0] <= offset && offset <= node.range[1]) return node;
  if (YAML.isMap(node)) {
    for (const pair of node.items) {
      const found = nodeAtOffset(pair.key, offset) || nodeAtOffset(pair.value, offset);
      if (found) return found;
    }
  } else if (YAML.isSeq(node)) {
    for (const item of node.items) {
      const found = nodeAtOffset(item, offset);
      if (found) return found;
    }
  }
  return undefined;
}

function capabilityMaps(root) {
  const maps = [mappingValue(root, "capabilities")];
  for (const scope of entries(mappingValue(root, "scopes"))) {
    maps.push(mappingValue(scope.value, "capabilities"));
  }
  return maps;
}

function actionMaps(root) {
  const maps = [mappingValue(root, "actions")];
  for (const scope of entries(mappingValue(root, "scopes"))) {
    maps.push(mappingValue(scope.value, "actions"));
  }
  return maps;
}

function goalLists(root) {
  const lists = [mappingValue(root, "goals")];
  for (const scope of entries(mappingValue(root, "scopes"))) {
    lists.push(mappingValue(scope.value, "goals"));
  }
  return lists;
}

function relationLists(root) {
  const lists = [mappingValue(root, "relations")];
  for (const scope of entries(mappingValue(root, "scopes"))) {
    lists.push(mappingValue(scope.value, "relations"));
  }
  return lists;
}

function stateNodes(root) {
  const nodes = [];
  for (const goals of goalLists(root)) {
    if (!YAML.isSeq(goals)) continue;
    for (const goal of goals.items) {
      if (YAML.isScalar(goal)) nodes.push(goal);
      else nodes.push(mappingValue(goal, "state"));
    }
  }
  for (const relations of relationLists(root)) {
    if (!YAML.isSeq(relations)) continue;
    for (const relation of relations.items) {
      nodes.push(mappingValue(relation, "state"));
      for (const key of ["after", "breaks"]) {
        const states = mappingValue(relation, key);
        if (YAML.isSeq(states)) nodes.push(...states.items);
      }
    }
  }
  const assumptions = mappingValue(root, "assume");
  if (YAML.isSeq(assumptions)) {
    for (const assumption of assumptions.items) {
      nodes.push(YAML.isScalar(assumption) ? assumption : mappingValue(assumption, "state"));
    }
  }
  return nodes.filter(Boolean);
}

function findItfReference(document, offset) {
  const root = document.contents;
  if (!root) return undefined;
  const node = nodeAtOffset(root, offset);
  const value = stringValue(node);
  if (!value) return undefined;

  for (const capabilities of capabilityMaps(root)) {
    for (const role of entries(capabilities)) {
      const entry = role.value;
      if (entry === node && value.includes(".")) return { kind: "factory", label: value };
      const factory = mappingValue(entry, "factory");
      if (factory === node && value.includes(".")) return { kind: "factory", label: value };
    }
  }

  for (const actions of actionMaps(root)) {
    for (const action of entries(actions)) {
      if (action.key === node && value.includes(".")) return { kind: "action", label: value };
    }
  }

  for (const goals of goalLists(root)) {
    if (!YAML.isSeq(goals)) continue;
    for (const goal of goals.items) {
      const action = mappingValue(goal, "by");
      if (action === node && value.includes(".")) return { kind: "action", label: value };
    }
  }

  if (stateNodes(root).includes(node) && value.includes(".")) {
    return { kind: "state", label: value };
  }

  return undefined;
}

module.exports = { findItfReference };
