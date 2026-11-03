"""Keep native Chroma SQLite on the same writable temp directory as Python."""
import os
import tempfile
from pathlib import Path


def prepare_chroma_temp_directory():
    explicit = os.environ.get("CHROMA_TEMP_DIR")
    if os.name != "nt" and not explicit:
        return None
    # Python probes candidates and can fall back when Windows TEMP is inaccessible;
    # native SQLite does not necessarily follow that fallback.
    directory = Path(explicit or tempfile.gettempdir()).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=directory):
        pass
    for name in ("TEMP", "TMP", "TMPDIR", "SQLITE_TMPDIR"):
        os.environ[name] = str(directory)
    tempfile.tempdir = str(directory)
    return str(directory)
