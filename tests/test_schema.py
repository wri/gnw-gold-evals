"""Every committed case file must conform to schema/case.schema.json."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema" / "case.schema.json").read_text())
CASE_FILES = sorted((ROOT / "cases").rglob("*.yaml"))


def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("path", CASE_FILES, ids=lambda p: p.stem)
def test_case_file_conforms(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(SCHEMA).iter_errors(data))
    assert not errors, "\n".join(e.message for e in errors)


def test_store_is_populated():
    assert CASE_FILES, "cases/ is empty — run tools/import_sheet.py"
