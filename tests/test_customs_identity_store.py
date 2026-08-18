"""CI-safe tests for the persisted Customs identity map (source of truth HeDE reads)."""

from __future__ import annotations

from gest.core.customs import identity_store
from gest.core.customs.identity import IdentityMap


def test_save_load_round_trip(tmp_path):
    path = str(tmp_path / "identity.json")
    m = IdentityMap()
    m.register(["Excel.exe"], "drydock-office-excel")
    identity_store.save(m, path)
    loaded = identity_store.load(path)
    assert loaded.resolve("excel.exe") == "drydock-office-excel"


def test_load_missing_is_empty(tmp_path):
    loaded = identity_store.load(str(tmp_path / "nope.json"))
    assert loaded.resolve("anything") is None


def test_load_corrupt_is_empty(tmp_path):
    path = tmp_path / "identity.json"
    path.write_text("{ not json", encoding="utf-8")
    assert identity_store.load(str(path)).resolve("x") is None


def test_register_entry_accumulates(tmp_path):
    path = str(tmp_path / "identity.json")
    identity_store.register_entry(["word.exe"], "drydock-office-word", path)
    identity_store.register_entry(["excel.exe"], "drydock-office-excel", path)
    loaded = identity_store.load(path)
    assert loaded.resolve("word.exe") == "drydock-office-word"
    assert loaded.resolve("excel.exe") == "drydock-office-excel"


def test_unregister_entry_removes_only_target(tmp_path):
    path = str(tmp_path / "identity.json")
    identity_store.register_entry(["word.exe"], "drydock-office-word", path)
    identity_store.register_entry(["excel.exe"], "drydock-office-excel", path)
    identity_store.unregister_entry("drydock-office-word", path)
    loaded = identity_store.load(path)
    assert loaded.resolve("word.exe") is None
    assert loaded.resolve("excel.exe") == "drydock-office-excel"


def test_default_path_under_shared_customs_dir():
    # both Drydock and Gangway write here — a shared Customs location, not either
    # subsystem's dir.
    assert identity_store.default_path().endswith("/hede/customs/identity.json")
