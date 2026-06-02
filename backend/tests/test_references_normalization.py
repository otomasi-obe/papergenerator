"""Regression tests for the DOCX references-shape bug.

The frontend may ship `references` as one of:
  - omitted entirely
  - empty list `[]`
  - list of dicts `[{"id": "1", "text": "..."}]`
  - list of strings `["[1] Foo et al."]`
  - dict `{"content": [...], "title": "..."}`  (legacy)

All five must be handled without raising AttributeError on `.get`.

NOTE: `templateAnalyse` package is generated lazily by template builders and
isn't always in the working tree. Skip the whole module if either package is
missing rather than failing CI on an environment-specific import.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

template = pytest.importorskip("template.IEEEgen", reason="template package not present")
templateAnalyse_ieee = pytest.importorskip(
    "templateAnalyse.IEEEgen", reason="templateAnalyse not present in this checkout"
)
templateAnalyse_jel = pytest.importorskip(
    "templateAnalyse.JELgen", reason="templateAnalyse not present in this checkout"
)
templateAnalyse_icet = pytest.importorskip(
    "templateAnalyse.ICETgen", reason="templateAnalyse not present in this checkout"
)

ieee_norm = template._normalize_references_field
ieee_an_norm = templateAnalyse_ieee._normalize_references_field
jel_norm = templateAnalyse_jel._normalize_references_field
icet_norm = templateAnalyse_icet._normalize_references_field

NORMALIZERS = [ieee_norm, ieee_an_norm, jel_norm, icet_norm]


@pytest.mark.parametrize("normalize", NORMALIZERS)
def test_none_returns_none(normalize):
    assert normalize(None) is None


@pytest.mark.parametrize("normalize", NORMALIZERS)
def test_empty_list_passes_through(normalize):
    """The original bug: list passed where dict.get was assumed."""
    assert normalize([]) == []


@pytest.mark.parametrize("normalize", NORMALIZERS)
def test_list_of_dicts(normalize):
    refs = [{"id": "1", "text": "Foo et al."}]
    assert normalize(refs) == refs


@pytest.mark.parametrize("normalize", NORMALIZERS)
def test_list_of_strings(normalize):
    refs = ["[1] Foo et al."]
    assert normalize(refs) == refs


@pytest.mark.parametrize("normalize", NORMALIZERS)
def test_dict_with_content_list(normalize):
    refs = {"content": [{"id": "1", "text": "Foo"}], "title": "REFERENCES"}
    assert normalize(refs) == [{"id": "1", "text": "Foo"}]


@pytest.mark.parametrize("normalize", NORMALIZERS)
def test_dict_with_no_content(normalize):
    assert normalize({}) == []


@pytest.mark.parametrize("normalize", NORMALIZERS)
def test_dict_with_non_list_content(normalize):
    """Defensive: content key exists but not a list."""
    assert normalize({"content": "not a list"}) == []


@pytest.mark.parametrize("normalize", NORMALIZERS)
def test_unexpected_type_returns_none(normalize):
    assert normalize(42) is None
    assert normalize("string") is None
