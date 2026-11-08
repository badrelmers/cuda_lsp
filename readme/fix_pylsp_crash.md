
python lsp pylsp gave this error with the this content:

import zzz
import bbb
  
def add_one(x: int) -> int:
    return x + 1
  ffff

here is the log:

2026-11-08 08:44:18,783 Morocco Daylight Time - WARNING - pylsp.config.config - Failed to load hook pylsp_lint: 'IndentationError' object has no attribute 'line'
Traceback (most recent call last):
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\frilouz.py", line 94, in parse
    return parser(code, *args, **kwargs), errors
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\gast\gast.py", line 384, in parse
    return ast_to_gast(_ast.parse(*args, **kwargs))
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\ast.py", line 47, in parse
    return compile(source, filename, mode, flags,
  File "<unknown>", line 6
    ffff
       ^
IndentationError: unindent does not match any outer indentation level

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\pyls_memestra\plugin.py", line 48, in pylsp_lint
    deprecated_uses = memestra(
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\memestra\memestra.py", line 421, in memestra
    module, syntax_errors = frilouz.parse(ast.parse, file_descriptor.read())
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\frilouz.py", line 101, in parse
    code = _build_safe_code(code, se.lineno)
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\frilouz.py", line 40, in _build_safe_code
    for tok in tokenize.tokenize(tmp.readline):
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\tokenize.py", line 512, in _tokenize
    raise IndentationError(
  File "<tokenize>", line 6
    ffff
    ^
IndentationError: unindent does not match any outer indentation level

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\pylsp\config\config.py", line 39, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\pluggy\_manager.py", line 480, in traced_hookexec
    return outcome.get_result()
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\pluggy\_result.py", line 100, in get_result
    raise exc.with_traceback(exc.__traceback__)
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\pluggy\_result.py", line 62, in from_call
    result = func()
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\pluggy\_manager.py", line 477, in <lambda>
    lambda: oldcall(hook_name, hook_impls, caller_kwargs, firstresult)
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\pluggy\_callers.py", line 139, in _multicall
    raise exception.with_traceback(exception.__traceback__)
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\pluggy\_callers.py", line 103, in _multicall
    res = hook_impl.function(*args)
  File "F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\_python\python-lsp-server\PY38embed_x64_NoTclTk\_\lib\site-packages\pyls_memestra\plugin.py", line 58, in pylsp_lint
    logger.error('Syntax error at {} - {} ({})', e.line, e.column, e.message)
AttributeError: 'IndentationError' object has no attribute 'line'

_____________________
i configure the lsp like that:
{
  "lexers": {
    "Python": "python"
  },
  // "cmd_windows": ["F:\\_bin\\_binz\\_ide\\_CudaText\\_tools\\_LSP\\_python\\python-lsp-server\\PY38embed_x64_NoTclTk\\_\\Scripts\\pylsp.exe"],
  "cmd_windows": ["pylsp.exe"],
  "log_stderr": true,


  // i decided to use ruff for linting and formatting 
  "settings": {
    "pylsp": {
      "plugins": {
        // ### Linters / error detectors ###########################################
        // - Pylint is much more thorough (and opinionated) - it reports more issues but can be noisy and slower.
        // - Ruff: An extremely fast linter and formatter written in Rust. modern replacement that implements many flake8 rules plus fixes and is extremely fast. If you pick Ruff you can often stop using pyflakes/pycodestyle/mccabe/flake8 separately. Uses Ruff for speed (faster than Flake8/Pylint). It aims to be a drop-in replacement for dozens of other tools (including Flake8, isort, pydocstyle, and more).
        // - Pyflakes is minimal and fast; it finds common errors (undefined names, unused imports) but not style issues.
        // - pycodestyle - Style checker - checks PEP8-style rules (line length, whitespace, naming etc.).
        // - Flake8 is a runner that combines pyflakes + pycodestyle + mccabe and accepts many plugins (a convenient ecosystem).
        // - McCabe (mccabe) - Cyclomatic complexity checker — warns on high function complexity.
        // - pydocstyle - Docstring style checker — enforces docstring conventions (PEP257).
        "pylint": { "enabled": false }, // Default:false
        "ruff": { "enabled": true }, // Default:true. this does not exist in https://github.com/python-lsp/python-lsp-server/blob/develop/CONFIGURATION.md but it works, and it is enabled by default
        "pyflakes": { "enabled": false }, // Default:true
        "pycodestyle": {
          "enabled": false,
          "indentSize": 2,
          "ignore": [
            "E501", // line too long (93 > 79 characters)
            // "W292",  // no newline at end of file
            "E261",  // at least two spaces before inline comment
            "E302", // expected 2 blank lines, found 1
            "E305", // expected 2 blank lines after class or function definition, found 1
            "E401", // Put imports on separate lines. // this is needed for autopep8 to not touch imports
            "E402", // Fix module level import not at top of file. // this is needed for autopep8 to not touch imports
          ]
        }, // Default:true
        "flake8": { "enabled": false }, // Default:false
        "mccabe": { "enabled": false }, // Default:true
        "pydocstyle": { "enabled": false },

        // ### Type checking ###########################################
        // - MyPy: static type checker — semantic analysis based on type annotations. Integrates into pylsp via pylsp-mypy. (Type checkers complement, not replace, linters.)
        "pylsp_mypy": { "enabled": true }, // Default:true. this does not exist in https://github.com/python-lsp/python-lsp-server/blob/develop/CONFIGURATION.md but it works, and it is enabled by default
  
        // ### formatter options ###########################################
        // - Black: opinionated, deterministic (fewer options). Makes formatting consistent across teams. Uses Black's strict rules (e.g., 88-char lines, no config debates); more deterministic than YAPF/autopep8.
        // - YAPF: configurable formatting (Google style base); sits between autopep8 and Black in flexibility. More algorithmic/intelligent than autopep8 (e.g., considers multiple layouts); configurable beyond PEP 8. Unlike Black, it's not fully opinionated—allows styles/tweaks. Faster for large files due to optimizations.
        // - autopep8: small tool to automatically fix PEP8 violations (less powerful). PEP 8-focused; fixes most pycodestyle issues but avoids semantic changes. Less configurable than YAPF (fewer "knobs"); opinionated like Black but not as strict.
        "autopep8": { "enabled": false }, // Default:true. it does not sort the imports if i disable isort but it still move the imports that are between code to the top but this can be solved by ignoring E401 and E402 in pycodestyle.ignore above. github stars:4.6k
        "yapf": { "enabled": false }, // Default:true. disabling autopep8 is required to use yapf (preferred over autopep8). al usar eso me da errores de black: ERROR - pylsp_black.plugin  Error formatting with black: Cannot parse:....  al usar autopep8 no pasa eso!!! disable  black to use this. it breaks when code is very badly formatted!!!. github stars:14k made by google
        "black": { "enabled": false }, // it gave error when code is very badly formatted!!! the error is: pylsp_black.plugin - Error formatting with black: Cannot parse... pero por lo menos it does not break like yapf. so it needs to fix the lint errors before formatting with this. You're seeing that error because Black refuses to touch files that contain invalid Python syntax — it parses the file with Python's parser and errors out when parsing fails. autopep8 sometimes appears to “work” on files with minor issues because it can be less strict in what it changes (or simply didn’t touch the broken area). Black is stricter — which is usually a good thing, because it prevents formatting code that would change program meaning or silently hide syntax bugs. Black is a solid choice — opinionated, consistent, and widely used — but it requires valid Python. autopep8 can be handy for small fixes, but Black’s strictness is what makes it reliably consistent across projects. So keep Black; just make sure your code is syntactically correct first. github stars:41k
        // "ruff": { "enabled": true }, // it is configured above already in linters
        
        // ___ import sorting _____________
        // - isort: sorts imports consistently (automatic import sorting)
        "isort": { "enabled": false }, // Default:true. this does not exist in https://github.com/python-lsp/python-lsp-server/blob/develop/CONFIGURATION.md but it works, and it is enabled by default. no me gusta ke cambie el order de los imports asi ke lo desactivo

        // ### auto-completion options ###########################################
        "jedi_completion": { "fuzzy": true }, // Default:false
        
        // ### Refactoring ###########################################
        // Refactoring and Completion Tools: Focus on code restructuring, renaming, and auto-completions.
        // - Rope: a purpose-built refactoring engine (rename, extract, move, inline, etc.). Editors and LSP servers use Rope to provide safe structural edits. It’s not a linter or formatter.
        // "rope_autoimport": { "enabled": true }, // Default:false
        // "rope_completion": { "enabled": true }, // Default:false

        // ???????? why cuda do not show it? TODO********************
        "jedi_type_definition": { "enabled": true }, // Default:true

      },
      "configurationSources": ["pycodestyle"], // Default:pycodestyle
      // "configurationSources": ["flake8"], // Default:pycodestyle

      // ### formatter options ###########################################
      // "signature": { "formatter": null }, // Default:black

    }
  }

}

_________________________________
AI answer:
## Short answer

It's neither your CudaText LSP plugin, nor pylsp itself, nor your settings JSON. The bug is in **`pyls-memestra`** — a third-party plugin pip-installed inside your embedded Python (`...\PY38embed_x64_NoTclTk\_\lib\site-packages\pyls_memestra\`). pylsp auto-loads *any* installed package that registers a `pylsp` entry point, so memestra participates in every lint pass whether you configured it or not. Both `pyls-memestra` (0.0.16, Feb 2022) and its parser `frilouz` (0.0.2) are unmaintained, and I checked current master — **both bugs are still there, so upgrading fixes nothing.**

## The failure chain

1. **The trigger**: your snippet is invalid Python. `  ffff` (2-space indent) matches no outer level (module = 0, function body = 4), so the tokenizer raises `IndentationError` at line 6. Totally normal mid-editing state.
2. pylsp lints via **one shared `pylsp_lint` hook** that runs *all* lint plugins (ruff, pylsp-mypy, memestra, …).
3. memestra → `frilouz.parse()`. frilouz is a "fallback parser for broken code" that's supposed to replace bad lines with `pass` — but its recovery (`_build_safe_code`) **tokenizes the original broken text**, and the tokenizer raises the *same* `IndentationError`, which escapes frilouz.
4. pyls_memestra catches it with `except SyntaxError` — but its handler is itself broken:

```python
except SyntaxError as e:
    logger.error('Syntax error at {} - {} ({})', e.line, e.column, e.message)  # ← crash
    raise e
```

`SyntaxError` has **no `.line`, `.column`, `.message` attributes** (the real names are `lineno`, `offset`, `msg`) — verified: `hasattr(e,'line') → False`. So the handler raises `AttributeError` — and even if the logging worked, the next line is `raise e`, which kills the hook anyway.
5. The exception aborts the **entire** `pylsp_lint` call. pylsp catches it, logs your `WARNING ... Failed to load hook pylsp_lint`, and returns `[]`.

**Net effect — the worst part:** while a file has this kind of error, you get *zero diagnostics from any linter, including ruff*, exactly when you need them most. I reproduced this end-to-end: memestra enabled → `[]`; disabled → the "unindent does not match any outer indentation level" diagnostic arrives, and ruff always reports `invalid-syntax` even with default rules.

## Fixes (pick one)

**A. Disable it in your existing settings** (no reinstall needed). Add inside `settings → pylsp → plugins`:

```json
"pyls_memestra": { "enabled": false }
```

⚠️ **Verified gotcha:** the key must be `pyls_memestra` **with an underscore**. That's the entry-point/pluggy name pylsp checks for `enabled`. The plugin's own documented namespace `pyls-memestra` (dash) only sets its *options* — I tested both keys: dash → still loads and still crashes; underscore → properly excluded. (Your pylsp is 1.11.x — your traceback's `config.py, line 39` matches v1.11.0 exactly — which has this mechanism.)

**B. Uninstall it from the embedded Python** (cleanest — you're not using it anyway; it only flags uses of `@deprecated`-decorated functions):

```
F:\_bin\_binz\_ide\_CudaText\_tools\_LSP\python\python-lsp-server\PY38embed_x64_NoTclTk\_\python.exe -m pip uninstall pyls-memestra memestra frilouz
```

**C. Patch it** if you want to keep memestra. In `...\site-packages\pyls_memestra\plugin.py`, replace the `except SyntaxError` block with:

```python
except SyntaxError as e:
    logger.error('Syntax error at %s - %s (%s)',
                 getattr(e, 'lineno', '?'), getattr(e, 'offset', '?'), getattr(e, 'msg', e))
    return diagnostics   # was: raise e  ← this was killing the whole lint hook
```

Either way, the log warning disappears and diagnostics come back. (Bonus finding: `pyls_memestra/plugin.py` also calls `logging.basicConfig(level=logging.ERROR)` at import, which hijacks the whole server's logging — one more reason to drop it.) Worth filing at github.com/QuantStack/pyls-memestra/issues — their latest issue is from 2021, so a PR with fix C would probably be welcome.

And of course the trigger itself: `  ffff` needs to be at column 0 (module level) or aligned inside the function — but a linter plugin should never crash on that.

___________________
so the easiest fix is to disable it, add it after this pydocstyle in my above config:
        "pydocstyle": { "enabled": false },
        "pyls_memestra": { "enabled": false },
        
