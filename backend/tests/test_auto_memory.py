"""Unit tests for the auto-memory extractor.

The regex layer must catch >=16 of 20 sample replies; the LLM fallback is
mocked so no real HTTP traffic occurs.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-real-and-not-short")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real-and-not-default")

import auto_memory  # noqa: E402
from chat.auto_memory import (  # noqa: E402
    ExtractedFact,
    _confidence_ok,
    _llm_fallback_layer,
    _parse_assistant,
    _regex_layer,
    _resolve_option_index,
    extract_facts,
)


# ── helpers ────────────────────────────────────────────────────────────────

OPSI_QUESTION = (
    "Mau pilih jurusan apa? [key=jurusan]\n"
    "[OPSI]\n"
    "1) Teknik Elektro\n"
    "2) Manajemen\n"
    "3) Hukum\n"
    "[/OPSI]"
)

OPSI_TOPIK_QUESTION = (
    "Topik apa di Teknik Elektro? [key=topik]\n"
    "[OPSI]\n"
    "1) Smart grid\n"
    "2) IoT energy monitoring\n"
    "3) Renewable inverter design\n"
    "[/OPSI]"
)

NO_KEY_QUESTION = (
    "Mau lanjut sekarang?\n"
    "[OPSI]\n"
    "1) Ya\n"
    "2) Nanti dulu\n"
    "[/OPSI]"
)


def _saved(facts):
    return [(f.key, f.value, f.source) for f in facts]


# ── parse_assistant ────────────────────────────────────────────────────────

def test_parse_assistant_extracts_key_marker():
    parsed = _parse_assistant(OPSI_QUESTION)
    assert parsed.expected_key == "jurusan"
    assert parsed.options[1] == "Teknik Elektro"
    assert parsed.options[2] == "Manajemen"
    assert parsed.options[3] == "Hukum"


def test_parse_assistant_no_key_no_opsi():
    parsed = _parse_assistant("plain text without markers")
    assert parsed.expected_key is None
    assert parsed.options == {}


def test_parse_assistant_opsi_without_key():
    parsed = _parse_assistant(NO_KEY_QUESTION)
    assert parsed.expected_key is None
    assert parsed.options[1] == "Ya"


def test_parse_assistant_handles_none():
    parsed = _parse_assistant(None)
    assert parsed.expected_key is None


# ── option index resolution ────────────────────────────────────────────────

def test_resolve_option_numeric():
    assert _resolve_option_index("1") == 1
    assert _resolve_option_index("  2 ") == 2
    assert _resolve_option_index("3") == 3


def test_resolve_option_pilih():
    assert _resolve_option_index("pilih 2") == 2
    assert _resolve_option_index("PILIH 1") == 1


def test_resolve_option_yang_ordinal():
    assert _resolve_option_index("yang pertama") == 1
    assert _resolve_option_index("yang kedua") == 2
    assert _resolve_option_index("yang ketiga") == 3
    assert _resolve_option_index("yang keempat") == 4


def test_resolve_option_none_for_free_text():
    assert _resolve_option_index("Teknik Elektro") is None
    assert _resolve_option_index("") is None


# ── confidence filter ─────────────────────────────────────────────────────

def test_confidence_filter_rejects_short():
    assert not _confidence_ok("ok", None)
    assert not _confidence_ok("a", None)
    assert not _confidence_ok("", None)


def test_confidence_filter_rejects_stopwords():
    for w in ["oke", "OK", "lanjut", "ya", "tidak", "yes", "no", "iya"]:
        assert not _confidence_ok(w, None), w


def test_confidence_filter_accepts_real_value():
    assert _confidence_ok("Teknik Elektro", None)
    assert _confidence_ok("smart grid IoT", None)


def test_confidence_filter_rejects_long_echo():
    long_echo = "a" * 100
    assert not _confidence_ok(long_echo, "preamble " + long_echo + " trailer")


# ── regex layer (the 20-sample target) ─────────────────────────────────────

def test_regex_layer_numeric_options():
    parsed = _parse_assistant(OPSI_QUESTION)
    facts = _regex_layer("1", parsed)
    assert _saved(facts) == [("jurusan", "Teknik Elektro", "regex")]

    facts = _regex_layer("2", parsed)
    assert _saved(facts) == [("jurusan", "Manajemen", "regex")]

    facts = _regex_layer("3", parsed)
    assert _saved(facts) == [("jurusan", "Hukum", "regex")]


def test_regex_layer_pilih_phrasal():
    parsed = _parse_assistant(OPSI_TOPIK_QUESTION)
    facts = _regex_layer("pilih 2", parsed)
    assert _saved(facts) == [("topik", "IoT energy monitoring", "regex")]


def test_regex_layer_yang_ordinal():
    parsed = _parse_assistant(OPSI_TOPIK_QUESTION)
    facts = _regex_layer("yang ketiga", parsed)
    assert _saved(facts) == [("topik", "Renewable inverter design", "regex")]

    facts = _regex_layer("yang pertama", parsed)
    assert _saved(facts) == [("topik", "Smart grid", "regex")]


def test_regex_layer_explicit_ingat_with_key():
    parsed = _parse_assistant(
        "Target jurnal mana? [key=target_jurnal]\n[OPSI]\n1) IEEE\n2) Elsevier\n[/OPSI]"
    )
    facts = _regex_layer("ingat: target jurnal IEEE Access", parsed)
    assert facts and facts[0].key == "target_jurnal"
    assert "IEEE Access" in facts[0].value


def test_regex_layer_explicit_simpan():
    parsed = _parse_assistant("anything")
    facts = _regex_layer(
        "simpan: key=tone value=formal IEEE-style", parsed
    )
    assert facts == [
        ExtractedFact(key="tone", value="formal IEEE-style", source="regex")
    ]


def test_regex_layer_plain_text_with_expected_key():
    parsed = _parse_assistant(OPSI_QUESTION)
    facts = _regex_layer("Teknik Elektro", parsed)
    assert _saved(facts) == [("jurusan", "Teknik Elektro", "regex")]


def test_regex_layer_plain_text_topik():
    parsed = _parse_assistant(OPSI_TOPIK_QUESTION)
    facts = _regex_layer(
        "Optimalisasi inverter PV grid-tie 5 kW dengan MPPT P&O",
        parsed,
    )
    assert facts and facts[0].key == "topik"
    assert "Optimalisasi" in facts[0].value


def test_regex_layer_stopword_oke_rejected():
    parsed = _parse_assistant(OPSI_QUESTION)
    facts = _regex_layer("oke", parsed)
    assert facts == []


def test_regex_layer_stopword_lanjut_rejected():
    parsed = _parse_assistant(OPSI_QUESTION)
    facts = _regex_layer("lanjut", parsed)
    assert facts == []


def test_regex_layer_empty_rejected():
    parsed = _parse_assistant(OPSI_QUESTION)
    assert _regex_layer("", parsed) == []
    assert _regex_layer("   ", parsed) == []


def test_regex_layer_no_key_no_opsi_returns_empty():
    parsed = _parse_assistant(None)
    assert _regex_layer("Teknik Elektro", parsed) == []


def test_regex_layer_numeric_without_options_falls_through():
    parsed = _parse_assistant("Plain question with no [OPSI] but [key=topik]")
    # A bare "1" with no options has no useful mapping; should not save.
    facts = _regex_layer("1", parsed)
    assert facts == []


def test_regex_layer_out_of_range_option():
    parsed = _parse_assistant(OPSI_QUESTION)
    facts = _regex_layer("9", parsed)
    assert facts == []


def test_regex_layer_ingat_without_expected_key_uses_catatan():
    parsed = _parse_assistant("free chat with no key")
    facts = _regex_layer("ingat: paper deadline 1 Juli", parsed)
    assert facts and facts[0].key == "catatan"
    assert "1 Juli" in facts[0].value


# 20-sample threshold: count regex hits.
SAMPLES = [
    (OPSI_QUESTION, "1", True),
    (OPSI_QUESTION, "2", True),
    (OPSI_QUESTION, "3", True),
    (OPSI_TOPIK_QUESTION, "pilih 2", True),
    (OPSI_TOPIK_QUESTION, "yang ketiga", True),
    (OPSI_TOPIK_QUESTION, "yang pertama", True),
    (OPSI_QUESTION, "Teknik Elektro", True),
    (OPSI_QUESTION, "Manajemen Operasional", True),
    (OPSI_TOPIK_QUESTION, "Optimalisasi inverter PV grid-tie", True),
    (OPSI_TOPIK_QUESTION, "Energy harvesting wireless sensor", True),
    (
        "Target jurnal? [key=target_jurnal]\n[OPSI]\n1) IEEE\n2) Elsevier\n[/OPSI]",
        "ingat: target jurnal IEEE Access",
        True,
    ),
    ("plain question", "simpan: key=tone value=formal IEEE-style", True),
    (OPSI_QUESTION, "pilih 1", True),
    (OPSI_QUESTION, "yang kedua", True),
    (OPSI_TOPIK_QUESTION, "3", True),
    (OPSI_TOPIK_QUESTION, "Renewable inverter design", True),
    (OPSI_QUESTION, "oke", False),
    (OPSI_QUESTION, "lanjut", False),
    (OPSI_QUESTION, "", False),
    (OPSI_QUESTION, "   ", False),
]


def test_regex_layer_20_sample_threshold():
    hits = 0
    for last, reply, expect_hit in SAMPLES:
        parsed = _parse_assistant(last)
        facts = _regex_layer(reply, parsed)
        got = bool(facts)
        if got == expect_hit and got:
            hits += 1
    assert hits >= 16, f"regex hits={hits} < 16"


# ── LLM fallback (mocked) ─────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_llm_fallback_returns_none_without_env(monkeypatch):
    monkeypatch.delenv("AIOTOMASI_API", raising=False)
    monkeypatch.delenv("AIOTOMASI_APIKEY", raising=False)
    out = _llm_fallback_layer("jurusan", "Saya kuliah di kampus negeri di Jawa Tengah")
    assert out is None


def test_llm_fallback_parses_json(monkeypatch):
    monkeypatch.setenv("AIOTOMASI_API", "https://example.test")
    monkeypatch.setenv("AIOTOMASI_APIKEY", "k")
    payload = {
        "choices": [{"message": {"content": '{"value": "Teknik Elektro"}'}}]
    }
    with patch("auto_memory.requests.post", return_value=_FakeResp(200, payload)):
        out = _llm_fallback_layer("jurusan", "Saya kuliah Teknik Elektro di UGM")
    assert out is not None
    assert out.key == "jurusan"
    assert out.value == "Teknik Elektro"
    assert out.source == "llm"


def test_llm_fallback_handles_null(monkeypatch):
    monkeypatch.setenv("AIOTOMASI_API", "https://example.test")
    monkeypatch.setenv("AIOTOMASI_APIKEY", "k")
    payload = {"choices": [{"message": {"content": "null"}}]}
    with patch("auto_memory.requests.post", return_value=_FakeResp(200, payload)):
        out = _llm_fallback_layer("jurusan", "saya tidak yakin sebenarnya")
    assert out is None


def test_llm_fallback_handles_code_fence(monkeypatch):
    monkeypatch.setenv("AIOTOMASI_API", "https://example.test")
    monkeypatch.setenv("AIOTOMASI_APIKEY", "k")
    payload = {
        "choices": [
            {
                "message": {
                    "content": '```json\n{"value": "Manajemen Operasional"}\n```'
                }
            }
        ]
    }
    with patch("auto_memory.requests.post", return_value=_FakeResp(200, payload)):
        out = _llm_fallback_layer(
            "jurusan", "Sebenarnya jurusan saya manajemen operasional di FEB"
        )
    assert out is not None
    assert out.value == "Manajemen Operasional"


def test_llm_fallback_swallows_exceptions(monkeypatch):
    monkeypatch.setenv("AIOTOMASI_API", "https://example.test")
    monkeypatch.setenv("AIOTOMASI_APIKEY", "k")

    def boom(*a, **k):
        raise TimeoutError("upstream slow")

    with patch("auto_memory.requests.post", side_effect=boom):
        out = _llm_fallback_layer("jurusan", "panjang sekali kalimat ini")
    assert out is None


def test_llm_fallback_short_input_skipped(monkeypatch):
    monkeypatch.setenv("AIOTOMASI_API", "https://example.test")
    monkeypatch.setenv("AIOTOMASI_APIKEY", "k")
    out = _llm_fallback_layer("jurusan", "halo")
    assert out is None


# ── extract_facts (top-level) ─────────────────────────────────────────────

def test_extract_facts_persists_via_save_memory(monkeypatch):
    saved = []

    def fake_save(paper_id, user_id, key, value, kind="fact"):
        saved.append((paper_id, user_id, key, value, kind))
        return f"Saved {key}."

    monkeypatch.setattr(auto_memory, "_save_memory", fake_save)
    out = extract_facts(
        paper_id="p1",
        user_id=42,
        conv=None,
        user_msg="1",
        last_assistant_msg=OPSI_QUESTION,
    )
    assert len(out) == 1
    assert out[0].key == "jurusan"
    assert out[0].value == "Teknik Elektro"
    assert saved == [("p1", 42, "jurusan", "Teknik Elektro", "fact")]


def test_extract_facts_no_paper_id_returns_empty(monkeypatch):
    monkeypatch.setattr(auto_memory, "_save_memory", lambda *a, **k: None)
    out = extract_facts(
        paper_id="",
        user_id=1,
        conv=None,
        user_msg="1",
        last_assistant_msg=OPSI_QUESTION,
    )
    assert out == []


def test_extract_facts_empty_user_msg(monkeypatch):
    saved = []
    monkeypatch.setattr(auto_memory, "_save_memory", lambda *a, **k: saved.append(a))
    out = extract_facts(
        paper_id="p1",
        user_id=1,
        conv=None,
        user_msg="   ",
        last_assistant_msg=OPSI_QUESTION,
    )
    assert out == [] and saved == []


def test_extract_facts_falls_back_to_llm(monkeypatch):
    saved = []
    monkeypatch.setattr(
        auto_memory,
        "_save_memory",
        lambda paper_id, user_id, key, value, kind="fact": saved.append((key, value, kind)),
    )

    def fake_llm(expected_key, user_msg):
        return ExtractedFact(
            key=expected_key, value="Teknik Industri", source="llm"
        )

    monkeypatch.setattr(auto_memory, "_llm_fallback_layer", fake_llm)
    # Pose a question whose [OPSI] options don't match the user reply, and a
    # reply that's NOT a stopword and longer than 5 chars — but make the regex
    # layer return [] by removing [key=...] so we can isolate the LLM path.
    last = (
        "Sebenarnya, jurusan apa? Bisa cerita?\n"
        "[OPSI]\n1) Teknik\n2) Manajemen\n[/OPSI]"
    )
    # No expected_key -> regex returns [] -> no LLM call (LLM needs key).
    out = extract_facts("p1", 1, None, "Saya di FT, ambil Teknik Industri", last)
    assert out == [] and saved == []

    # Now with expected_key, regex won't match (free-text >5 chars triggers regex
    # actually). Force regex to fail by making message a stopword-ish phrase but
    # long enough for LLM. We'll simulate by directly calling the LLM path.
    last_with_key = (
        "Jurusan apa? [key=jurusan]\n[OPSI]\n1) Teknik\n2) Manajemen\n[/OPSI]"
    )
    saved.clear()
    # Force regex to skip by patching _regex_layer.
    monkeypatch.setattr(auto_memory, "_regex_layer", lambda *a, **k: [])
    out = extract_facts(
        "p1", 1, None,
        "Sulit dijelaskan singkat, intinya saya kuliah Teknik Industri",
        last_with_key,
    )
    assert len(out) == 1
    assert out[0].source == "llm"
    assert saved == [("jurusan", "Teknik Industri", "fact")]


def test_extract_facts_swallows_internal_errors(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(auto_memory, "_parse_assistant", boom)
    out = extract_facts(
        paper_id="p1",
        user_id=1,
        conv=None,
        user_msg="1",
        last_assistant_msg=OPSI_QUESTION,
    )
    assert out == []
