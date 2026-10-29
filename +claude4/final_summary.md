# Final Summary - All Required Changes

## Quick Reference: What to Copy-Paste

### 1. Replace These 3 Files Completely ✅
Just copy-paste the entire file:

- **`sansio_lsp_client/client.py`** ← Use artifact `client_py_updated`
- **`sansio_lsp_client/events.py`** ← Use artifact `events_py_updated`
- **`sansio_lsp_client/structs.py`** ← Use artifact `structs_py_updated`

---

### 2. CompletionMan Methods (language.py)

Find the `CompletionMan` class (around line 1600) and replace these 3 methods:

#### Method 1: prepare_complete
**Replace entire method** with: artifact `prepare_complete_full`

#### Method 2: show_complete  
**Replace entire method** with: artifact `show_complete_full`

#### Method 3: do_complete
**Replace entire method** with: artifact `do_complete_full`

---

### 3. Import Changes

#### dlg.py (Top of file)
**Change:**
```python
from .sansio_lsp_client.structs import MarkupKind
```
**To:**
```python
from lsprotocol.types import MarkupKind, MessageType
```

**Delete from PanelLog.__init__ (line ~397):**
```python
# DELETE THESE LINES:
global LogMessage, ShowMessage
from .sansio_lsp_client import LogMessage, ShowMessage
# OR
from lsprotocol.types import LogMessage, ShowMessage

# DELETE THIS TOO:
PanelLog.type_captions = {
    ShowMessage: TYPE_MSG,
    LogMessage: TYPE_LOG,
}
```

#### tree.py (Top of file)
**Change:**
```python
from .sansio_lsp_client.structs import SymbolKind, DocumentSymbol, SymbolInformation
```
**To:**
```python
from lsprotocol.types import SymbolKind, DocumentSymbol, SymbolInformation
```

#### lsp.py (Top of file)
**Add:**
```python
from lsprotocol import types as lsp_types
```

#### language.py (Top of file)
**Delete ALL imports from `.sansio_lsp_client.structs` EXCEPT:**
```python
from .sansio_lsp_client.structs import unstructure
```

**Add:**
```python
from lsprotocol import types as lsp_types
```

**Keep only these from events:**
```python
from .sansio_lsp_client.events import ResponseError, Metadata
```

**Add to dlg imports:**
```python
from .dlg import (
    Hint,
    SignaturesDialog,
    TYPE_DIAG,
    PanelLog,
    SEVERITY_MAP,
    SEVERITY_ERR,
    SEVERITY_LOG,
    SEVERITY_WRN,
    SEVERITY_INFO,
    LogMsg,  # ADD THIS
)
```

---

### 4. Search & Replace in language.py

Use Ctrl+H (Find & Replace) - do these in order:

| Find | Replace |
|------|---------|
| `WorkspaceFolder(` | `lsp_types.WorkspaceFolder(` |
| `CompletionItemKind.` | `lsp_types.CompletionItemKind.` |
| `CompletionTriggerKind.` | `lsp_types.CompletionTriggerKind.` |
| `TextDocumentSyncKind.` | `lsp_types.TextDocumentSyncKind.` |
| `DiagnosticSeverity.` | `lsp_types.DiagnosticSeverity.` |
| `InsertTextFormat.` | `lsp_types.InsertTextFormat.` |
| `MarkupKind.` | `lsp_types.MarkupKind.` |
| `isinstance(link, Location)` | `isinstance(link, lsp_types.Location)` |
| `isinstance(link, LocationLink)` | `isinstance(link, lsp_types.LocationLink)` |
| `isinstance(item, MarkupContent)` | `isinstance(item, lsp_types.MarkupContent)` |
| `msgtype == events.Initialized` | `msgtype == lsp_types.InitializeResponse` |
| `msgtype == events.Completion` | `msgtype == lsp_types.CompletionResponse` |
| `msgtype == events.SignatureHelp` | `msgtype == lsp_types.SignatureHelpResponse` |
| `msgtype == events.Definition` | `msgtype == lsp_types.DefinitionResponse` |
| `msgtype == events.References` | `msgtype == lsp_types.ReferencesResponse` |
| `msgtype == events.Implementation` | `msgtype == lsp_types.ImplementationResponse` |
| `msgtype == events.TypeDefinition` | `msgtype == lsp_types.TypeDefinitionResponse` |
| `msgtype == events.Declaration` | `msgtype == lsp_types.DeclarationResponse` |
| `msgtype == events.PublishDiagnostics` | `msgtype == lsp_types.PublishDiagnosticsNotification` |
| `msgtype == events.LogMessage` | `msgtype == lsp_types.LogMessageNotification` |
| `msgtype == events.ShowMessage` | `msgtype == lsp_types.ShowMessageRequest` |
| `msgtype == events.Shutdown` | `msgtype == lsp_types.ShutdownResponse` |
| `msgtype == events.RegisterCapabilityRequest` | `msgtype == lsp_types.RegisterCapabilityRequest` |
| `msgtype == events.WorkspaceFolders` | `msgtype == lsp_types.WorkspaceFoldersRequest` |
| `msgtype == events.MDocumentSymbols` | `msgtype == lsp_types.DocumentSymbolResponse` |
| `msgtype == events.DocumentFormatting` | `msgtype == lsp_types.DocumentFormattingResponse` |
| `msgtype == events.ConfigurationRequest` | `msgtype == lsp_types.ConfigurationRequest` |
| `msgtype == events.SemanticTokens` | `msgtype == lsp_types.SemanticTokensResponse` |

---

### 5. Update Constants in language.py

**Find and replace these constant definitions:**

#### GOTO_EVENT_TYPES (around line 50-60)
```python
GOTO_EVENT_TYPES = {
    lsp_types.DefinitionResponse,
    lsp_types.ReferencesResponse,
    lsp_types.ImplementationResponse,
    lsp_types.TypeDefinitionResponse,
    lsp_types.DeclarationResponse,
}
```

#### GOTO_TITLES (around line 90-100)
```python
GOTO_TITLES = {
    lsp_types.DefinitionResponse: _('Go to: definition'),
    lsp_types.ReferencesResponse: _('Go to: references'),
    lsp_types.ImplementationResponse: _('Go to: implementation'),
    lsp_types.TypeDefinitionResponse: _('Go to: type definition'),
    lsp_types.DeclarationResponse: _('Go to: declaration'),
}
```

#### CALLABLE_COMPLETIONS (around line 70)
```python
CALLABLE_COMPLETIONS = {
    lsp_types.CompletionItemKind.Method,
    lsp_types.CompletionItemKind.Function,
    lsp_types.CompletionItemKind.Constructor,
}
```

---

## Files You DON'T Need to Change

These files need **NO CHANGES**:
- ✅ `book.py`
- ✅ `util.py`
- ✅ `snippet_engine.py`
- ✅ `sansio_lsp_client/io_handler.py`

---

## Testing Checklist

After all changes:

### Basic Startup
- [ ] CudaText starts without errors
- [ ] No import errors in console
- [ ] LSP server initializes

### Core Features
- [ ] Completion works (Ctrl+Space)
- [ ] Hover works (mouse hover)
- [ ] Signature help works
- [ ] Go to definition works
- [ ] Find references works
- [ ] Diagnostics appear
- [ ] Format document works

### Console Check
- [ ] No "cannot import" errors
- [ ] No "AttributeError" errors
- [ ] No "NameError" errors
- [ ] No "unknown Message type" errors

---

## Estimated Time

- **Easy tasks** (30 min): Files 1-3, simple imports
- **Medium tasks** (30 min): Search & replace, constants
- **Complex tasks** (30 min): CompletionMan methods, testing
- **Total**: ~90 minutes for careful migration

---

## If You Get Stuck

1. **Check console for error message**
2. **Note the file and line number**
3. **Look up the error in the appropriate artifact:**
   - Import errors → `import_reference`
   - Type errors → `search_replace_guide`
   - Method errors → `completionman_replacement_guide`
   - Logic errors → `language_py_complete_changes`

4. **Common error patterns:**
   - `NameError: name 'X' is not defined` → Add `lsp_types.` prefix
   - `AttributeError: 'X' object has no attribute 'Y'` → Access through `.result` or `.params`
   - `cannot import name 'X'` → Wrong import, check `import_reference`

---

## Success! ✨

When you see:
- ✅ No errors on startup
- ✅ Completion popup appears
- ✅ Hover info shows
- ✅ Diagnostics work

**You're done!** The migration is complete.

Your codebase is now:
- ✅ Using official lsprotocol types
- ✅ Automatically compatible with LSP spec updates
- ✅ ~500 lines lighter
- ✅ Better type safety
- ✅ More maintainable

**Congratulations!** 🎉
