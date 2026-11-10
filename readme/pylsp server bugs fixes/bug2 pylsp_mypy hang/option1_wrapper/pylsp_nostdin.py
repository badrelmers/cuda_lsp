#!/usr/bin/env python
r"""
pylsp_nostdin.py - launcher for pylsp that stops child processes from
inheriting pylsp's stdin (the LSP stdio pipe).

Why this exists (Windows):
  pylsp-mypy runs mypy with:

      subprocess.run([...], capture_output=True, ...)   # no stdin=

  With no stdin=, mypy.exe *inherits* pylsp's own stdin - the anonymous
  pipe that carries the LSP protocol from the editor. While pylsp's
  reader thread sits in a blocking read on that pipe (i.e. whenever the
  server is idle), the child process hangs at startup on Windows, so
  diagnostics only show up when the next client message (an edit or a
  save) completes the pending read and releases the pipe.

  The same pattern (spawn without an explicit stdin) exists in other
  plugins too (pylint, flake8), so this protects them as well.

What this launcher does:
  It wraps subprocess.Popen.__init__ so that any child spawned without an
  explicit stdin gets stdin=DEVNULL (NUL on Windows, /dev/null elsewhere).
  Children that ask for a pipe still get one (ruff spawns with
  stdin=PIPE and is not affected), and subprocess.run(..., input=...)
  still works (run() passes stdin=PIPE itself). Nothing in a pylsp setup
  ever legitimately reads the LSP stream, so nothing is lost.

Usage:
  Point your client's server command at this file instead of "pylsp".
  All pylsp command line flags pass through unchanged, e.g.:

      python C:\path\to\pylsp_nostdin.py
      python C:\path\to\pylsp_nostdin.py --tcp --host 127.0.0.1 --port 2087

  Keep this file OUTSIDE site-packages so package upgrades don't remove it.
"""

import subprocess
import sys

_ORIG_INIT = subprocess.Popen.__init__


def _stdin_devnull_init(self, *args, **kwargs):
    # Popen.__init__(self, args, bufsize, executable, stdin, ...):
    # stdin is the 4th positional parameter. Only patch when stdin was
    # not specified at all (absent, or explicitly None = "inherit").
    if kwargs.get("stdin") is None and len(args) < 4:
        kwargs["stdin"] = subprocess.DEVNULL
    _ORIG_INIT(self, *args, **kwargs)


subprocess.Popen.__init__ = _stdin_devnull_init

from pylsp.__main__ import main  # noqa: E402  (must be imported AFTER the patch)

sys.exit(main())
