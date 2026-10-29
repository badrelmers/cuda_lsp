# Quick Reference - Key Changes Summary

## What's Kept vs What's Changed

### ✅ Kept (for readability)
- **Type aliases**: `JSONDict`, `JSONList`, `Id`
- **All original comments** in IO handler functions
- **Custom types**: `ResponseError`, `Metadata` (for OmniSharp)

### ❌ Removed
- **Files deleted**: `events.py`, `structs.py`, `io_handler.py`
- **reply() methods**: Now use `self.client._send_response()` directly
- **Backward compatibility code**: Clean new implementation only

## Import Pattern

```python
from .sansio_lsp_client import client as lsp
from .sansio_lsp_client.client import ResponseError, Metadata
from lsprotocol import types as lsp_types

Converter = lsp.Converter  # If you need it for unstructure
```

## Response Access Pattern

All responses now have `.result` attribute:
```python
# Pattern: msg.result contains the actual data
result = msg.result
if result:
    # Use result...
```

All notifications have `.params` attribute:
```python
# Pattern: msg.params contains the parameters
msg.params.uri
msg.params.diagnostics
msg.params.type
msg.params.message
```

## Reply Pattern (Server Requests)

**OLD:** `msg.reply(data)`  
**NEW:** `self.client._send_response(id=msg.id, result=data)`

Examples:
```python
# Simple confirmation
self.client._send_response(id=msg.id, result={})

# With data
self.client._send_response(id=msg.id, result=cfgs)

# With None
self.client._send_response(id=msg.id, result=None)
```

## Type Checking Pattern

```python
msgtype = type(msg)

if msgtype == lsp_types.CompletionResponse:
    # Handle completion
elif msgtype == lsp_types.HoverResponse:
    # Handle hover
elif msgtype == lsp_types.PublishDiagnosticsNotification:
    # Handle diagnostics
elif msgtype == ResponseError:
    # Handle errors
```

## Common Response Handlers

### Completion
```python
result = msg.result
if result:
    if isinstance(result, lsp_types.CompletionList):
        items = result.items
        is_incomplete = result.is_incomplete or False
    elif isinstance(result, list):
        items = result
        is_incomplete = False
```

### Hover
```python
result = msg.result
if result and result.contents:
    contents = result.contents
```

### Diagnostics
```python
self.diagnostics_man.set_diagnostics(
    uri=msg.params.uri, 
    diag_list=msg.params.diagnostics
)
```

### Progress
```python
if isinstance(msg, lsp_types.ProgressNotification):
    val = msg.params.value
    token = msg.params.token
    
    if isinstance(val, lsp_types.WorkDoneProgressBegin):
        title = val.title
```

## ServerConfig Initialization

```python
def __init__(self, initialized, langids, lang_str):
    # initialized is lsp_types.InitializeResponse
    capabilities = initialized.result.capabilities
    
    # Handle nested capabilities (some servers do this)
    if 'capabilities' in capabilities:
        capabilities = capabilities['capabilities']
    
    # Rest of code...
```

## Files Structure After Migration

```
cuda_lsp/
├── sansio_lsp_client/
│   └── client.py          # Everything consolidated here
├── language.py            # Updated to use lsprotocol
├── dlg.py                 # No changes needed
├── book.py                # No changes needed
├── tree.py                # No changes needed
├── util.py                # No changes needed
└── lsp.py                 # No changes needed
```

## Migration Steps

1. **Backup** your current code
2. **Replace** `sansio_lsp_client/client.py` with new version
3. **Delete** `events.py`, `structs.py`, `io_handler.py`
4. **Update** `language.py`:
   - Change imports
   - Update `_on_lsp_msg()` method
   - Update `_on_progress()` method
   - Update GOTO_EVENT_TYPES and GOTO_TITLES
   - Update ServerConfig.__init__()
5. **Test** all LSP features

## Testing Order

1. Server initialization ← Start here
2. Hover information
3. Code completion
4. Diagnostics
5. Go to definition
6. All other features

If initialization works, most other features will work too!
