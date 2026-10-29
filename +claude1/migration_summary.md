# LSProtocol Migration - Action Checklist

## Quick Summary

**Goal**: Replace hand-written LSP event classes with `lsprotocol`'s built-in types using `METHOD_TO_TYPES` for automatic response handling.

**Impact**: ~500 lines removed, better type safety, automatic LSP spec updates.

---

## Step-by-Step Migration

### ✅ Step 1: Update sansio Files (Easy - Just Replace)

**Files**: Replace these 3 files completely with provided code:

1. **`sansio_lsp_client/client.py`** ← Use artifact `client_py_updated`
2. **`sansio_lsp_client/events.py`** ← Use artifact `events_py_updated`  
3. **`sansio_lsp_client/structs.py`** ← Use artifact `structs_py_updated`

**Note**: `io_handler.py` needs NO changes.

---

### ⚠️ Step 2: Update language.py (Complex - Follow Guide)

**File**: `language.py`

**Use**: Artifact `language_py_complete_changes` for line-by-line changes.

**Key Changes**:

#### A. Imports (Top of File)
```python
# REMOVE:
from .sansio_lsp_client import events
from .sansio_lsp_client.events import ShowMessage, LogMessage
from .sansio_lsp_client.structs import (...)  # All struct imports

# ADD:
from lsprotocol import types as lsp_types
from lsprotocol import converters

# KEEP (only these from events):
from .sansio_lsp_client.events import ResponseError, Metadata
```

#### B. Constants Update
```python
# Update GOTO_EVENT_TYPES with lsp_types.*Response
# Update GOTO_TITLES with lsp_types.*Response keys
# Update CALLABLE_COMPLETIONS with lsp_types.CompletionItemKind.*
```

#### C. _on_lsp_msg Method (~300 lines)
- **Pattern**: `if msgtype == lsp_types.XyzResponse:`
- **Access data**: Through `.result` for responses, `.params` for requests
- **Send replies**: `msg._client._send_response(id=msg.id, result=...)`

**Critical conversions**:
```python
# OLD → NEW
events.Initialized → lsp_types.InitializeResponse
events.Completion → lsp_types.CompletionResponse
events.PublishDiagnostics → lsp_types.PublishDiagnosticsNotification
events.Definition → lsp_types.DefinitionResponse
events.SignatureHelp → lsp_types.SignatureHelpResponse
# ... etc (see migration guide)
```

#### D. ServerConfig.__init__
```python
def __init__(self, initialized_result, langids, lang_str):
    # Handle both InitializeResult object and raw dict
    if hasattr(initialized_result, 'capabilities'):
        capabilities = initialized_result.capabilities
    else:
        capabilities = initialized_result
    # ... rest stays same
```

#### E. CompletionMan.prepare_complete
```python
# Convert lsp_types.CompletionItem objects to dicts
for item in items:
    item_dict = {
        'label': item.label,
        'kind': item.kind,
        'insertText': item.insert_text or item.label,
        # ... etc
    }
```

---

### ✅ Step 3: Update Other Files (Simple Import Changes)

#### `lsp.py`
```python
# Just update imports - no logic changes
from lsprotocol import types as lsp_types
```

#### `dlg.py`
```python
# Change one import:
# OLD: from .sansio_lsp_client.structs import MarkupKind
# NEW: from lsprotocol.types import MarkupKind
```

#### `tree.py`
```python
# Change one import:
# OLD: from .sansio_lsp_client.structs import SymbolKind, DocumentSymbol, SymbolInformation
# NEW: from lsprotocol.types import SymbolKind, DocumentSymbol, SymbolInformation
```

#### `book.py`, `util.py`, `snippet_engine.py`
**No changes needed** ✓

---

## Testing Checklist

### Phase 1: Syntax ✓
```bash
cd /path/to/cuda_lsp
python -m py_compile language.py
python -m py_compile lsp.py
python -m py_compile sansio_lsp_client/client.py
```

### Phase 2: Basic Startup ✓
1. Start CudaText
2. Check console for import errors
3. Open file with LSP support
4. Verify server starts

### Phase 3: Feature Testing ✓
- [ ] Code completion (Ctrl+Space)
- [ ] Hover info (Ctrl+hover or mouse hover)
- [ ] Signature help (Ctrl+Shift+Space)
- [ ] Go to definition (Ctrl+click)
- [ ] Find references
- [ ] Diagnostics (errors/warnings)
- [ ] Document formatting
- [ ] Code tree/outline
- [ ] Semantic tokens (if enabled)

### Phase 4: Edge Cases ✓
- [ ] Multiple language servers
- [ ] Server crash/restart
- [ ] Large file (1000+ lines)
- [ ] Project folder change
- [ ] Save with format-on-save

---

## Common Errors & Fixes

### Error: `'InitializeResponse' object has no attribute 'capabilities'`
**Fix**: Update ServerConfig.__init__ to handle both object and dict:
```python
capabilities = initialized_result.capabilities if hasattr(initialized_result, 'capabilities') else initialized_result
```

### Error: `'CompletionResponse' object has no attribute 'completion_list'`
**Fix**: Access through `.result`:
```python
if msg.result:
    if isinstance(msg.result, lsp_types.CompletionList):
        items = msg.result.items
```

### Error: `'PublishDiagnosticsNotification' object has no attribute 'uri'`
**Fix**: Access through `.params`:
```python
params = msg.params if hasattr(msg, 'params') else msg
uri = params.uri
```

### Error: `TypeError: structure() argument after ** must be a mapping`
**Fix**: Ensure you're passing dicts to `structure()`, not objects:
```python
# WRONG: structure(completion_item_object, CompletionItem)
# RIGHT: structure(completion_item_dict, CompletionItem)
```

---

## Verification Steps

After migration, verify:

1. **No import errors** on startup
2. **Server initialization** succeeds (check console)
3. **Completion works** - you get completion items
4. **Hover shows info** - tooltips appear
5. **Diagnostics appear** - errors/warnings show
6. **No "unknown Message type"** errors in console

---

## Rollback Instructions

If something breaks:

```bash
git stash  # Save your changes
git checkout HEAD -- .  # Restore old version
# Or restore from backup
```

Then file an issue with:
- Error message
- Stack trace
- Which feature failed
- Language server used

---

## Benefits After Migration

✅ **Code Reduction**: ~500 lines removed  
✅ **Type Safety**: Full mypy/pyright support  
✅ **Maintainability**: LSP updates from lsprotocol  
✅ **Automatic**: New methods via METHOD_TO_TYPES  
✅ **Correctness**: Official LSP types  

---

## Need Help?

1. Check `migration_guide` artifact for detailed patterns
2. Check `language_py_complete_changes` for exact code
3. Check `client_py_updated` for response handling examples

---

## Final Notes

- **Take your time** - this is a significant refactoring
- **Test incrementally** - do one file at a time if needed
- **Keep backups** - git commit before starting
- **Ask questions** - if something's unclear, ask!

The migration is straightforward if you follow the patterns. The key insight is:
- **Responses**: Access data through `.result`
- **Requests/Notifications**: Access data through `.params`
- **Replies**: Use `msg._client._send_response()`

Good luck! 🚀
