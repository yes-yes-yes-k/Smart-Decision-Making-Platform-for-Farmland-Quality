"""Compatibility wrapper for the upstream caj2pdf command-line converter.

The upstream project invokes the external ``mutool clean`` command and uses
fixed working-directory temporary names.  This wrapper keeps its public CLI,
uses PyMuPDF for the repair step, and isolates each conversion in a temporary
directory so concurrent uploads cannot overwrite one another.
"""
from __future__ import annotations

import argparse
import gc
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = Path(
    os.environ.get("CAJ2PDF_VENDOR_DIR")
    or PROJECT_ROOT / ".tools" / "caj2pdf"
).resolve()


def _load_parser():
    if not (VENDOR_ROOT / "cajparser.py").is_file():
        raise RuntimeError(
            "未找到 caj2pdf 源码；请设置 CAJ2PDF_VENDOR_DIR 或将官方仓库放到 "
            f"{VENDOR_ROOT}"
        )
    sys.path.insert(0, str(VENDOR_ROOT))
    import cajparser  # type: ignore

    original_check_output = cajparser.check_output

    def check_output(command, *args, **kwargs):
        if len(command) == 4 and command[:2] == ["mutool", "clean"]:
            import fitz

            source = Path(command[2]).resolve()
            destination = Path(command[3]).resolve()
            with fitz.open(source) as document:
                document.save(
                    destination,
                    garbage=4,
                    clean=True,
                    deflate=True,
                )
            return b""
        return original_check_output(command, *args, **kwargs)

    cajparser.check_output = check_output

    # Some otherwise readable CAJ files contain malformed bookmark records
    # (for example, an empty page-number field).  Upstream parses the table of
    # contents only after it has already reconstructed the document body.  A
    # bad optional outline must therefore not discard usable pages.
    original_get_toc = cajparser.CAJParser.get_toc

    def get_toc_or_empty(document, *args, **kwargs):
        try:
            return original_get_toc(document, *args, **kwargs)
        except Exception as exc:
            print(
                f"[caj2pdf-adapter] 跳过损坏的目录书签: {exc}",
                file=sys.stderr,
            )
            return []

    cajparser.CAJParser.get_toc = get_toc_or_empty
    return cajparser.CAJParser


def _convert(source: Path, output: Path) -> None:
    parser_type = _load_parser()
    source = source.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(
        prefix="caj2pdf_", ignore_cleanup_errors=True,
    ) as temp_dir:
        work_dir = Path(temp_dir)
        vendor_lib = VENDOR_ROOT / "lib"
        if vendor_lib.is_dir():
            shutil.copytree(vendor_lib, work_dir / "lib")
        document = None
        try:
            os.chdir(work_dir)
            document = parser_type(str(source))
            document.convert(str(output))
        finally:
            if document is not None:
                del document
            gc.collect()
            _release_decoder_libraries()
            os.chdir(previous)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("CAJ 转换器没有生成有效输出")


def _release_decoder_libraries() -> None:
    """Release Windows decoder DLLs before deleting the isolated work dir."""
    if os.name != "nt":
        return
    import _ctypes

    for module_name, attribute in (
        ("jbigdec", "libjbigdec"),
        ("jbig2dec", "libjbig2codec"),
    ):
        module = sys.modules.get(module_name)
        library = getattr(module, attribute, None) if module else None
        handle = getattr(library, "_handle", None)
        if handle:
            _ctypes.FreeLibrary(handle)
            setattr(module, attribute, None)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    convert = subparsers.add_parser("convert")
    convert.add_argument("input")
    convert.add_argument("-o", "--output", required=True)
    show = subparsers.add_parser("show")
    show.add_argument("input")
    args = parser.parse_args(argv)

    parser_type = _load_parser()
    if args.command == "show":
        document = parser_type(str(Path(args.input).resolve()))
        print(f"Type: {document.format}")
        return 0
    _convert(Path(args.input), Path(args.output))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
