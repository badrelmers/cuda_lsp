# LSProtocol Migration Guide

## Summary of Changes

This migration replaces custom hand-written LSP event classes with `lsprotocol`'s built-in types, leveraging `METHOD_TO_TYPES` for automatic response handling.

---

## 1. Files to Update

### A. `sansio_lsp_client/client.py`
✅ **Already provided above** - Replace entire file

**Key changes:**
- Import `lsp_types.METHOD_TO_TYPES` 
- New `_handle_response()` using automatic structuring
- Updated `_handle_request()` for server requests
- All method signatures now use `lsp_types.*` instead of custom classes

### B. `sansio_lsp_client/events.py`
✅ **Already provided above** - Replace entire file

**Removed classes** (now use lsprotocol):
- `Initialized` → use `lsp_types.InitializeResponse`
- `Shutdown` → use `lsp_types.ShutdownResponse`
- `ShowMessage` → use `lsp_types.ShowMessageRequest/Notification`
- `LogMessage` → use `lsp_types.LogMessageNotification`
- `WorkDoneProgress*` → use `lsp_types.ProgressNotification`
- `Completion` → use `lsp_types.CompletionResponse`
- `SignatureHelp` → use `lsp_types.SignatureHelpResponse`
- `Definition`, `References`, etc. → use `lsp_types.*Response`
- `PublishDiagnostics` → use `lsp_types.PublishDiagnosticsNotification`
- `RegisterCapabilityRequest` → use `lsp_types.RegisterCapabilityRequest`
- `ConfigurationRequest` → use `lsp_types.ConfigurationRequest`
- `WorkspaceFolders` → use `lsp_types.WorkspaceFoldersRequest`

**Kept classes:**
- `ResponseError` - custom error handling
- `Metadata` - OmniSharp-specific extension

### C. `sansio_lsp_client/structs.py`
✅ **Already provided above** - Replace entire file

**Removed** (now use lsprotocol directly):
- All `lsp_types.*` re-exports
- Custom `Range`, `Position`, etc.
- Helper functions like `make_text_document_content_change_event`

**Kept:**
- `Request`, `Response` - internal message structures
- `unstructure()`, `structure()` - converter helpers
- Type aliases: `JSONDict`, `JSONList`, `Id`

### D. `sansio_lsp_client/io_handler.py`
✅ **No changes needed** - Works as-is

---

## 2. Main Plugin Files

### A. `language.py` - **MAJOR CHANGES NEEDED**

#### Import Changes:
```python
# OLD:
from .sansio_lsp_client import events
from .sansio_lsp_client.structs import (
    CompletionRegistrationOptions,
    TextDocumentSyncKind,
    # ... many more
)

# NEW:
from lsprotocol import types as lsp_types
from .sansio_lsp_client.events import (
    ResponseError,  # Keep
    Metadata,       # Keep
)
```

#### Update Type References:
Replace all `events.*` and `structs.*` with `lsp_types.*`:

```python
# OLD:
GOTO_EVENT_TYPES = {
    events.Definition,
    events.References,
    events.Implementation,
    events.TypeDefinition,
    events.Declaration,
}

# NEW:
GOTO_EVENT_TYPES = {
    lsp_types.DefinitionResponse,
    lsp_types.ReferencesResponse,
    lsp_types.ImplementationResponse,
    lsp_types.TypeDefinitionResponse,
    lsp_types.DeclarationResponse,
}
```

#### Update `_on_lsp_msg()` Method:
**See the detailed example provided above in `language_py_key_changes` artifact**

Key patterns:
1. Access `result` attribute for response data
2. Access `params` attribute for request/notification data
3. Use `msg._client` to send replies for server requests
4. Handle both old and new attribute patterns with `hasattr()` checks

#### Update `ServerConfig.__init__()`:
```python
# OLD:
def __init__(self, initialized, langids, lang_str):
    capabilities = initialized.capabilities

# NEW:
def __init__(self, initialized_result, langids, lang_str):
    # Handle both InitializeResult and raw dict
    if hasattr(initialized_result, 'capabilities'):
        capabilities = initialized_result.capabilities
    else:
        capabilities = initialized_result
```

#### Update GOTO_TITLES:
```python
GOTO_TITLES = {
    lsp_types.DefinitionResponse: _('Go to: definition'),
    lsp_types.ReferencesResponse: _('Go to: references'),
    lsp_types.ImplementationResponse: _('Go to: implementation'),
    lsp_types.TypeDefinitionResponse: _('Go to: type definition'),
    lsp_types.DeclarationResponse: _('Go to: declaration'),
}
```

#### Update CompletionMan:
```python
# Access completion items from lsprotocol types
def prepare_complete(self, message_id, items, is_incomplete, is_cached=False):
    # items is now list[lsp_types.CompletionItem]
    # Convert to dict format if needed for compatibility
    filtered_items = []
    for item in items:
        # Access attributes directly or convert to dict
        filtered_items.append({
            'label': item.label,
            'kind': item.kind,
            'insertText': item.insert_text or item.label,
            'filterText': item.filter_text,
            'sortText': item.sort_text,
            # ... other fields
        })
```

### B. `lsp.py` - **MINIMAL CHANGES**

Update imports:
```python
# OLD:
from .language import Language

# NEW:
from .language import Language, CompletionMan, DiagnosticsMan

# All lsp_types imports now through lsprotocol
from lsprotocol import types as lsp_types
```

### C. `book.py` - **NO CHANGES**
Works as-is.

### D. `dlg.py` - **MINIMAL CHANGES**

Update imports:
```python
# OLD:
from .sansio_lsp_client.structs import MarkupKind

# NEW:
from lsprotocol.types import MarkupKind
```

Update type checks:
```python
# In Hint.show():
if markupkind == MarkupKind.Markdown:
    # ... same logic
```

### E. `tree.py` - **MINIMAL CHANGES**

Update imports:
```python
# OLD:
from .sansio_lsp_client.structs import SymbolKind, DocumentSymbol, SymbolInformation

# NEW:
from lsprotocol.types import SymbolKind, DocumentSymbol, SymbolInformation
```

All enum access remains the same:
```python
SymbolKind.FILE
SymbolKind.METHOD
# etc.
```

### F. `util.py` - **NO CHANGES**
Works as-is.

---

## 3. Handling Response Data

### Pattern for Accessing Response Data:

```python
# OLD (custom events):
if msgtype == events.Completion:
    items = msg.completion_list['items']

# NEW (lsprotocol):
if msgtype == lsp_types.CompletionResponse:
    if msg.result:
        if isinstance(msg.result, lsp_types.CompletionList):
            items = msg.result.items
        elif isinstance(msg.result, list):
            items = msg.result
```

### Pattern for Server Requests:

```python
# OLD:
elif msgtype == events.ConfigurationRequest:
    cfgs = [...]
    msg.reply(cfgs)

# NEW:
elif msgtype == lsp_types.ConfigurationRequest:
    items = msg.params.items
    cfgs = [...]
    if hasattr(msg, '_client'):
        msg._client._send_response(id=msg.id, result=cfgs)
```

---

## 4. Testing Strategy

### Phase 1: Syntax Check
1. Replace all files
2. Run: `python -m py_compile language.py`
3. Fix import errors

### Phase 2: Basic Function Test
1. Start CudaText with plugin
2. Open a file with LSP support
3. Check console for errors

### Phase 3: Feature Testing
Test each feature:
- ✓ Completion
- ✓ Hover
- ✓ Signature Help
- ✓ Go to Definition
- ✓ References
- ✓ Diagnostics
- ✓ Formatting
- ✓ Document Symbols (tree)

### Phase 4: Edge Cases
- Multiple language servers
- Server crashes/restarts
- Large files
- Semantic tokens
- Progress reporting

---

## 5. Common Pitfalls

### ❌ Don't Do This:
```python
# Accessing result as if it's the event itself
if msg.completion_list:  # WRONG
```

### ✅ Do This:
```python
# Access through result
if msg.result and isinstance(msg.result, lsp_types.CompletionList):
    items = msg.result.items
```

### ❌ Don't Do This:
```python
# Assuming params is always present
token = msg.params.token  # Might error
```

### ✅ Do This:
```python
# Safe access with fallback
params = msg.params if hasattr(msg, 'params') else msg
token = params.token
```

---

## 6. Benefits of This Migration

1. **Less Code**: Removed ~500 lines of custom event classes
2. **Type Safety**: Full type hints from lsprotocol
3. **Maintainability**: Updates to LSP spec come from lsprotocol
4. **Automatic**: METHOD_TO_TYPES handles new methods automatically
5. **Correctness**: Official LSP types, less chance of bugs

---

## 7. Rollback Plan

If migration fails:
1. Keep backup of old files
2. Revert changes in git
3. File issue with specific error messages

---

## 8. Next Steps

1. ✅ Replace `client.py`, `events.py`, `structs.py` (provided above)
2. ⚠️ Update `language.py` (use patterns from `language_py_key_changes`)
3. ⚠️ Update imports in `lsp.py`, `dlg.py`, `tree.py`
4. ⚠️ Test thoroughly
5. 🎉 Enjoy cleaner, more maintainable code!

---

## Quick Reference: Type Mappings

| Old Custom Type | New lsprotocol Type |
|----------------|---------------------|
| `events.Initialized` | `lsp_types.InitializeResponse` |
| `events.Completion` | `lsp_types.CompletionResponse` |
| `events.SignatureHelp` | `lsp_types.SignatureHelpResponse` |
| `events.Definition` | `lsp_types.DefinitionResponse` |
| `events.References` | `lsp_types.ReferencesResponse` |
| `events.Implementation` | `lsp_types.ImplementationResponse` |
| `events.PublishDiagnostics` | `lsp_types.PublishDiagnosticsNotification` |
| `events.LogMessage` | `lsp_types.LogMessageNotification` |
| `events.ShowMessage` | `lsp_types.ShowMessageRequest` |
| `events.RegisterCapabilityRequest` | `lsp_types.RegisterCapabilityRequest` |
| `events.WorkspaceFolders` | `lsp_types.WorkspaceFoldersRequest` |
| `structs.Position` | `lsp_types.Position` |
| `structs.Range` | `lsp_types.Range` |
| `structs.CompletionItem` | `lsp_types.CompletionItem` |
| `structs.Diagnostic` | `lsp_types.Diagnostic` |
| `structs.*` | `lsp_types.*` |

**Exceptions** (keep custom):
- `ResponseError` - custom error handling
- `Metadata` - OmniSharp extension
