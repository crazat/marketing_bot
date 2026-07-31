"""Regression tests for scoped, evidence-only Cafe enrichment."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_script_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "enrich_cafe_bodies.py"
    spec = spec_from_file_location("enrich_cafe_bodies", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scoped_cafe_enrichment_query_binds_source_lineage():
    script = _load_script_module()

    query = script.build_target_query(130)

    assert "COALESCE(source_scan_run_id, 0) = ?" in query
    assert query.count("?") == 4
    assert "comment_status = 'pending'" in query


def test_unscoped_cafe_enrichment_query_preserves_existing_selection():
    script = _load_script_module()

    query = script.build_target_query(None)

    assert "source_scan_run_id" not in query
    assert query.count("?") == 3
