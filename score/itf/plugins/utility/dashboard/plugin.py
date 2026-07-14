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
"""ITF Dashboard — a read-only web UI showing composition graph and test progress.

Usage in conftest::

    pytest_plugins = [
        "score.itf.core.itf_plugin",
        "score.itf.plugins.utility.dashboard.plugin",
    ]

CLI flags::

    --itf-dashboard              Enable the dashboard (default: off)
    --itf-dashboard-port         Port to serve on (default: 8099)
    --itf-dashboard-snapshot     Path for HTML snapshot on completion/crash

The dashboard is a utility plugin — it doesn't contribute capabilities to the
DUT, it observes the framework and reports status via a lightweight HTTP server.

On session end (or crash), an HTML snapshot is dumped with all state embedded
as static data — viewable offline without the server running.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from score.itf.core.ctf.dut import DUT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State collector
# ---------------------------------------------------------------------------
@dataclass
class DashboardState:
    """Accumulated state visible to the dashboard."""

    # Composition graph
    contracts: list[str] = field(default_factory=list)
    spine: list[str] = field(default_factory=list)
    unavailable: dict[str, str] = field(default_factory=dict)
    tier_map: dict[str, int] = field(default_factory=dict)
    disabled: list[str] = field(default_factory=list)
    edges: list[dict[str, str]] = field(default_factory=list)
    node_types: dict[str, str] = field(default_factory=dict)
    materialized: list[str] = field(default_factory=list)

    # Lifecycle
    phases_completed: list[str] = field(default_factory=list)
    verify_results: list[dict[str, Any]] = field(default_factory=list)

    # Test execution
    tests_collected: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    current_test: str | None = None
    test_log: list[dict[str, Any]] = field(default_factory=list)

    # Timing
    session_start: float = 0.0
    crashed: bool = False

    # Startup checks (verify phase results)
    startup_checks: list[dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        elapsed = time.time() - self.session_start if self.session_start else 0
        return {
            "composition": {
                "contracts": self.contracts,
                "spine": self.spine,
                "unavailable": self.unavailable,
                "tier_map": self.tier_map,
                "disabled": self.disabled,
                "edges": self.edges,
                "node_types": self.node_types,
                "materialized": self.materialized,
            },
            "lifecycle": {
                "phases_completed": self.phases_completed,
                "verify_results": self.verify_results,
                "startup_checks": self.startup_checks,
            },
            "tests": {
                "collected": self.tests_collected,
                "passed": self.tests_passed,
                "failed": self.tests_failed,
                "skipped": self.tests_skipped,
                "current": self.current_test,
                "log": self.test_log[-100:],
            },
            "elapsed_seconds": round(elapsed, 2),
            "crashed": self.crashed,
        }


# ---------------------------------------------------------------------------
# HTTP server (runs in a daemon thread)
# ---------------------------------------------------------------------------
_state: DashboardState | None = None


def _make_handler():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/api/state":
                body = json.dumps(_state.snapshot() if _state else {}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/" or self.path == "/index.html":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(_build_html(live=True).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):  # noqa: A002
            pass

    return Handler


def _start_server(port: int) -> HTTPServer:
    server = HTTPServer(("0.0.0.0", port), _make_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ---------------------------------------------------------------------------
# Pytest hooks
# ---------------------------------------------------------------------------
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("itf-dashboard", "ITF Dashboard")
    group.addoption(
        "--itf-dashboard",
        action="store_true",
        default=False,
        help="Enable the ITF live dashboard web UI.",
    )
    group.addoption(
        "--itf-dashboard-port",
        type=int,
        default=8099,
        help="Port for the dashboard HTTP server (default: 8099).",
    )
    group.addoption(
        "--itf-dashboard-snapshot",
        type=str,
        default=None,
        help="Path for HTML snapshot on completion or crash.",
    )


_server: HTTPServer | None = None
_snapshot_path: str | None = None


@pytest.hookimpl
def pytest_itf_declare(registry, config):
    global _state, _snapshot_path  # noqa: PLW0603
    if not config.getoption("--itf-dashboard", default=False):
        return
    _state = DashboardState(session_start=time.time())
    _state.phases_completed.append("declare")
    _snapshot_path = config.getoption("--itf-dashboard-snapshot", default=None)


@pytest.hookimpl
def pytest_itf_init(dut: DUT, config: pytest.Config) -> None:
    if _state is None:
        return
    _populate_composition(dut)
    _state.phases_completed.append("init")


@pytest.hookimpl
def pytest_itf_provision(dut: DUT, config: pytest.Config) -> None:
    if _state is None:
        return
    _state.phases_completed.append("provision")


@pytest.hookimpl(trylast=True)
def pytest_itf_verify(dut: DUT, config: pytest.Config) -> None:
    if _state is None:
        return
    _state.phases_completed.append("verify")
    _state.verify_results.append({"status": "passed", "time": time.time()})
    _state.materialized = sorted(dut.materialized().keys())
    # Collect startup checks reported during this phase
    from score.itf.core.itf_plugin import get_startup_checks

    checks = get_startup_checks(config)
    _state.startup_checks = [
        {"name": c.name, "status": c.status, "duration": round(c.duration, 3), "detail": c.detail} for c in checks
    ]


@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    global _server  # noqa: PLW0603
    if _state is None:
        return
    port = session.config.getoption("--itf-dashboard-port", default=8099)
    _server = _start_server(port)
    logger.info("ITF Dashboard running at http://localhost:%d", port)


def pytest_collection_modifyitems(config, items):
    if _state is None:
        return
    _state.tests_collected = len(items)


def pytest_runtest_logreport(report):
    if _state is None:
        return
    if report.when == "setup":
        _state.current_test = report.nodeid
    elif report.when == "call":
        entry = {"nodeid": report.nodeid, "outcome": report.outcome, "duration": round(report.duration, 3)}
        _state.test_log.append(entry)
        if report.passed:
            _state.tests_passed += 1
        elif report.failed:
            _state.tests_failed += 1
        elif report.skipped:
            _state.tests_skipped += 1
    elif report.when == "teardown":
        _state.current_test = None


@pytest.hookimpl
def pytest_itf_teardown(dut: DUT, config: pytest.Config) -> None:
    pass  # Keep server up until pytest_unconfigure


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _state is None:
        return
    if exitstatus != 0:
        _state.crashed = True
    # On crash, always dump snapshot (even without --itf-dashboard-snapshot)
    if _state.crashed:
        _dump_snapshot(force_path="itf_dashboard_crash.html")


def pytest_unconfigure(config: pytest.Config) -> None:
    global _server  # noqa: PLW0603
    # Dump snapshot at end if path configured
    _dump_snapshot()
    if _server is not None:
        _server.shutdown()
        _server = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _populate_composition(dut: DUT) -> None:
    assembly = dut._assembly
    plan = assembly.plan
    registry = assembly.registry

    _state.contracts = sorted(plan.available | set(plan.unavailable))
    _state.spine = sorted(plan.spine)
    _state.unavailable = dict(plan.unavailable)
    _state.tier_map = dict(plan.tier_of)
    _state.disabled = sorted(dut.disabled)

    # Build edges and node types from registry
    edges = []
    node_types = {}
    for contract in _state.contracts:
        desc = registry.descriptor(contract)
        if desc is not None:
            node_types[contract] = "descriptor"
        else:
            prov = registry.provider(contract)
            if prov is not None:
                node_types[contract] = "provider"
                for dep in prov.requires:
                    edges.append({"source": dep, "target": contract})
    _state.edges = edges
    _state.node_types = node_types


_snapshot_dumped = False


def _dump_snapshot(force_path: str | None = None) -> None:
    global _snapshot_dumped  # noqa: PLW0603
    if _state is None or _snapshot_dumped:
        return
    path = force_path or _snapshot_path
    if path is None:
        return
    _snapshot_dumped = True
    html = _build_html(live=False)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    logger.info("ITF Dashboard snapshot saved to %s", out.resolve())


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------
def _build_html(live: bool) -> str:
    """Build the dashboard HTML.

    live=True: polls /api/state every second.
    live=False: embeds final state as static JSON — works offline.
    """
    if live:
        data_script = """\
let STATE = null;
async function loadState() {
  try { const r = await fetch('/api/state'); STATE = await r.json(); render(); } catch(e) {}
}
setInterval(loadState, 1000);
loadState();"""
    else:
        snapshot_json = json.dumps(_state.snapshot() if _state else {})
        data_script = f"let STATE = {snapshot_json};"

    return _HTML_TEMPLATE.replace("__DATA_SCRIPT__", data_script)


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ITF Dashboard</title>
<script src="https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js"></script>
<script src="https://unpkg.com/dagre@0.8.5/dist/dagre.min.js"></script>
<script src="https://unpkg.com/cytoscape-dagre@2.5.0/cytoscape-dagre.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; background: #1a1a2e; color: #eee; padding: 1rem; }
h1 { color: #0f9; margin-bottom: 0.5rem; font-size: 1.3rem; }
.header { display: flex; align-items: center; gap: 1rem; margin-bottom: 0.75rem; }
.header .crashed { color: #f44; font-weight: bold; font-size: 0.9rem; }
.header .ok { color: #0f9; font-size: 0.85rem; }
.layout { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr auto; gap: 0.75rem; height: calc(100vh - 4rem); }
.card { background: #16213e; border-radius: 8px; padding: 0.75rem; overflow: hidden; }
.card h2 { color: #0af; font-size: 0.8rem; text-transform: uppercase; margin-bottom: 0.4rem; }
.graph-card { grid-column: 1 / -1; position: relative; min-height: 300px; }
#cy { width: 100%; height: 100%; min-height: 280px; }
.metric { font-size: 1.6rem; font-weight: bold; }
.pass { color: #0f9; } .fail { color: #f44; } .skip { color: #fa0; }
.badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; margin: 1px; }
.badge-phase { background: #0f93; color: #0f9; }
#test-log { font-family: monospace; font-size: 0.72rem; max-height: 220px; overflow-y: auto; }
#test-log .passed { color: #0f9; } #test-log .failed { color: #f44; } #test-log .skipped { color: #fa0; }
.startup-row { display: flex; align-items: center; gap: 8px; padding: 3px 0; border-bottom: 1px solid #333; }
.startup-row .check-name { flex: 1; font-family: monospace; }
.startup-row .check-badge { padding: 1px 6px; border-radius: 3px; font-size: 0.7rem; font-weight: bold; }
.startup-row .check-badge.passed { background: #0f93; color: #0f9; }
.startup-row .check-badge.failed { background: #f443; color: #f44; }
.startup-row .check-badge.skipped { background: #fa03; color: #fa0; }
.startup-row .check-dur { font-size: 0.7rem; color: #888; }
.legend { position: absolute; top: 8px; right: 12px; font-size: 0.7rem; background: #1a1a2ecc; padding: 6px 10px; border-radius: 6px; display: flex; gap: 10px; }
.leg-spine { color: #0f9; } .leg-desc { color: #6cf; } .leg-prov { color: #fa0; }
.leg-mat { color: #fff; } .leg-dis { color: #666; }
</style>
</head>
<body>
<div class="header">
  <h1>ITF Dashboard</h1>
  <span id="status-line"></span>
</div>
<div class="layout">
  <div class="card graph-card">
    <h2>Resolution Graph</h2>
    <div class="legend">
      <span class="leg-spine">&#9632; spine</span>
      <span class="leg-desc">&#9632; descriptor</span>
      <span class="leg-prov">&#9632; provider</span>
      <span class="leg-mat">&#9634; materialized</span>
      <span class="leg-dis">&#9632; disabled</span>
    </div>
    <div id="cy"></div>
  </div>
  <div class="card">
    <h2>Lifecycle &amp; Progress</h2>
    <div id="phases" style="margin-bottom:0.5rem"></div>
    <div style="margin-bottom:0.5rem">
      <span class="metric pass" id="passed">0</span> /
      <span class="metric" id="total">0</span>
      <span class="fail" id="failed-ct"></span>
      <span class="skip" id="skipped-ct"></span>
    </div>
    <div style="font-size:0.8rem;margin-bottom:0.3rem">Current: <span id="current">-</span></div>
    <div style="font-size:0.8rem">Elapsed: <span id="elapsed">-</span></div>
  </div>
  <div class="card">
    <h2>Startup Checks</h2>
    <div id="startup-checks" style="font-size:0.85rem"></div>
  </div>
  <div class="card">
    <h2>Test Log</h2>
    <div id="test-log"></div>
  </div>
</div>
<script>
__DATA_SCRIPT__

let cy = null;
function initGraph(data) {
  const comp = data.composition || {};
  const contracts = comp.contracts || [];
  const spine = new Set(comp.spine || []);
  const mat = new Set(comp.materialized || []);
  const dis = new Set(comp.disabled || []);
  const types = comp.node_types || {};
  const tiers = comp.tier_map || {};

  const nodes = contracts.map(c => {
    const isSpine = spine.has(c);
    const isDesc = types[c] === 'descriptor';
    const isMat = mat.has(c);
    const isDis = dis.has(c);
    let bg = isDesc ? '#6cf' : '#fa0';
    if (isSpine) bg = '#0f9';
    if (isDis) bg = '#555';
    return {
      data: { id: c, label: c.split('/').slice(-1)[0], fullLabel: c, tier: tiers[c] || 0 },
      style: {
        'background-color': bg,
        'border-color': isMat ? '#fff' : '#444',
        'border-width': isMat ? 3 : 1,
        'opacity': isDis ? 0.4 : 1,
      }
    };
  });
  const edges = (comp.edges || []).map((e, i) => ({
    data: { id: 'e' + i, source: e.source, target: e.target }
  }));

  if (cy) cy.destroy();
  cy = cytoscape({
    container: document.getElementById('cy'),
    elements: [...nodes, ...edges],
    style: [
      { selector: 'node', style: {
        'label': 'data(label)', 'font-size': '9px', 'color': '#ddd',
        'text-valign': 'bottom', 'text-margin-y': 5,
        'width': 26, 'height': 26, 'shape': 'roundrectangle',
      }},
      { selector: 'edge', style: {
        'width': 2, 'line-color': '#4a4a6a',
        'target-arrow-color': '#6a6a8a', 'target-arrow-shape': 'triangle',
        'curve-style': 'bezier', 'arrow-scale': 0.7,
      }}
    ],
    layout: { name: 'dagre', rankDir: 'LR', nodeSep: 35, rankSep: 70, edgeSep: 15 },
    userZoomingEnabled: true, userPanningEnabled: true,
  });
  cy.on('mouseover', 'node', e => e.target.style('label', e.target.data('fullLabel')));
  cy.on('mouseout', 'node', e => e.target.style('label', e.target.data('label')));
}

let graphDone = false;
function render() {
  if (!STATE) return;
  const d = STATE;
  // Graph
  if (!graphDone && d.composition?.contracts?.length) {
    initGraph(d);
    graphDone = true;
  } else if (graphDone && cy) {
    const mat = new Set(d.composition?.materialized || []);
    const dis = new Set(d.composition?.disabled || []);
    cy.nodes().forEach(n => {
      n.style('border-color', mat.has(n.id()) ? '#fff' : '#444');
      n.style('border-width', mat.has(n.id()) ? 3 : 1);
      n.style('opacity', dis.has(n.id()) ? 0.4 : 1);
    });
  }
  // Status
  const sl = document.getElementById('status-line');
  if (d.crashed) sl.innerHTML = '<span class="crashed">SESSION CRASHED</span>';
  else sl.innerHTML = '<span class="ok">' + (d.lifecycle?.phases_completed?.join(' \\u2192 ') || '') + '</span>';
  // Phases
  document.getElementById('phases').innerHTML =
    (d.lifecycle?.phases_completed || []).map(p => '<span class="badge badge-phase">' + p + '</span>').join(' ');
  // Tests
  document.getElementById('passed').textContent = d.tests?.passed || 0;
  document.getElementById('total').textContent = d.tests?.collected || 0;
  document.getElementById('failed-ct').textContent = d.tests?.failed ? ' ' + d.tests.failed + ' failed' : '';
  document.getElementById('skipped-ct').textContent = d.tests?.skipped ? ' ' + d.tests.skipped + ' skipped' : '';
  document.getElementById('current').textContent = d.tests?.current || '-';
  document.getElementById('elapsed').textContent = (d.elapsed_seconds || 0) + 's';
  // Log
  const log = document.getElementById('test-log');
  log.innerHTML = (d.tests?.log || []).slice(-40).map(e =>
    '<div class="' + e.outcome + '">' + e.outcome.charAt(0).toUpperCase() + ' ' + e.nodeid + ' (' + e.duration + 's)</div>'
  ).join('');
  log.scrollTop = log.scrollHeight;
  // Startup checks
  const sc = document.getElementById('startup-checks');
  const checks = d.lifecycle?.startup_checks || [];
  if (checks.length === 0) {
    sc.innerHTML = '<span style="color:#666">No checks reported yet</span>';
  } else {
    sc.innerHTML = checks.map(c =>
      '<div class="startup-row">' +
        '<span class="check-badge ' + c.status + '">' + c.status.toUpperCase() + '</span>' +
        '<span class="check-name">' + c.name + '</span>' +
        '<span class="check-dur">' + c.duration + 's</span>' +
        (c.detail ? '<span style="font-size:0.7rem;color:#f88">' + c.detail + '</span>' : '') +
      '</div>'
    ).join('');
  }
}
if (STATE) render();
</script>
</body>
</html>
"""
