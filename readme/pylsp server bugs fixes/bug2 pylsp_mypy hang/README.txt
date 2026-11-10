CUDATEXT + PYLSP + PYLSP-MYPY FIX
"mypy diagnostics only appear after I edit or save" (Windows, stdio transport)
================================================================================

THE BUG
pylsp-mypy runs mypy.exe with subprocess.run(..., capture_output=True) and no
stdin=, so mypy INHERITS pylsp's stdin - the pipe that carries the LSP
protocol from CudaText. While pylsp's reader thread sits in a blocking read
on that pipe (i.e. whenever the server is idle), the child process hangs at
startup on Windows. It only finishes when your next message (edit / save)
completes the pending read. That is why every mypy diagnostic lags exactly
one event behind, and why live_mode=false, dmypy=true, and waiting 3 minutes
changed nothing - all of them still spawn a child with inherited stdin.
(ruff was never affected because it spawns its process with stdin=PIPE.)

THE FIX
Children must not inherit pylsp's stdin: pass stdin=subprocess.DEVNULL (the
NUL device) to every mypy/dmypy subprocess call. mypy never reads stdin and
dmypy detaches from it when it daemonizes, so nothing is lost.

Pick ONE of the options below.

--------------------------------------------------------------------------------
OPTION 1 - wrapper launcher  (RECOMMENDED: no package files touched)
--------------------------------------------------------------------------------
1. Copy  option1_wrapper\pylsp_nostdin.py  to a permanent place that survives
   updates, e.g.   F:\_bin\_tools\pylsp_nostdin.py
   (do NOT put it inside site-packages - upgrades would delete it)
2. In your cuda_lsp server config change the pylsp server command from
   "pylsp" to:
       <python.exe path> F:\_bin\_tools\pylsp_nostdin.py
   Use the SAME python.exe that runs pylsp. All pylsp flags pass through,
   including --tcp.
3. Restart the server. Done.

It wraps subprocess.Popen so any child spawned without an explicit stdin gets
DEVNULL. This also protects other plugins that spawn children without stdin=
(pylint, flake8) if you ever enable them.

--------------------------------------------------------------------------------
OPTION 2 - auto-patch script (patches the INSTALLED pylsp_mypy in place)
--------------------------------------------------------------------------------
Run with the SAME python that runs pylsp:

    python option2_patch_script\patch_pylsp_mypy.py --dry-run    (preview)
    python option2_patch_script\patch_pylsp_mypy.py              (patch)
    python option2_patch_script\patch_pylsp_mypy.py --restore    (undo)

- AST-based (understands the calls, no blind regex), idempotent, writes .bak
  backups next to each file.
- Works for ANY pylsp-mypy version: calls in backend.py AND/OR plugin.py.
- RE-RUN it after every upgrade / reinstall of pylsp-mypy.
- To find the installed location:
    python -c "import pylsp_mypy, os; print(os.path.dirname(pylsp_mypy.__file__))"

--------------------------------------------------------------------------------
OPTION 3 - copy-paste the patched file  (pylsp-mypy 0.8.2 ONLY)
--------------------------------------------------------------------------------
ONLY if  pip show pylsp-mypy  reports 0.8.2 (otherwise use Option 2):

1. Find the installed package:
    python -c "import pylsp_mypy, os; print(os.path.dirname(pylsp_mypy.__file__))"
2. Copy  option3_copy_paste_pylsp_mypy_0.8.2\pylsp_mypy\backend.py
   over   <that folder>\backend.py
3. Restart the server.

--------------------------------------------------------------------------------
OPTION 4 - git patches (fork / upstream style)
--------------------------------------------------------------------------------
From the site-packages directory (the one CONTAINING the pylsp_mypy folder),
in git bash:

    cd <site-packages>
    git apply <path to>\git_patches\pylsp-mypy-0.8.2-backend.py-stdin-devnull.patch
  or
    patch -p1 < <path to>\git_patches\pylsp-mypy-0.8.2-backend.py-stdin-devnull.patch

Files:
  pylsp-mypy-0.8.2-backend.py-stdin-devnull.patch
      -> released 0.8.2: pylsp_mypy/backend.py, 7 subprocess calls
  pylsp-mypy-master-plugin.py-stdin-devnull.patch
      -> current master: pylsp_mypy/plugin.py, 6 subprocess calls
         (master merged the backends back into plugin.py)

Both are git format-patch files: "git am" also works, and the commit message
documents the bug - handy for a PR to https://github.com/python-lsp/pylsp-mypy

--------------------------------------------------------------------------------
NOTES
--------------------------------------------------------------------------------
- Confirmed against the code: with mypy.exe on PATH, pylsp-mypy picks
  MypyCommandBackend (subprocess). live_mode / dmypy only change the args,
  not how the child is spawned - which is why neither fixed it.
- TCP transport also sidesteps the bug (pylsp --tcp --host 127.0.0.1
  --port 2087; stdin is then no longer the LSP pipe) but needs a fixed
  free port.
- Everything here was tested on pylsp 1.15 / pylsp-mypy 0.8.2 / mypy 2.4
  over real stdio LSP sessions; both patches were verified to apply cleanly
  onto pristine originals and to reproduce the patched files byte-exact.
