#!/usr/bin/env python
r"""
patch_pylsp_mypy.py - add stdin=subprocess.DEVNULL to every
subprocess.run / subprocess.Popen call in the installed pylsp_mypy
package that does not already set stdin.

Why (Windows): pylsp-mypy spawns mypy/dmypy with capture_output=True and
no stdin=, so the child inherits pylsp's stdin - the LSP pipe. While
pylsp's reader thread has a blocking read pending on that pipe, the child
hangs at startup and diagnostics only appear after the next client
message (edit/save).

Usage (use the SAME python that runs pylsp):
    python patch_pylsp_mypy.py                 # patch installed pylsp_mypy
    python patch_pylsp_mypy.py --dry-run       # show diffs, change nothing
    python patch_pylsp_mypy.py --restore       # undo from the .bak backups
    python patch_pylsp_mypy.py PATH            # patch a given copy

Notes:
  * AST-based: it understands the calls, it does not blindly regex them.
  * A .bak copy is written next to each patched file; --restore uses it.
  * Idempotent: calls that already pass stdin= are skipped.
  * Re-run it after every upgrade / reinstall of pylsp-mypy.
"""
import argparse
import ast
import difflib
import pathlib
import sys

CALL_NAMES = {"run", "Popen", "check_output", "check_call"}
KWARG = "stdin=subprocess.DEVNULL"


def find_package_dir(explicit):
    if explicit:
        p = pathlib.Path(explicit)
        if not p.exists():
            sys.exit(f"path does not exist: {p}")
        return p
    try:
        import pylsp_mypy  # noqa
    except ImportError:
        sys.exit(
            "pylsp_mypy is not importable by this python. "
            "Run this script with the python that runs pylsp, or pass the "
            "path to the pylsp_mypy package directory explicitly."
        )
    return pathlib.Path(pylsp_mypy.__file__).parent


def line_starts(text):
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def insertion_points(src, close_off):
    """Return [(offset, text), ...] to insert so that stdin=DEVNULL lands
    cleanly before the closing paren, with a correctly placed comma."""
    i = close_off - 1
    while i >= 0 and src[i] in " \t\r\n":
        i -= 1
    if i >= 0 and src[i] in ",(":
        return [(close_off, KWARG)]
    # need a comma: put it right after the last non-space char,
    # so a multiline call stays "encoding=...,\n    stdin=...DEVNULL)"
    return [(i + 1, ","), (close_off, KWARG)]


def patch_source(src, fname):
    """Return patched source, or None if nothing to do / not safe."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"  ! {fname}: cannot parse ({e}); skipped")
        return None
    if "import subprocess" not in src and "from subprocess import" not in src:
        return None  # nothing that calls subprocess.* in a sane way

    starts = line_starts(src)
    close_offs = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in CALL_NAMES):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
            continue
        if any(kw.arg == "stdin" for kw in node.keywords):
            continue  # already sets stdin -> idempotency
        end_off = starts[node.end_lineno - 1] + node.end_col_offset
        close_off = end_off - 1
        if close_off < 0 or src[close_off] != ")":
            continue
        close_offs.append(close_off)

    if not close_offs:
        return None

    edits = []
    for off in sorted(set(close_offs), reverse=True):
        for pos, text in insertion_points(src, off):
            edits.append((pos, text))
    # apply right-to-left so offsets stay valid
    for pos, text in sorted(edits, reverse=True):
        src = src[:pos] + text + src[pos:]

    try:
        ast.parse(src)
    except SyntaxError:
        print(f"  ! {fname}: patched source would not parse; file left unchanged")
        return None
    return src


def list_files(pkg):
    if pkg.is_dir():
        return sorted(pkg.glob("*.py"))
    return [pkg]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("path", nargs="?", help="pylsp_mypy package dir (default: the installed one)")
    ap.add_argument("--dry-run", action="store_true", help="only show diffs")
    ap.add_argument("--restore", action="store_true", help="restore from .bak files")
    ns = ap.parse_args()

    pkg = find_package_dir(ns.path)
    print(f"pylsp_mypy location: {pkg}")

    if ns.restore:
        n = 0
        for f in list_files(pkg):
            bak = f.with_suffix(f.suffix + ".bak")
            if bak.exists():
                f.write_bytes(bak.read_bytes())
                bak.unlink()
                print(f"  restored {f.name}")
                n += 1
        print(f"restored {n} file(s)")
        return

    total = 0
    for f in list_files(pkg):
        src = f.read_text(encoding="utf-8")
        patched = patch_source(src, f.name)
        if patched is None:
            continue
        diff = "\n".join(
            difflib.unified_diff(
                src.splitlines(), patched.splitlines(),
                fromfile=f"a/{f.name}", tofile=f"b/{f.name}", lineterm="",
            )
        )
        n_calls = patched.count(KWARG) - src.count(KWARG)
        print(f"\n{diff}\n")
        print(f"  {f.name}: {n_calls} subprocess call(s) patched")
        total += n_calls
        if not ns.dry_run:
            bak = f.with_suffix(f.suffix + ".bak")
            if not bak.exists():
                bak.write_text(src, encoding="utf-8")
            f.write_text(patched, encoding="utf-8")

    mode = " (dry run)" if ns.dry_run else ""
    print(f"\n{total} subprocess call(s) patched{mode}")
    if total and not ns.dry_run:
        print("Backups saved as .bak next to the files. Undo with: python patch_pylsp_mypy.py --restore")


if __name__ == "__main__":
    main()
