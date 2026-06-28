"""SFZ export: key assignment (chromatic + drum-map), region text, path form, caps.
Pure — no CLAP, no DB."""

from __future__ import annotations

import re

from forage import sfz


def _m(fid, cat=None):
    return {"forage_id": fid, "filename": f"{fid}.wav", "category": cat, "is_oneshot": True}


def test_chromatic_ascends_from_36():
    pairs = sfz.assign_keys([_m("a"), _m("b"), _m("c")], layout="chromatic")
    assert [k for _, k in pairs] == [36, 37, 38]


def test_chromatic_caps_at_127():
    pairs = sfz.assign_keys([_m(f"x{i}") for i in range(200)], layout="chromatic")
    assert len(pairs) == sfz.MAX_KEY - 36 + 1  # keys 36..127 inclusive = 92


def test_drum_map_places_kick_at_36_distinct_keys():
    pairs = sfz.assign_keys([_m("k1", "kick"), _m("k2", "kick"), _m("s1", "snare")], layout="drum-map")
    by_fid = {m["forage_id"]: k for m, k in pairs}
    assert by_fid["k1"] == 36
    assert by_fid["s1"] == 38
    assert by_fid["k2"] not in (36, 38)            # collision -> a different key
    assert len(set(by_fid.values())) == 3          # all distinct


def test_build_sfz_region_per_sound_and_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("FORAGE_HOME", str(tmp_path))
    text = sfz.build_sfz([_m("freesound-1"), _m("freesound-2")], layout="chromatic")
    assert text.count("<region>") == 2
    assert "key=36" in text and "key=37" in text
    assert "pitch_keycenter=36" in text and "loop_mode=one_shot" in text
    samples = re.findall(r"sample=(.+)", text)
    assert len(samples) == 2
    assert all("/" in s and "\\" not in s for s in samples)   # absolute, forward slashes
    assert all(s.endswith(".wav") for s in samples)


def test_write_sfz(tmp_path, monkeypatch):
    monkeypatch.setenv("FORAGE_HOME", str(tmp_path))
    out = sfz.write_sfz([_m("freesound-1")], name="my kit", layout="chromatic")
    assert out.exists() and out.suffix == ".sfz"
    assert out.name == "my kit.sfz"
    assert "<region>" in out.read_text(encoding="utf-8")
