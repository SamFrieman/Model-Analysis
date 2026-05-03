"""
Called once at startup. Makes stdout UTF-8 safe on Windows so Rich
box-drawing characters survive the CP1252 terminal codec.
Also provides the single shared Rich Console instance.
"""
import sys
import os

def _patch_stdout():
    if sys.platform != "win32":
        return
    # Already patched?
    if getattr(sys.stdout, "_val_utf8_patched", False):
        return
    import io
    raw = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else None
    if raw is None:
        return
    wrapped = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", line_buffering=True)
    wrapped._val_utf8_patched = True
    sys.stdout = wrapped
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer if hasattr(sys.stderr, "buffer") else sys.stderr,
        encoding="utf-8", errors="replace", line_buffering=True,
    )

_patch_stdout()

# Build the single console instance AFTER patching stdout
try:
    from rich.console import Console
    # file=sys.stdout pins it to the already-patched stream; width=120 prevents wrapping
    CONSOLE = Console(file=sys.stdout, highlight=False, width=120)
    RICH = True
except ImportError:
    CONSOLE = None
    RICH = False
