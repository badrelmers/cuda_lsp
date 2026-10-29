# Migration Guide: Using lsprotocol Exclusively

## Overview
This guide consolidates `events.py`, `structs.py`, and `io_handler.py` into `client.py` and migrates to use `lsprotocol` types exclusively.

## Files to Delete
1. `sansio_lsp_client/events.py`
2. `sansio_lsp_client/structs.py`
3. `sansio_lsp_client/io_handler.py`

## Files to Update

### 1. `sansio_lsp_client/client.py`
**Replace entirely with the new consolidated version provided in the first artifact.**

Key changes:
- Merged IO handler functions (`_make_request`, `_make_response`, `_parse_messages`)
- Kept only 2 custom types: `ResponseError` and `Metadata` (for OmniSharp)
- All other types now use `lsprotocol` directly
- Response handling returns `lsprotocol` types

### 2. `language.py`

#### Import Changes
```python
# OLD:
from .sansio_lsp_client import client as lsp
from .sansio_lsp_client import events

# NEW:
from .sansio_lsp_client import client as lsp
from .sansio_lsp_client.client import ResponseError, Metadata
from lsprotocol import types as lsp_types
```

#### Type Mapping Changes

| Old Type | New Type |
|----------|----------|
| `events.Initialized` | `lsp_types.InitializeResponse` |
| `events.RegisterCapabilityRequest` | `lsp_types.RegisterCapabilityRequest` |
| `events.WorkspaceFolders` | `lsp_types.WorkspaceFoldersRequest` |
| `events.Completion` | `lsp_types.CompletionResponse` |
| `events.SignatureHelp` | `lsp_types.SignatureHelpResponse` |
| `events.SemanticTokens` | `lsp_types.SemanticTokensResponse` |
| `events.PublishDiagnostics` | `lsp_types.PublishDiagnosticsNotification` |
| `events.ConfigurationRequest` | `lsp_types.ConfigurationRequest` |
| `events.LogMessage` | `lsp_types.LogMessageNotification` |
| `events.ShowMessage` | `lsp_types.ShowMessageNotification` |
| `events.WorkDoneProgressCreate` | `lsp_types.WorkDoneProgressCreateRequest` |
| `events.WorkDoneProgress*` | `lsp_types.ProgressNotification` |
| `events.Shutdown` | `lsp_types.ShutdownResponse` |
| `events.Hover` | `lsp_types.HoverResponse` |

#### Response Data Access Changes

**Completion Response:**
```python
# OLD:
if msg.completion_list:
    items = msg.completion_list['items']
    is_incomplete = msg.completion_list['isIncomplete']

# NEW:
result = msg.result
if result:
    if isinstance(result, lsp_types.CompletionList):
        items = result.items
        is_incomplete = result.is_incomplete or False
    elif isinstance(result, list):
        items = result
        is_incomplete = False
```

**Hover Response:**
```python
# OLD:
contents = msg.contents

# NEW:
result = msg.result
if result:
    contents = result.contents
```

**SignatureHelp Response:**
```python
# OLD:
signatures = msg.signatures
active_signature = msg.activeSignature
active_parameter = msg.activeParameter

# NEW:
result = msg.result
if result:
    signatures = result.signatures
    active_signature = result.active_signature
    active_parameter = result.active_parameter
```

**PublishDiagnostics:**
```python
# OLD:
msg.uri
msg.diagnostics

# NEW:
msg.params.uri
msg.params.diagnostics
```

**LogMessage/ShowMessage:**
```python
# OLD:
msg.type
msg.message

# NEW:
msg.params.type
msg.params.message
```

**SemanticTokens:**
```python
# OLD:
msg.data
msg.resultId

# NEW:
result = msg.result
if result:
    result.data
    result.result_id
```

#### Progress Handling Changes
```python
# OLD:
if isinstance(msg, events.WorkDoneProgressBegin):
    val = msg.value

# NEW:
if isinstance(msg, lsp_types.ProgressNotification):
    val = msg.params.value
    if isinstance(val, lsp_types.WorkDoneProgressBegin):
        # Handle begin
```

### 3. `dlg.py`
No major changes needed. The dialog classes work with dictionaries and don't depend on the old event types.

### 4. Update GOTO_TITLES in `language.py`
```python
GOTO_TITLES = {
    lsp_types.DefinitionResponse:      _('Go to: definition'),
    lsp_types.ReferencesResponse:      _('Go to: references'),
    lsp_types.ImplementationResponse:  _('Go to: implementation'),
    lsp_types.TypeDefinitionResponse:  _('Go to: type definition'),
    lsp_types.DeclarationResponse:     _('Go to: declaration'),
}
```

### 5. ServerConfig Changes
Handle both old initialization (during migration) and new:
```python
def __init__(self, initialized, langids, lang_str):
    # Handle both InitializeResponse and old dict format
    if hasattr(initialized, 'result'):
        capabilities = initialized.result.capabilities
    elif hasattr(initialized, 'capabilities'):
        capabilities = initialized.capabilities
    else:
        capabilities = initialized  # Legacy dict format
```

## Request Reply Methods

Some request types have a `reply()` method that needs the `_client` reference:

```python
# These types need _client set for replying:
- lsp_types.WorkspaceFoldersRequest
- lsp_types.ConfigurationRequest
- lsp_types.WorkDoneProgressCreateRequest
- lsp_types.RegisterCapabilityRequest
```

The client automatically sets `_client` attribute on these when handling requests.

## Testing Checklist

After migration, test these features:
- [ ] Server initialization
- [ ] Code completion
- [ ] Hover information
- [ ] Signature help
- [ ] Go to definition
- [ ] Find references
- [ ] Diagnostics display
- [ ] Document formatting
- [ ] Semantic tokens
- [ ] Document symbols (tree)
- [ ] Progress notifications
- [ ] Configuration requests
- [ ] Workspace folder changes

## Benefits of This Migration

1. **Single source of truth**: All LSP types come from `lsprotocol`
2. **Reduced code maintenance**: No need to maintain parallel type definitions
3. **Better type safety**: `lsprotocol` is actively maintained and type-checked
4. **Automatic updates**: New LSP features automatically available when updating `lsprotocol`
5. **Simplified codebase**: Three fewer files to maintain

## Backward Compatibility Notes

The main breaking change is how response data is accessed:
- Responses now have `.result` attribute containing the actual data
- Notifications have `.params` attribute containing the parameters
- Custom `ResponseError` and `Metadata` classes maintained for special cases
