import os
import tempfile
from pathlib import Path
import pytest
from framework.vector_store.runtime_temp import prepare_chroma_temp_directory


def test_explicit_temp_is_writable_and_shared_with_native_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_TEMP_DIR", str(tmp_path / "native-temp"))
    for key in ("TEMP", "TMP", "TMPDIR", "SQLITE_TMPDIR"):
        monkeypatch.setenv(key, "invalid-original-temp")
    monkeypatch.setattr(tempfile, "tempdir", None)
    actual = prepare_chroma_temp_directory()
    assert Path(actual).is_dir()
    assert all(os.environ[key] == actual for key in ("TEMP", "TMP", "TMPDIR", "SQLITE_TMPDIR"))
    with tempfile.TemporaryFile(dir=actual) as stream:
        stream.write(b"native temp probe")


def test_invalid_explicit_temp_does_not_silently_fall_back(tmp_path, monkeypatch):
    target = tmp_path / "file"
    target.write_text("not a directory")
    monkeypatch.setenv("CHROMA_TEMP_DIR", str(target))
    with pytest.raises(OSError):
        prepare_chroma_temp_directory()
