"""Sidecar validation + load tests (pure — no CLAP, no network, no DB)."""

from __future__ import annotations

import json

from forage import library


def _valid_meta() -> dict:
    return dict(
        forage_id="freesound-1", source="freesound", file_hash="abc123",
        filename="freesound-1.wav", title="punchy kick", license_name="CC0",
        requires_attribution=False, non_commercial=False, share_alike=False,
        no_derivatives=False, tags=["kick", "drum"],
    )


def test_valid_sidecar_has_no_problems():
    assert library.validate_sidecar(_valid_meta()) == []


def test_missing_required_field_is_flagged():
    m = _valid_meta()
    del m["file_hash"]
    problems = library.validate_sidecar(m)
    assert any("file_hash" in p for p in problems)


def test_non_bool_obligation_is_flagged():
    m = _valid_meta()
    m["non_commercial"] = "yes"  # not a bool
    assert any("non_commercial" in p for p in library.validate_sidecar(m))


def test_empty_title_is_flagged():
    m = _valid_meta()
    m["title"] = "   "
    assert any("title" in p for p in library.validate_sidecar(m))


def test_non_list_tags_is_flagged():
    m = _valid_meta()
    m["tags"] = "kick"
    assert any("tags" in p for p in library.validate_sidecar(m))


def test_not_a_dict():
    assert library.validate_sidecar([1, 2, 3]) == ["not a JSON object"]


def test_load_sidecar_valid(tmp_path):
    p = tmp_path / "freesound-1.json"
    p.write_text(json.dumps(_valid_meta()), encoding="utf-8")
    meta, problems = library.load_sidecar(p)
    assert problems == [] and meta["forage_id"] == "freesound-1"


def test_load_sidecar_malformed_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not valid json", encoding="utf-8")
    meta, problems = library.load_sidecar(p)
    assert meta is None and problems


def test_load_sidecar_invalid_returns_meta_and_problems(tmp_path):
    """A parsed-but-invalid sidecar is still returned so callers can inspect it."""
    bad = _valid_meta()
    del bad["filename"]
    p = tmp_path / "freesound-1.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    meta, problems = library.load_sidecar(p)
    assert meta is not None and meta["source"] == "freesound"
    assert any("filename" in pr for pr in problems)
