"""Expectations files for the synthetic documents load and point at real files (M9b-6)."""

from pathlib import Path

import pytest

from testforge.validation.schema import load_expectations

EXPECTATIONS = sorted(Path("fixtures/expectations").glob("*.yml"))


@pytest.mark.parametrize("path", EXPECTATIONS, ids=lambda p: p.stem)
def test_expectations_file_loads(path):
    expectations = load_expectations(path)

    assert expectations.document_summary
    if expectations.fixture_file is not None:
        assert Path(expectations.fixture_file).is_file()


def test_every_synthetic_document_has_expectations():
    covered = {
        Path(load_expectations(path).fixture_file).name
        for path in EXPECTATIONS
        if load_expectations(path).fixture_file is not None
    }
    documents = {path.name for path in Path("fixtures/documents").glob("*.pdf")}

    assert documents == covered
