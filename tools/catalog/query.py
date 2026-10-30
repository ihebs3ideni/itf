# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""Query the ITF pack catalog, a SQLite database built from the packs' decorators.

    bazel run //tools/catalog:query -- schema            tables, views, column comments: read first
    bazel run //tools/catalog:query -- sql "SELECT ..."  any read-only query; --json for JSON rows
    bazel run //tools/catalog:query -- search WORDS...   full-text hits for a requirement sentence
    bazel run //tools/catalog:query -- serve [--port N]  build catalog.html and serve it on 127.0.0.1
    bazel run //tools/catalog:query -- recipe PROVIDER   a node skeleton, in Starlark and YAML

The database is built from the packs' own decorators on every run (it cannot drift from the code)
and kept in the temp directory while its sources are unchanged. `--from catalog.html` builds it from
the data embedded in a generated catalog instead; `--db PATH` uses an existing database as is.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import sqlite3
import os
import sys
import tempfile
from pathlib import Path

from tools.catalog import build_catalog

STOPWORDS = {
    "a",
    "an",
    "and",
    "the",
    "to",
    "of",
    "in",
    "on",
    "for",
    "is",
    "be",
    "it",
    "its",
    "with",
    "that",
    "shall",
    "must",
    "should",
    "can",
    "via",
    "from",
    "by",
    "as",
    "at",
    "or",
    "each",
    "every",
    "all",
    "after",
    "before",
    "within",
    "while",
    "when",
    "then",
    "not",
    "no",
}


def _fresh_db() -> Path:
    """The catalog database, rebuilt from the packs when its sources changed."""
    path = build_catalog.DB
    fingerprint = build_catalog.source_hash()
    if path.exists():
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            row = db.execute("SELECT value FROM meta WHERE key = 'source_hash'").fetchone()
        if row and row[0] == fingerprint:
            return path
    build_catalog.write_db(build_catalog.build(), path, fingerprint)
    return path


def _db_from_html(html_path: Path) -> Path:
    html = html_path.read_text(encoding="utf-8")
    data = json.loads(html.split("const DATA = ", 1)[1].split(";\n", 1)[0].replace("<\\/", "</"))
    out = Path(tempfile.mkdtemp(prefix="itf-catalog-")) / "catalog.db"
    build_catalog.write_db(data, out)
    return out


def connect(args) -> sqlite3.Connection:
    workspace = Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", "."))
    if args.db:
        path = workspace / args.db
    else:
        path = _db_from_html(workspace / args.source) if args.source else _fresh_db()
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def _print(rows, as_json: bool) -> None:
    rows = [dict(r) for r in rows]
    if as_json:
        print(json.dumps(rows, indent=1))
        return
    if not rows:
        print("(no rows)")
        return
    print("\t".join(rows[0]))
    for row in rows:
        print("\t".join("" if v is None else str(v).replace("\n", " ") for v in row.values()))


def _print_recipe_node(db, provider: str) -> None:
    """A node for `provider`, required config as placeholders, optional config as comments."""
    row = db.execute("SELECT * FROM v_recipe_node WHERE provider = ?", (provider,)).fetchone()
    if row is None:
        sys.exit(f'no provider {provider!r}; see: sql "SELECT provider FROM v_recipe_node"')
    fields = [f.strip() for f in (row["config"] or "").split(",") if f.strip()]
    required = [f.split(":", 1)[0] for f in fields if f.endswith("!")]
    optional = [f for f in fields if not f.endswith("!")]
    name = provider.split(".", 1)[-1]
    config = ", ".join(f'"{k}": "<{k}>"' for k in required)
    print(f"# load: {row['entrypoints']}" + (f"; slots: {row['needs']}" if row["needs"] else ""))
    print("# Starlark (bazel/recipe.bzl)")
    print(
        f'node("{name}", "{row["contract"]}", using = "{provider}"'
        + (f", config = {{{config}}}" if required else "")
        + ")"
    )
    print("# YAML")
    yaml_config = ", ".join(f"{k}: <{k}>" for k in required)
    print(
        f"- {{name: {name}, contract: {row['contract']}, using: {provider}"
        + (f", config: {{{yaml_config}}}" if required else "")
        + "}"
    )
    if optional:
        print(f"# optional config: {', '.join(optional)}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="source", type=Path, help="build from a generated catalog.html")
    parser.add_argument("--db", type=Path, help="use this database as is")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("schema")
    sql = sub.add_parser("sql")
    sql.add_argument("query")
    sql.add_argument("--json", action="store_true")
    find = sub.add_parser("search")
    find.add_argument("words", nargs="+")
    find.add_argument("--limit", type=int, default=15)
    find.add_argument("--json", action="store_true")
    sub.add_parser("serve").add_argument("--port", type=int, default=8799)
    sub.add_parser("recipe").add_argument("provider")
    args = parser.parse_args(argv)

    if args.command == "serve":
        directory = Path(tempfile.mkdtemp(prefix="itf-catalog-"))
        (directory / "catalog.html").write_text(build_catalog.render(build_catalog.build()), encoding="utf-8")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
        with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
            print(f"catalog: http://127.0.0.1:{args.port}/catalog.html  (Ctrl+C to stop)", flush=True)
            server.serve_forever()
        return

    db = connect(args)
    if args.command == "recipe":
        _print_recipe_node(db, args.provider)
        return
    if args.command == "schema":
        for (text,) in db.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'search_%' "
            "ORDER BY type = 'view', rowid"
        ):
            print(text + ";\n")
        print("-- counts:", db.execute("SELECT value FROM meta WHERE key = 'counts'").fetchone()[0])
    elif args.command == "sql":
        try:
            _print(db.execute(args.query).fetchall(), args.json)
        except sqlite3.Error as exc:
            sys.exit(f"sql error: {exc}")
    else:
        terms = [w for w in re.findall(r"[a-z0-9]+", " ".join(args.words).lower()) if w not in STOPWORDS and len(w) > 1]
        rows = (
            db.execute(
                "SELECT kind, id, title, round(rank, 2) AS rank FROM search WHERE search MATCH ? ORDER BY rank LIMIT ?",
                (" OR ".join(f'"{t}"' for t in terms), args.limit),
            ).fetchall()
            if terms
            else []
        )
        if rows or args.json:
            _print(rows, args.json)
        else:
            print(
                f"no matches for {' '.join(terms) or '(no searchable words)'}: likely a gap, "
                'see `sql "SELECT token FROM capabilities"`'
            )


if __name__ == "__main__":
    main()
