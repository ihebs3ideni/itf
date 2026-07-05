from __future__ import annotations

from ctf_governance.catalog import build_catalog
from ctf_governance.collector import collect


def _codes(catalog):
    return {f.code for f in catalog.findings}


def test_healthy_ecosystem_has_no_errors(plugins):
    catalog = build_catalog(collect(plugins["good"]))
    assert catalog.ok()
    assert catalog.errors() == ()


def test_catalog_lists_contracts_and_requirers(plugins):
    catalog = build_catalog(collect(plugins["good"]))
    by_name = {c.contract: c for c in catalog.contracts}
    assert "score/doip/client" in by_name
    client = by_name["score/doip/client"]
    assert client.kind == "provider"
    transport = by_name["score/transport/doip"]
    assert transport.kind == "descriptor"
    # The descriptor is required by the doip client provider.
    assert any("doip_client" in r for r in transport.required_by)


def test_duplicate_provider_is_an_error(plugins):
    catalog = build_catalog(collect(plugins["dup_a"], plugins["dup_b"]))
    assert "duplicate-provider" in _codes(catalog)
    assert not catalog.ok()


def test_dangling_requirement_is_an_error(plugins):
    catalog = build_catalog(collect(plugins["dangling"]))
    assert "unresolved" in _codes(catalog)
    assert not catalog.ok()


def test_unique_point_collision_is_an_error(plugins):
    catalog = build_catalog(collect(plugins["collide_a"], plugins["collide_b"]))
    assert "unique-collision" in _codes(catalog)
    point = next(p for p in catalog.points if p.point == "ctf_provision")
    assert len(point.contributors) == 2


def test_namespace_violation_is_a_warning(plugins):
    catalog = build_catalog(collect(plugins["bad_namespace"]))
    assert "namespace" in _codes(catalog)
    # A pure namespace issue is a warning, not an error.
    assert catalog.ok()
    assert catalog.warnings()
