"""Bundle contract: candidate rejected on missing keys; exploratory ok with warnings."""

from crypto_analyzer.contracts.schema_versions import SEED_DERIVATION_SCHEMA_VERSION
from crypto_analyzer.contracts.validation_bundle_contract import (
    VALIDATION_BUNDLE_SCHEMA_VERSION,
    validate_bundle_for_level,
)


def _meta_provenance(**overrides):
    base = {
        "validation_bundle_schema_version": VALIDATION_BUNDLE_SCHEMA_VERSION,
        "dataset_id_v2": "abc",
        "dataset_hash_algo": "sqlite_logical_v2",
        "dataset_hash_mode": "STRICT",
        "run_key": "rk",
        "engine_version": "v1",
        "config_version": "c1",
        "seed_version": SEED_DERIVATION_SCHEMA_VERSION,
    }
    base.update(overrides)
    return base


def test_candidate_rejected_on_missing_run_key():
    meta = _meta_provenance()
    meta.pop("run_key", None)
    ok, reasons, _ = validate_bundle_for_level(meta, "candidate")
    assert ok is False
    assert any("run_key" in r for r in reasons)


def test_candidate_rejected_on_missing_dataset_id_v2():
    meta = _meta_provenance()
    meta.pop("dataset_id_v2", None)
    ok, reasons, _ = validate_bundle_for_level(meta, "candidate")
    assert ok is False
    assert any("dataset_id_v2" in r for r in reasons)


def test_candidate_rejected_when_dataset_hash_mode_not_strict():
    meta = _meta_provenance(dataset_hash_mode="FAST_DEV")
    ok, reasons, _ = validate_bundle_for_level(meta, "candidate")
    assert ok is False
    assert any("STRICT" in r for r in reasons)


def test_candidate_passes_when_all_provenance_present():
    meta = _meta_provenance()
    ok, reasons, _ = validate_bundle_for_level(meta, "candidate")
    assert ok is True
    assert len(reasons) == 0


def test_candidate_rejected_when_schema_version_missing_or_wrong():
    meta_ok = _meta_provenance()
    ok, _, _ = validate_bundle_for_level(meta_ok, "candidate")
    assert ok is True
    meta_missing = _meta_provenance()
    meta_missing.pop("validation_bundle_schema_version", None)
    ok, reasons, _ = validate_bundle_for_level(meta_missing, "candidate")
    assert ok is False
    assert any("validation_bundle_schema_version" in r for r in reasons)
    meta_wrong = _meta_provenance(validation_bundle_schema_version=99)
    ok, reasons, _ = validate_bundle_for_level(meta_wrong, "candidate")
    assert ok is False
    assert any("99" in r for r in reasons)


def test_exploratory_ok_with_warnings_when_keys_missing():
    meta = {"run_id": "123"}
    ok, reasons, warnings = validate_bundle_for_level(meta, "exploratory")
    assert ok is True
    assert len(reasons) == 0
    assert len(warnings) > 0
    assert any("missing" in w or "STRICT" in w for w in warnings)


def test_schema_version_constant():
    assert VALIDATION_BUNDLE_SCHEMA_VERSION == 1
