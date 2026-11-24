"""Index ITF factories, actions, and state contracts without importing providers."""

import ast
import json
from pathlib import Path
import sys


def _decorator_name(node):
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _argument(call, name, position):
    if not isinstance(call, ast.Call):
        return None
    if len(call.args) > position and isinstance(call.args[position], ast.Constant):
        return call.args[position].value
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            return keyword.value.value
    return None


def _keyword_string(call, name):
    if not isinstance(call, ast.Call):
        return None
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            return keyword.value.value
    return None


def _strings(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [item.value for item in node.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)]
    return []


def _decorator_label(call, default):
    label = _keyword_string(call, "label")
    return label if isinstance(label, str) else default


def _records(node, pack, path):
    records = []
    for decorator in node.decorator_list:
        name = _decorator_name(decorator)
        if name not in {"capability", "state"}:
            continue

        label = f"{pack}.{_decorator_label(decorator, node.name)}"
        location = {
            "path": str(path),
            "line": max(decorator.lineno - 1, 0),
            "character": decorator.col_offset,
            "endLine": max(node.end_lineno - 1, 0),
            "endCharacter": node.end_col_offset,
        }
        if name == "capability":
            records.append({"kind": "factory", "label": label, **location})
            continue

        records.append({"kind": "action", "label": label, **location})
        state_name = _argument(decorator, "state_name", 0)
        if isinstance(state_name, str):
            records.append({"kind": "state", "label": state_name, **location})
        for keyword in getattr(decorator, "keywords", ()):
            if keyword.arg == "also":
                records.extend({"kind": "state", "label": state, **location} for state in _strings(keyword.value))
    return records


def resolve(payload):
    records = []
    seen = set()
    for source in payload.get("sources", []):
        path = Path(source["path"]).resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            records.extend(_records(node, source["pack"], path))
    return records


if __name__ == "__main__":
    json.dump(resolve(json.load(sys.stdin)), sys.stdout)
