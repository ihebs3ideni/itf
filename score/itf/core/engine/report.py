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
"""Render a resolved plan as one self-contained, interactive HTML page.

Composition describes persistent objects; the separate state lane describes work and observation.

Per scope: the bring-up lane (states in the order ITF executed them) and the composition tree (the
target, the capabilities it is made of, and what each of those consumes, to any depth). Hovering or
clicking any element shows its provenance: contract, provider and why it was chosen, each slot and
why it was bound, expected vs. given shapes, ordering reasons, and whether a state ran or already held.
"""

from __future__ import annotations

import html
import json

from ..octo import ActionPlan
from .render import TEMPLATES, render
from .scopes import display

_EMPTY_ACTION_PLAN = ActionPlan(goals=(), observed_at_plan_time=(), steps=(), edges=(), unprobed=())


class _Wanted:
    """A state card for a plan that did not resolve: its key and the ghost nodes it lacks."""

    def __init__(self, key: str, uses: tuple):
        self.key, self.uses = key, uses


_NODE_W, _NODE_H = 184, 58
_NODE_GAP = 36
_LAYER_GAP = 120
_STATE_H, _STATE_GAP = 44, 46
_TARGET_W, _TARGET_H = 168, 50
_MARGIN = 36
_STATE_TOP = 46

_WHY_PROVIDER = {
    "explicit-using": "named explicitly by the recipe (using=)",
    "sole-implementation": "the only provider implementing this contract",
}
_WHY_BINDING = {
    "explicit": "bound explicitly by the recipe (bind=)",
    "rebind": "rebound by a higher-precedence contributor",
    "sole-candidate-in-scope": "the only node offering this contract in the scope",
    "derived": "created automatically to satisfy this slot",
    "alias": "reached through an alias",
}
_EDGE_REASON = {
    "delivers-requires": "needs a state the other step delivers",
    "invalidates": "ordered so an invalidated state is restored",
    "latent-order": "stable tie-break order",
}

_STYLE = """
:root { --bg:#07090c; --panel:#0c1117; --line:#1c2731; --text:#eef2f6; --muted:#8597a8;
  --orange:#f2a65a; --green:#57c98d; --teal:#54c8c8; --violet:#a88cf0; --red:#f07178; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
  background-image:radial-gradient(circle, #121a22 1px, transparent 1px); background-size:24px 24px;
  font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
main { margin-right:400px; padding:34px 36px 60px; }
h1 { margin:0; font-size:24px; font-weight:650; letter-spacing:.01em; }
.subtitle { color:var(--muted); font-size:13.5px; margin:6px 0 18px; max-width:760px; line-height:1.5; }
.summary { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; }
.summary span { background:#111a22; border:1px solid var(--line); border-radius:999px; padding:4px 11px;
  font-size:12px; color:#c7d3de; }
.legend { display:flex; gap:20px; flex-wrap:wrap; align-items:center; color:var(--muted); font-size:12px; }
.legend span { display:inline-flex; align-items:center; gap:7px; }
.sw { display:inline-block; width:22px; height:13px; border-radius:4px; border:1.6px solid; }
.sw.state { border-color:var(--orange); background:#2a1d10; border-radius:8px; }
.sw.node { border-color:var(--green); background:#10241b; }
.sw.derived { border-color:var(--green); border-style:dashed; background:#10241b; }
.sw.target { border-color:var(--teal); background:#0f2526; border-radius:8px; }
.ln { display:inline-block; width:24px; border-top:1.8px solid #4d6476; }
.ln.uses { border-top:1.8px dashed #9fb3c4; }
.toggle { display:inline-flex; gap:8px; align-items:center; margin-top:14px; color:var(--muted);
  font-size:12.5px; cursor:pointer; user-select:none; }
section.scope { margin-top:28px; background:var(--panel); border:1px solid var(--line); border-radius:16px;
  box-shadow:0 18px 40px -24px #000; overflow:hidden; }
.scope-h { display:flex; align-items:baseline; gap:14px; padding:16px 22px 12px; border-bottom:1px solid var(--line); }
.scope-h h2 { margin:0; font-size:16px; letter-spacing:.06em; text-transform:uppercase; }
.scope-h .meta { color:var(--muted); font-size:12.5px; }
.scope-err { color:var(--red); font-size:12.5px; font-weight:600; }
.state.blocked .box { fill:#211316; stroke:var(--red); }
.state.pending .box { fill:#111820; stroke:#4a5a68; stroke-dasharray:4 4; }
.st-blocked { fill:var(--red); }
.node.missing .box { fill:#211316; stroke:var(--red); stroke-width:2; stroke-dasharray:7 5;
  animation:gap-dash 1.2s linear infinite; }
.node.missing .cross line { stroke:var(--red); stroke-width:3; stroke-linecap:round;
  animation:gap-pulse 1.4s ease-in-out infinite; }
.node.missing .gap-t { fill:var(--red); }
.node.missing:hover .box, .node.missing.sel .box { filter:drop-shadow(0 0 8px rgba(240,113,120,.6)); }
.tree.root.gap path { stroke:var(--red); stroke-dasharray:6 5; }
.uses.gap { opacity:.9; }
.uses.gap path { stroke:var(--red); stroke-width:1.8; }
.b-missing, .b-blocked { color:var(--red); border-color:#6b2f35; }
@keyframes gap-pulse { 0%, 100% { opacity:.25; } 50% { opacity:.85; } }
@keyframes gap-dash { to { stroke-dashoffset:-24; } }
.failure { background:#211316; border:1px solid #6b2f35; border-radius:12px; padding:12px 16px;
  margin:0 0 16px; max-width:1000px; color:var(--red); font-size:13px; }
.failure pre { color:#f2d0d3; white-space:pre-wrap; margin:8px 0 0; font-size:12px;
  font-family:ui-monospace,Menlo,Consolas,monospace; }
.canvas { overflow-x:auto; padding:6px 0 4px; }
svg { display:block; margin:0 auto; }
svg text { font-family:inherit; }
.lane { fill:#5f7385; font-size:10.5px; letter-spacing:.14em; font-weight:600; }
.empty { fill:var(--muted); font-size:12px; font-style:italic; }
.item { cursor:pointer; transition:opacity .15s ease; outline:none; }
.item .box { stroke-width:1.6; transition:stroke-width .15s ease, filter .15s ease; }
.item text { pointer-events:none; text-anchor:middle; }
.t1 { fill:var(--text); font-size:13px; font-weight:600; }
.t2 { fill:var(--muted); font-size:11px; }
.t3 { fill:var(--teal); font-size:9.5px; letter-spacing:.18em; font-weight:700; }
.idx { fill:var(--orange); font-weight:800; }
.node .box { fill:#10241b; stroke:var(--green); }
.node.derived .box { stroke-dasharray:5 4; }
.node.external .box { fill:#111820; stroke:#4a5a68; stroke-dasharray:3 4; }
.state .box { fill:#2a1d10; stroke:var(--orange); }
.target .box { fill:#0f2526; stroke:var(--teal); stroke-width:2; }
.item:hover .box, .item:focus .box, .item.sel .box { stroke-width:3; }
.node:hover .box, .node.sel .box { filter:drop-shadow(0 0 7px rgba(87,201,141,.55)); }
.state:hover .box, .state.sel .box { filter:drop-shadow(0 0 7px rgba(242,166,90,.55)); }
.target:hover .box, .target.sel .box { filter:drop-shadow(0 0 7px rgba(84,200,200,.55)); }
.status { font-size:10.5px; text-anchor:middle; font-weight:600; letter-spacing:.03em; }
.st-ran { fill:var(--green); } .st-held { fill:var(--teal); } .st-planned { fill:var(--orange); }
.st-pending { fill:var(--muted); }
.link { transition:opacity .15s ease; }
.link path, .link line { fill:none; }
.flow line { stroke:var(--orange); stroke-width:2; }
.tree path { stroke:#3f5566; stroke-width:1.7; }
.tree.root path { stroke:#2f7273; }
.tree rect { fill:#0b1015; stroke:#243240; }
.tree text { fill:var(--muted); font-size:10.5px; text-anchor:middle; }
.uses path { stroke:#9fb3c4; stroke-width:1.5; stroke-dasharray:5 5; }
.uses { opacity:0; pointer-events:none; }
body.show-uses .uses { opacity:.3; }
svg.focus .item:not(.on) { opacity:.2; }
svg.focus .link:not(.on) { opacity:.08; }
svg.focus .status { opacity:.35; }
svg.focus .uses.on { opacity:.95; }
svg.focus .link.on path, svg.focus .link.on line { stroke-width:2.6; }
#panel { position:fixed; top:0; right:0; width:400px; height:100vh; overflow-y:auto; background:#0a0f14;
  border-left:1px solid var(--line); padding:26px 24px 40px; font-size:13px; line-height:1.45; }
#panel h3 { margin:6px 0 2px; font-size:19px; word-break:break-word; }
#panel .ref { color:var(--muted); font-size:12px; font-family:ui-monospace,Menlo,Consolas,monospace;
  word-break:break-all; }
.badges { display:flex; gap:6px; flex-wrap:wrap; }
.badge { font-size:10.5px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; border-radius:999px;
  padding:3px 9px; border:1px solid; }
.b-node { color:var(--green); border-color:#2c6b4c; } .b-derived { color:var(--violet); border-color:#4e3f7a; }
.b-external { color:var(--muted); border-color:#3a4a58; }
.b-state { color:var(--orange); border-color:#7a5530; } .b-target { color:var(--teal); border-color:#2b6a6a; }
.b-ran { color:var(--green); border-color:#2c6b4c; } .b-held { color:var(--teal); border-color:#2b6a6a; }
.b-planned { color:var(--orange); border-color:#7a5530; } .b-pending { color:var(--muted); border-color:#3a4a58; }
.grid { display:grid; grid-template-columns:118px 1fr; gap:6px 12px; margin:16px 0 4px; }
.grid .k { color:var(--muted); } .grid .v { word-break:break-word; }
.mono { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12px; }
.sec { margin-top:20px; } .sec h4 { margin:0 0 9px; font-size:10.5px; letter-spacing:.14em; text-transform:uppercase;
  color:#6f8496; border-bottom:1px solid var(--line); padding-bottom:6px; }
.chips { display:flex; gap:5px; flex-wrap:wrap; }
.chip { background:#121c25; border:1px solid #22313e; border-radius:6px; padding:2px 7px; font-size:12px;
  font-family:ui-monospace,Menlo,Consolas,monospace; }
.chip.missing { color:var(--red); border-color:#6b2f35; background:#211316; }
.none { color:#5d6f80; font-style:italic; }
.entry { background:#0e151c; border:1px solid var(--line); border-radius:10px; padding:9px 11px; margin-bottom:8px; }
.entry-h { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.slot-name { font-weight:700; color:#dfe8f0; font-family:ui-monospace,Menlo,Consolas,monospace; }
.arrow { color:#5d6f80; }
.why { color:var(--muted); font-size:12px; margin-top:4px; }
.shape { display:flex; gap:8px; align-items:center; margin-top:6px; flex-wrap:wrap; }
.shape .lbl { color:#6f8496; font-size:11px; width:52px; }
button.jump { background:none; border:0; padding:0; color:#7fc8ff; cursor:pointer; font:inherit;
  font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12.5px; text-align:left; }
button.jump:hover { text-decoration:underline; } button.jump:disabled { color:var(--muted); cursor:default; }
.intro p { color:var(--muted); margin:8px 0; } .intro b { color:var(--text); }
.hint { color:#5d6f80; font-size:11.5px; margin-top:18px; }
@media (max-width:1100px) { main { margin-right:0; } #panel { position:static; width:auto; height:auto;
  border-left:0; border-top:1px solid var(--line); } }
"""

_SCRIPT = r"""
(function () {
  var DATA = JSON.parse(document.getElementById("itf-data").textContent);
  var ITEMS = DATA.items;
  var body = document.getElementById("panel-body");
  var pinned = null;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }
  function clear() { while (body.firstChild) body.removeChild(body.firstChild); }
  function section(title) {
    var s = el("div", "sec"); s.appendChild(el("h4", null, title)); body.appendChild(s); return s;
  }
  function none(parent) { parent.appendChild(el("div", "none", "none")); }
  function chips(parent, items, cls) {
    var w = el("div", "chips");
    if (!items || !items.length) { w.appendChild(el("span", "none", "none")); }
    (items || []).forEach(function (t) { w.appendChild(el("span", "chip " + (cls || ""), t)); });
    parent.appendChild(w);
  }
  function grid(parent, rows) {
    var g = el("div", "grid");
    rows.forEach(function (r) {
      if (r[1] === undefined || r[1] === null || r[1] === "") return;
      g.appendChild(el("div", "k", r[0]));
      g.appendChild(el("div", "v" + (r[2] ? " mono" : ""), r[1]));
    });
    parent.appendChild(g);
  }
  function jump(parent, id, text) {
    var b = el("button", "jump", text);
    if (ITEMS[id]) { b.addEventListener("click", function () { pin(id); }); } else { b.disabled = true; }
    parent.appendChild(b);
  }
  function header(badges, title, ref) {
    var b = el("div", "badges");
    badges.forEach(function (x) { b.appendChild(el("span", "badge b-" + x[0], x[1])); });
    body.appendChild(b);
    body.appendChild(el("h3", null, title));
    body.appendChild(el("div", "ref", ref));
  }
  function shapes(parent, e) {
    [["expects", e.expected, ""], ["gets", e.given, ""], ["missing", e.missing, "missing"]].forEach(function (s) {
      if (!s[1] || !s[1].length) return;
      var r = el("div", "shape"); r.appendChild(el("span", "lbl", s[0])); chips(r, s[1], s[2]); parent.appendChild(r);
    });
  }
  function refList(title, list, withSlot, extra) {
    var s = section(title);
    if (!list.length) { none(s); return; }
    list.forEach(function (x) {
      var e = el("div", "entry"); var h = el("div", "entry-h");
      if (withSlot) { h.appendChild(el("span", "slot-name", x.slot)); h.appendChild(el("span", "arrow", "\u2192")); }
      jump(h, x.id, x.label); e.appendChild(h);
      if (extra) extra(e, x);
      s.appendChild(e);
    });
  }

  var RENDER = {
    node: function (it) {
      var badges = [["node", "capability"]];
      if (it.derived) badges.push(["derived", "derived"]);
      header(badges, it.title, it.ref);
      grid(body, [["contract", it.contract, 1], ["provider", it.provider, 1], ["chosen because", it.why_provider],
                  ["implementation", it.impl, 1], ["scope", it.scope]]);
      var s = section("configuration");
      if (it.config.length) { grid(s, it.config.map(function (p) { return [p[0], p[1], 1]; })); } else { none(s); }
      if (it.config_schema && it.config_schema.length) {
        s = section("provider config schema");
        it.config_schema.forEach(function (f) {
          var entry = el("div", "entry");
          entry.appendChild(el("div", "slot-name", f.name));
          entry.appendChild(el("div", "why", f.type + " · " +
            (f.required ? "required" : "optional" + (Object.hasOwn(f, "default") ? " · default " + f.default : "")) +
            (f.sensitive ? " · sensitive" : "")));
          s.appendChild(entry);
        });
      }
      if (it.config_issues && it.config_issues.length) {
        s = section("config errors");
        it.config_issues.forEach(function (message) { s.appendChild(el("div", "entry", message)); });
      }
      refList("slots \u2014 what it consumes", it.slots, true, function (e, x) {
        if (x.why) e.appendChild(el("div", "why", x.why));
        shapes(e, x);
      });
      refList("consumed by", it.consumed_by, false, function (e, x) {
        e.appendChild(el("div", "why", "through its \u201c" + x.slot + "\u201d slot"));
      });
      refList("used by bring-up steps", it.used_by, false, function (e, x) {
        e.appendChild(el("div", "why", "through its \u201c" + x.slot + "\u201d slot"));
      });
    },
    state: function (it) {
      header([["state", "state"], [it.status, it.status_text]], it.title, it.ref);
      grid(body, [["bring-up order", "#" + it.order + " of " + it.total], ["implementation", it.impl, 1],
                  ["probe", it.probe || "none (unprobed)", 1], ["scope", it.scope]]);
      var s = section("delivers"); chips(s, it.delivers);
      s = section("requires"); chips(s, it.requires);
      s = section("invalidates"); chips(s, it.invalidates);
      refList("uses capabilities", it.uses, true, function (e, x) { shapes(e, x); });
      var why = function (e, x) { e.appendChild(el("div", "why", x.reason + " \u00b7 " + x.state)); };
      refList("runs after", it.after, false, why);
      refList("runs before", it.before, false, why);
    },
    target: function (it) {
      header([["target", "target"]], it.title, "scope " + it.ref);
      grid(body, it.counts);
      var s = section("goals"); chips(s, it.goals);
      s = section("already held at plan time"); chips(s, it.held);
      s = section("assumed without evidence"); chips(s, it.assumed);
      refList("made of", it.top_level, false);
      s = section("aliases");
      if (it.aliases.length) { grid(s, it.aliases.map(function (a) { return [a[0], "\u2192 " + a[1], 1]; })); }
      else { none(s); }
    },
    wanted: function (it) {
      header([["state", "state"], [it.status, it.status_text]], it.title, it.ref);
      grid(body, [["scope", it.scope], ["why", it.why]]);
      refList("missing capabilities", it.uses, true);
    },
    missing: function (it) {
      header([["missing", "missing capability"]], it.title, it.ref);
      grid(body, [["contract", it.contract, 1], ["scope", it.scope], ["needed by", it.action, 1],
                  ["slot", it.slot, 1], ["why", it.why]]);
      refList("blocks", it.blocks, false);
      refList("exists in other scopes", it.elsewhere, false);
      var s = section("fix"); s.appendChild(el("div", "entry mono", it.fix));
    }
  };

  function intro() {
    clear();
    var d = el("div", "intro");
    d.appendChild(el("h3", null, "How to read this"));
    [["Bring-up order", " \u2014 every state ITF had to reach, left to right in the order it executed them, with what happened to each underneath."],
     ["Composition", " \u2014 the target at the top, the capabilities it is made of below it, and what each of those consumes, nested as deep as the plan goes. Edge labels name the slot."],
     ["Dashed border", " \u2014 a derived capability: nobody declared it, ITF created it to satisfy a slot."],
     ["Hover", " to preview, click to pin. Click any reference in this panel to jump to it."]].forEach(function (p) {
      var e = el("p"); e.appendChild(el("b", null, p[0])); e.appendChild(document.createTextNode(p[1])); d.appendChild(e);
    });
    body.appendChild(d);
    body.appendChild(el("div", "hint", "Esc or a click on empty space clears the selection."));
  }

  function show(id) {
    var it = ITEMS[id];
    if (!it) { intro(); return; }
    clear(); RENDER[it.kind](it); body.scrollTop = 0;
  }

  function focus(id) {
    var on = {};
    if (id) { on[id] = true; ((ITEMS[id] || {}).related || []).forEach(function (r) { on[r] = true; }); }
    document.querySelectorAll("svg[data-graph]").forEach(function (svg) {
      var has = false;
      svg.querySelectorAll(".item").forEach(function (n) {
        var i = n.getAttribute("data-id");
        n.classList.toggle("on", !!on[i]); n.classList.toggle("sel", i === id);
        if (i === id) has = true;
      });
      svg.querySelectorAll(".link").forEach(function (l) {
        var a = l.getAttribute("data-a"), b = l.getAttribute("data-b");
        l.classList.toggle("on", !!id && (a === id || b === id) && !!on[a] && !!on[b]);
      });
      svg.classList.toggle("focus", has);
    });
  }

  function pin(id) { pinned = id; show(id); focus(id); }
  function unpin() { pinned = null; intro(); focus(null); }

  document.querySelectorAll(".item").forEach(function (n) {
    var id = n.getAttribute("data-id");
    n.addEventListener("mouseenter", function () { show(id); focus(id); });
    n.addEventListener("mouseleave", function () { if (pinned) { show(pinned); focus(pinned); } else { intro(); focus(null); } });
    n.addEventListener("click", function (ev) { ev.stopPropagation(); if (pinned === id) { unpin(); } else { pin(id); } });
    n.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pin(id); } });
  });
  document.querySelector("main").addEventListener("click", function () { if (pinned) unpin(); });
  document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") unpin(); });
  var toggle = document.getElementById("show-uses");
  toggle.addEventListener("click", function (ev) { ev.stopPropagation(); });
  toggle.addEventListener("change", function () { document.body.classList.toggle("show-uses", toggle.checked); });
  intro();
})();
"""


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _clip(text: str, width_px: float, char_px: float) -> str:
    limit = max(int(width_px / char_px), 4)
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def _script_json(data) -> str:
    """JSON safe to embed in a <script> element: no sequence in it can close the element early."""
    raw = json.dumps(data, sort_keys=True, default=str)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _resolve(target_plan, ref):
    try:
        return target_plan.resolve(ref)
    except KeyError:
        return None


def _token(key: str) -> str:
    return key.split(":", 1)[1] if ":" in key else key


def _status(step, action_plan, run_report) -> tuple[str, str]:
    if run_report is not None:
        if step.key in run_report.executed:
            return "ran", "ran"
        if step.key in run_report.skipped:
            return "held", "already held \u00b7 skipped"
        return "pending", "not run"
    if set(step.delivers) & set(action_plan.observed_at_plan_time):
        return "held", "held at plan time"
    return "planned", "planned"


def _layers(refs, children) -> tuple[dict, list]:
    """Depth of every ref below the target: 1 for what nothing else in `refs` consumes, otherwise
    one deeper than its deepest consumer (longest path), so nesting of any depth gets its own row.
    Bounded by `len(refs)`, so a cycle can never loop forever."""
    in_set = set(refs)
    consumed = {c for p in refs for _, c in children.get(p, ()) if c in in_set}
    roots = [r for r in refs if r not in consumed] or list(refs)
    layer = {r: 1 for r in roots}
    limit = len(refs) + 1
    for _ in range(limit):
        changed = False
        for p in list(layer):
            for _, c in children.get(p, ()):
                depth = layer[p] + 1
                if c in in_set and depth > layer.get(c, 0) and depth <= limit:
                    layer[c] = depth
                    changed = True
        if not changed:
            break
    for r in refs:
        layer.setdefault(r, 1)
    return layer, roots


def _build_items(target_plan, action_plan, run_report, scopes, config_schemas, config_issues, gaps=None) -> dict:
    items: dict[str, dict] = {}
    node_scope = {n.ref: n.scope for n in target_plan.nodes}
    seams = {(s.consumer, s.slot): s for s in target_plan.seams}

    def shape(consumers, slot) -> dict:
        for consumer in consumers:
            seam = seams.get((consumer, slot))
            if seam is not None:
                expected, given = list(seam.expected), list(seam.given)
                return {"expected": expected, "given": given, "missing": sorted(set(expected) - set(given))}
        return {"expected": [], "given": [], "missing": []}

    consumed_by: dict[str, list] = {}
    for n in target_plan.nodes:
        for slot, ref in n.bindings:
            r = _resolve(target_plan, ref) or ref
            consumed_by.setdefault(r, []).append({"id": f"n|{n.ref}", "label": n.ref, "slot": slot})
    used_by: dict[str, list] = {}
    for st in action_plan.steps:
        for slot, ref in st.uses:
            r = _resolve(target_plan, ref) or ref
            used_by.setdefault(r, []).append({"id": f"s|{st.key}", "label": st.key, "slot": slot})

    top_level: dict[str, list] = {}
    for n in target_plan.nodes:
        why_b = dict(n.why_bindings)
        slots = []
        for slot, ref in n.bindings:
            r = _resolve(target_plan, ref) or ref
            why = why_b.get(slot, "")
            slots.append(
                {"id": f"n|{r}", "label": r, "slot": slot, "why": _WHY_BINDING.get(why, why), **shape((n.ref,), slot)}
            )
        cb, ub = consumed_by.get(n.ref, []), used_by.get(n.ref, [])
        related = [s["id"] for s in slots] + [c["id"] for c in cb] + [u["id"] for u in ub]
        if not any(node_scope.get(c["label"]) == n.scope for c in cb):
            top_level.setdefault(n.scope, []).append(n)
            related.append(f"t|{n.scope}")
        items[f"n|{n.ref}"] = {
            "kind": "node",
            "title": n.name,
            "ref": n.ref,
            "scope": n.scope,
            "contract": n.contract,
            "provider": n.provider,
            "impl": n.impl,
            "derived": n.derived,
            "why_provider": _WHY_PROVIDER.get(n.why_provider, n.why_provider),
            "config": [[k, "null" if v is None else str(v)] for k, v in n.config],
            "config_schema": config_schemas.get(n.provider, []),
            "config_issues": [message for ref, _, message in config_issues if ref == n.ref],
            "slots": slots,
            "consumed_by": cb,
            "used_by": ub,
            "related": related,
        }

    after: dict[str, list] = {}
    before: dict[str, list] = {}
    for e in action_plan.edges:
        reason = _EDGE_REASON.get(e.reason, e.reason)
        after.setdefault(e.after, []).append(
            {"id": f"s|{e.before}", "label": e.before, "reason": reason, "state": e.state}
        )
        before.setdefault(e.before, []).append(
            {"id": f"s|{e.after}", "label": e.after, "reason": reason, "state": e.state}
        )

    steps_by_scope: dict[str, list] = {}
    for st in action_plan.steps:
        steps_by_scope.setdefault(st.key.split(":", 1)[0], []).append(st)
    for scope, steps in steps_by_scope.items():
        for i, st in enumerate(steps):
            status, status_text = _status(st, action_plan, run_report)
            uses = []
            for slot, ref in st.uses:
                r = _resolve(target_plan, ref) or ref
                uses.append({"id": f"n|{r}", "label": r, "slot": slot, **shape((st.key,) + tuple(st.delivers), slot)})
            aft, bef = after.get(st.key, []), before.get(st.key, [])
            items[f"s|{st.key}"] = {
                "kind": "state",
                "title": _token(st.key),
                "ref": st.key,
                "scope": scope,
                "order": i + 1,
                "total": len(steps),
                "impl": st.impl,
                "probe": st.probe,
                "probes": dict(st.state_probes()),
                "delivers": list(st.delivers),
                "requires": list(st.requires),
                "invalidates": list(st.invalidates),
                "uses": uses,
                "after": aft,
                "before": bef,
                "status": status,
                "status_text": status_text,
                "related": [u["id"] for u in uses] + [a["id"] for a in aft] + [b["id"] for b in bef],
            }

    for scope in scopes:
        pre = f"{scope}:"
        scoped = [n for n in target_plan.nodes if n.scope == scope]
        tops = sorted(top_level.get(scope, []), key=lambda n: n.name)
        gap = (gaps or {}).get(scope)
        goals = gap["goals"] if gap and not action_plan.steps else [g for g in action_plan.goals if g.startswith(pre)]
        items[f"t|{scope}"] = {
            "kind": "target",
            "title": scope,
            "ref": scope,
            "goals": [_token(g) for g in goals],
            "held": [_token(g) for g in action_plan.observed_at_plan_time if g.startswith(pre)],
            "assumed": [_token(g) for g in action_plan.assumed if g.startswith(pre)],
            "top_level": [{"id": f"n|{n.ref}", "label": n.name} for n in tops],
            "aliases": [[a, b] for a, b in target_plan.aliases if a.startswith(f"{scope}.")],
            "counts": [
                ["capabilities", str(len(scoped))],
                ["derived", str(sum(1 for n in scoped if n.derived))],
                ["bring-up steps", str(len(steps_by_scope.get(scope, [])))],
            ],
            "related": [f"n|{n.ref}" for n in tops],
        }
        if gap and not action_plan.steps:
            _add_gap_items(items, scope, gap)
    return items


def _add_gap_items(items: dict, scope: str, gap: dict) -> None:
    for key in gap["wanted"]:
        misses = gap["blocked"].get(key, [])
        items[f"s|{key}"] = {
            "kind": "wanted",
            "title": _token(key),
            "ref": key,
            "scope": scope,
            "status": "blocked" if misses else "pending",
            "status_text": "blocked" if misses else "not planned",
            "why": misses[0]["why"] if misses else ("a goal" if key in gap["goals"] else ""),
            "uses": [{"id": f"n|{m['ghost']}", "label": m["contract"], "slot": m["slot"]} for m in misses],
            "related": [f"n|{m['ghost']}" for m in misses],
        }
    for ghost, m in gap["ghosts"].items():
        items[f"n|{ghost}"] = {
            "kind": "missing",
            "title": m["slot"],
            "ref": f"{scope}.{m['slot']} (missing)",
            "scope": scope,
            "contract": m["contract"],
            "action": m["action"],
            "slot": m["slot"],
            "why": m["why"],
            "fix": m["fix"],
            "blocks": [{"id": f"s|{m['key']}", "label": m["key"]}],
            "elsewhere": [{"id": f"n|{r}", "label": r} for r in m["elsewhere"]],
            "related": [f"s|{m['key']}", f"t|{scope}"] + [f"n|{r}" for r in m["elsewhere"]],
        }
    items[f"t|{scope}"]["related"] += [f"n|{g}" for g in gap["ghosts"]]


def _gaps(failure, goals) -> dict:
    """Per scope, what a failed Gate 2 wanted and what it lacked: the plan as if it had resolved."""
    out: dict[str, dict] = {}

    def scope_of(key):
        return out.setdefault(key.split(":", 1)[0], {"goals": [], "wanted": [], "blocked": {}, "ghosts": {}})

    for g in sorted(goals):
        scope_of(g)["goals"].append(g)
    for d in failure.diagnostics:
        ev = dict(d.evidence)
        if d.code != "USES_UNSATISFIED" or "contract" not in ev:
            continue
        key = d.subject.split("#", 1)[0]
        fix = next(
            (ln.strip()[len("Fix: ") :] for ln in TEMPLATES[d.code](d).splitlines() if ln.strip().startswith("Fix: ")),
            "",
        )
        ghost = f"{ev['scope']}.{ev['slot']}!missing"
        why = f"required by {ev['required_by']} (a goal)" if ev.get("required_by") else "a goal"
        miss = {
            "key": key,
            "ghost": ghost,
            "slot": ev["slot"],
            "contract": ev["contract"],
            "action": ev["action"],
            "why": why,
            "fix": fix,
            "elsewhere": [r for r in ev.get("elsewhere", "").split(", ") if r],
        }
        gap = scope_of(key)
        gap["blocked"].setdefault(key, []).append(miss)
        gap["ghosts"][ghost] = miss
    for gap in out.values():
        gap["wanted"] = sorted(set(gap["goals"]) | set(gap["blocked"]), key=lambda k: (k not in gap["blocked"], k))
    return {s: g for s, g in out.items() if g["blocked"]}


def _link(cls, a, b, inner) -> str:
    return f'<g class="link {cls}" data-a="{_esc(a)}" data-b="{_esc(b)}">{inner}</g>'


def _vcurve(x1, y1, x2, y2, marker) -> str:
    bend = max((y2 - y1) * 0.5, 30)
    return (
        f'<path d="M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + bend:.1f} {x2:.1f},{y2 - bend:.1f} {x2:.1f},{y2 - 2:.1f}" '
        f'marker-end="url(#{marker})" />'
    )


def _pill(x, y, text) -> str:
    text = _clip(text, 150, 6.3)
    w = len(text) * 6.3 + 16
    return (
        f'<rect x="{x - w / 2:.1f}" y="{y - 10:.1f}" width="{w:.1f}" height="19" rx="9.5" />'
        f'<text x="{x:.1f}" y="{y + 3.5:.1f}">{_esc(text)}</text>'
    )


def _state_width(index: int, label: str) -> float:
    return max(118.0, 7.4 * (len(label) + len(str(index))) + 44)


def _ghost_card(ref: str, miss: dict, x: float, y: float) -> str:
    """A capability the plan needed and the target lacks: red, dashed, crossed out."""
    mx, x2, y2 = x + _NODE_W / 2, x + _NODE_W - 14, y + _NODE_H - 10
    return (
        f'<g class="item node missing" data-id="{_esc("n|" + ref)}" tabindex="0">'
        f'<rect class="box" x="{x:.1f}" y="{y:.1f}" width="{_NODE_W}" height="{_NODE_H}" rx="12" />'
        f'<g class="cross"><line x1="{x + 14:.1f}" y1="{y + 10:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" />'
        f'<line x1="{x2:.1f}" y1="{y + 10:.1f}" x2="{x + 14:.1f}" y2="{y2:.1f}" /></g>'
        f'<text class="t1" x="{mx:.1f}" y="{y + 25:.1f}">{_esc(_clip(miss["slot"], _NODE_W - 20, 7.4))}</text>'
        f'<text class="t2 gap-t" x="{mx:.1f}" y="{y + 43:.1f}">'
        f"{_esc(_clip('missing: ' + miss['contract'], _NODE_W - 20, 6.3))}</text></g>"
    )


def _scope_section(index: int, scope: str, target_plan, action_plan, items, failure=None, gap=None) -> str:
    uid = f"g{index}"
    node_by_ref = {n.ref: n for n in target_plan.nodes}
    nodes = sorted((n for n in target_plan.nodes if n.scope == scope), key=lambda n: n.name)
    children: dict[str, list] = {}
    for n in nodes:
        for slot, ref in n.bindings:
            r = _resolve(target_plan, ref)
            if r and r != n.ref:
                children.setdefault(n.ref, []).append((slot, r))
    externals = sorted(
        {c for kids in children.values() for _, c in kids if c in node_by_ref and node_by_ref[c].scope != scope}
    )
    pre = f"{scope}:"
    steps = [s for s in action_plan.steps if s.key.startswith(pre)]
    wanted = gap if gap and not steps else None
    ghosts = wanted["ghosts"] if wanted else {}
    refs = [n.ref for n in nodes] + externals + list(ghosts)
    layer, roots = _layers(refs, children)
    roots = [r for r in roots if r not in externals]
    if wanted:
        steps = [
            _Wanted(k, tuple((m["slot"], m["ghost"]) for m in wanted["blocked"].get(k, []))) for k in wanted["wanted"]
        ]
    widths = [_state_width(i + 1, _token(s.key)) for i, s in enumerate(steps)]
    rel_x, cursor = [], 0.0
    for w in widths:
        rel_x.append(cursor)
        cursor += w + _STATE_GAP
    pipeline_w = cursor - _STATE_GAP if steps else 0.0
    state_mid = {s.key: rel_x[i] + widths[i] / 2 - pipeline_w / 2 for i, s in enumerate(steps)}

    users: dict[str, list] = {}
    for s in steps:
        for _slot, ref in s.uses:
            r = ref if ref in ghosts else _resolve(target_plan, ref)
            if r:
                users.setdefault(r, []).append(state_mid[s.key])
    parents: dict[str, list] = {}
    for p, kids in children.items():
        for _, c in kids:
            parents.setdefault(c, []).append(p)

    def name_of(ref):
        return node_by_ref[ref].name if ref in node_by_ref else ref

    max_layer = max(layer.values(), default=0)
    placed: dict[str, float] = {}
    row_widths = []
    for k in range(1, max_layer + 1):
        row = [r for r in refs if layer[r] == k]

        def anchor(ref, depth=k):
            xs = [placed[p] for p in parents.get(ref, ()) if p in placed] if depth > 1 else []
            xs = xs or users.get(ref, [])
            return (0, sum(xs) / len(xs), name_of(ref)) if xs else (1, 0.0, name_of(ref))

        row.sort(key=anchor)
        total = len(row) * _NODE_W + (len(row) - 1) * _NODE_GAP
        row_widths.append(total)
        for i, r in enumerate(row):
            placed[r] = -total / 2 + i * (_NODE_W + _NODE_GAP) + _NODE_W / 2

    width = max([pipeline_w, float(_TARGET_W)] + row_widths) + 2 * _MARGIN
    cx = width / 2
    lane2 = _STATE_TOP + _STATE_H + 64
    target_top = lane2 + 20

    def layer_top(k):
        return target_top + _TARGET_H + 64 + (k - 1) * _LAYER_GAP

    height = (layer_top(max_layer) + _NODE_H if max_layer else target_top + _TARGET_H) + _MARGIN
    state_x0 = cx - pipeline_w / 2
    target_id = f"t|{scope}"

    links, labels, cards = [], [], []
    for i in range(len(steps) - 1 if not wanted else 0):
        y = _STATE_TOP + _STATE_H / 2
        x1, x2 = state_x0 + rel_x[i] + widths[i], state_x0 + rel_x[i + 1]
        links.append(
            _link(
                "flow",
                f"s|{steps[i].key}",
                f"s|{steps[i + 1].key}",
                f'<line x1="{x1 + 2:.1f}" y1="{y}" x2="{x2 - 3:.1f}" y2="{y}" marker-end="url(#mf-{uid})" />',
            )
        )

    for r in roots:
        links.append(
            _link(
                "tree root gap" if r in ghosts else "tree root",
                target_id,
                f"n|{r}",
                _vcurve(cx, target_top + _TARGET_H, cx + placed[r], layer_top(layer[r]), f"mt-{uid}"),
            )
        )
    for p, kids in children.items():
        if p not in placed:
            continue
        for slot, c in kids:
            if c not in placed:
                continue
            x1, y1 = cx + placed[p], layer_top(layer[p]) + _NODE_H
            x2, y2 = cx + placed[c], layer_top(layer[c])
            links.append(_link("tree", f"n|{p}", f"n|{c}", _vcurve(x1, y1, x2, y2, f"me-{uid}")))
            labels.append(_link("tree", f"n|{p}", f"n|{c}", _pill((x1 + x2) / 2, (y1 + y2) / 2, slot)))

    for s in steps:
        sx, sy = cx + state_mid[s.key], _STATE_TOP + _STATE_H
        for _slot, ref in s.uses:
            if ref in ghosts:
                links.append(
                    _link(
                        "uses gap",
                        f"s|{s.key}",
                        f"n|{ref}",
                        _vcurve(sx, sy, cx + placed[ref], layer_top(layer[ref]), f"mx-{uid}"),
                    )
                )
                continue
            r = _resolve(target_plan, ref)
            if r in placed:
                links.append(
                    _link(
                        "uses",
                        f"s|{s.key}",
                        f"n|{r}",
                        _vcurve(sx, sy, cx + placed[r], layer_top(layer[r]), f"mu-{uid}"),
                    )
                )

    for i, s in enumerate(steps):
        item = items[f"s|{s.key}"]
        x, label = state_x0 + rel_x[i], _token(s.key)
        mid = x + widths[i] / 2
        cls = f"state {item['status']}" if wanted else "state"
        idx = "" if wanted else f'<tspan class="idx">{i + 1}</tspan><tspan dx="8">'
        cards.append(
            f'<g class="item {cls}" data-id="{_esc("s|" + s.key)}" tabindex="0">'
            f'<rect class="box" x="{x:.1f}" y="{_STATE_TOP}" width="{widths[i]:.1f}" height="{_STATE_H}" rx="22" />'
            f'<text class="t1" x="{mid:.1f}" y="{_STATE_TOP + 27}">{idx}'
            f"{_esc(label)}{'' if wanted else '</tspan>'}</text></g>"
            f'<text class="status st-{item["status"]}" x="{mid:.1f}" y="{_STATE_TOP + _STATE_H + 18}">'
            f"{_esc(item['status_text'])}</text>"
        )
    if not steps:
        empty = (
            f"no action plan: Gate {failure.gate} failed, see the error above"
            if failure is not None
            else "no bring-up steps were planned for this scope"
        )
        cards.append(f'<text class="empty" x="{_MARGIN}" y="{_STATE_TOP + 26}">{_esc(empty)}</text>')

    tx = cx - _TARGET_W / 2
    cards.append(
        f'<g class="item target" data-id="{_esc(target_id)}" tabindex="0">'
        f'<rect class="box" x="{tx:.1f}" y="{target_top}" width="{_TARGET_W}" height="{_TARGET_H}" rx="25" />'
        f'<text class="t3" x="{cx:.1f}" y="{target_top + 19}">TARGET</text>'
        f'<text class="t1" x="{cx:.1f}" y="{target_top + 37}">{_esc(_clip(scope, _TARGET_W - 24, 7.4))}</text></g>'
    )
    for r in refs:
        x, y = cx + placed[r] - _NODE_W / 2, layer_top(layer[r])
        if r in ghosts:
            cards.append(_ghost_card(r, ghosts[r], x, y))
            continue
        n = node_by_ref.get(r)
        if n is None:
            continue
        cls = "node external" if r in externals else ("node derived" if n.derived else "node")
        sub = f"in scope {n.scope}" if r in externals else n.contract
        cards.append(
            f'<g class="item {cls}" data-id="{_esc("n|" + r)}" tabindex="0">'
            f'<rect class="box" x="{x:.1f}" y="{y:.1f}" width="{_NODE_W}" height="{_NODE_H}" rx="12" />'
            f'<text class="t1" x="{x + _NODE_W / 2:.1f}" y="{y + 25:.1f}">{_esc(_clip(n.name, _NODE_W - 20, 7.4))}</text>'
            f'<text class="t2" x="{x + _NODE_W / 2:.1f}" y="{y + 43:.1f}">{_esc(_clip(sub, _NODE_W - 20, 6.3))}</text></g>'
        )

    def marker(mid, color):
        return (
            f'<marker id="{mid}-{uid}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{color}" /></marker>'
        )

    defs = (
        "<defs>"
        + marker("mf", "#f2a65a")
        + marker("mt", "#2f7273")
        + marker("me", "#3f5566")
        + marker("mu", "#9fb3c4")
        + marker("mx", "#f07178")
        + "</defs>"
    )
    lane1 = "WANTED · NOT PLANNED" if wanted else "BRING-UP ORDER"
    lanes = (
        f'<text class="lane" x="{_MARGIN}" y="26">{lane1}</text>'
        f'<text class="lane" x="{_MARGIN}" y="{lane2}">COMPOSITION</text>'
    )
    svg = (
        f'<svg data-graph="1" viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" height="{height:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg">{defs}{lanes}{"".join(links)}{"".join(labels)}{"".join(cards)}</svg>'
    )
    meta = f"{len(nodes)} capabilities \u00b7 {sum(1 for n in nodes if n.derived)} derived \u00b7 " + (
        f"{len(steps)} wanted states \u00b7 {len(wanted['blocked'])} blocked \u00b7 {len(ghosts)} missing capabilities"
        if wanted
        else f"{len(steps)} bring-up steps \u00b7 {max_layer} level(s) deep"
    )
    errors = sum(1 for d in failure.diagnostics if d.subject.startswith((f"{scope}:", f"{scope}."))) if failure else 0
    err = f'<span class="scope-err">{errors} error(s)</span>' if errors else ""
    return (
        f'<section class="scope"><div class="scope-h"><h2>{_esc(scope)}</h2>'
        f'<span class="meta">{_esc(meta)}</span>{err}</div><div class="canvas">{svg}</div></section>'
    )


def render_target_html(
    target_plan,
    action_plan,
    *,
    title: str = "itf target",
    run_report=None,
    config_schemas=None,
    config_issues=(),
    failure=None,
    goals=(),
) -> str:
    """Render a resolved plan as one self-contained, interactive HTML page.

    `action_plan` may be `None` (Gate 1 resolved, Gate 2 did not); `run_report`, when given, marks
    each state as ran / already held; `failure` (a `ResolutionFailed`) is shown above the scopes,
    and with `goals` ("scope:token") a scope it blocks is drawn as wanted, its gaps in red.
    """
    if action_plan is None:
        action_plan = _EMPTY_ACTION_PLAN
    gaps = _gaps(failure, goals) if failure is not None and not action_plan.steps else {}
    step_scopes = {s.key.split(":", 1)[0] for s in action_plan.steps}
    scopes = sorted(set(target_plan.scopes()) | step_scopes)
    items = _build_items(target_plan, action_plan, run_report, scopes, config_schemas or {}, config_issues, gaps)
    sections = "".join(
        _scope_section(i, s, target_plan, action_plan, items, failure, gaps.get(s)) for i, s in enumerate(scopes)
    )

    nodes = target_plan.nodes
    summary = [
        f"{len(scopes)} scope(s)",
        f"{len(nodes)} capabilities",
        f"{sum(1 for n in nodes if n.derived)} derived",
        f"{len(action_plan.steps)} bring-up steps",
    ]
    if run_report is not None:
        summary += [f"{len(run_report.executed)} ran", f"{len(run_report.skipped)} already held"]
    if action_plan.assumed:
        summary.append(f"{len(action_plan.assumed)} assumed")
    banner = ""
    if failure is not None:
        banner = (
            f'<div class="failure"><b>Gate {failure.gate} \u00b7 {_esc(failure.hook)} failed: '
            "nothing was brought up</b>"
            f"<pre>{_esc(render(failure.diagnostics, gate=failure.gate, hook=failure.hook))}</pre></div>"
        )
    legend = (
        '<div class="legend">'
        '<span><i class="sw state"></i>state</span><span><i class="sw target"></i>target</span>'
        '<span><i class="sw node"></i>capability</span><span><i class="sw derived"></i>derived capability</span>'
        '<span><i class="ln"></i>consumes (labeled by slot)</span><span><i class="ln uses"></i>state uses capability</span>'
        "</div>"
    )
    header = (
        f"<header><h1>{_esc(title)}</h1>"
        '<p class="subtitle">What ITF resolved and how it brought it up: the states it reached in order, '
        "and the capabilities the target is made of. Hover or click anything for its provenance.</p>"
        '<div class="summary">' + "".join(f"<span>{_esc(s)}</span>" for s in summary) + "</div>"
        f"{banner}{legend}"
        '<label class="toggle"><input type="checkbox" id="show-uses" /> show every state \u2192 capability link</label>'
        "</header>"
    )
    return display(
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />'
        f"<title>{_esc(title)}</title><style>{_STYLE}</style></head><body>"
        f"<main>{header}{sections}</main>"
        '<aside id="panel"><div id="panel-body"></div></aside>'
        f'<script type="application/json" id="itf-data">{_script_json({"items": items})}</script>'
        f"<script>{_SCRIPT}</script>"
        "</body></html>"
    )
