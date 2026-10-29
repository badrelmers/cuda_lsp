# Import Reference for Migration

## lsprotocol.types - What's Available

These are the **correct** types available in `lsprotocol.types`:

### Response Types (use these in language.py)
```python
from lsprotocol import types as lsp_types

# Responses (returned from our requests)
lsp_types.InitializeResponse
lsp_types.ShutdownResponse
lsp_types.CompletionResponse
lsp_types.HoverResponse
lsp_types.SignatureHelpResponse
lsp_types.DefinitionResponse
lsp_types.ReferencesResponse
lsp_types.ImplementationResponse
lsp_types.TypeDefinitionResponse
lsp_types.DeclarationResponse
lsp_types.DocumentSymbolResponse
lsp_types.DocumentFormattingResponse
lsp_types.RangeFormattingResponse
lsp_types.SemanticTokensResponse
lsp_types.RenameResponse
```

### Server Requests (incoming from server)
```python
# Server asking us for something
lsp_types.WorkspaceFoldersRequest
lsp_types.ConfigurationRequest
lsp_types.ShowMessageRequest
lsp_types.WorkDoneProgressCreateRequest
lsp_types.RegisterCapabilityRequest
```

### Server Notifications (incoming from server)
```python
# Server notifying us of something
lsp_types.PublishDiagnosticsNotification
lsp_types.LogMessageNotification
lsp_types.ShowMessageNotification  # Note: Different from ShowMessageRequest!
lsp_types.ProgressNotification
```

### Data Types
```python
# Basic LSP structures
lsp_types.Position
lsp_types.Range
lsp_types.Location
lsp_types.LocationLink
lsp_types.Diagnostic
lsp_types.DiagnosticSeverity
lsp_types.CompletionItem
lsp_types.CompletionList
lsp_types.CompletionItemKind
lsp_types.TextEdit
lsp_types.TextDocumentIdentifier
lsp_types.VersionedTextDocumentIdentifier
lsp_types.TextDocumentItem
lsp_types.TextDocumentPositionParams
lsp_types.WorkspaceFolder
lsp_types.MessageType  # Enum: Error, Warning, Info, Log
lsp_types.MarkupKind
lsp_types.MarkupContent
lsp_types.FormattingOptions
```

---

## What's NOT in lsprotocol.types

These names don't exist, don't try to import them:

❌ `LogMessage` - Use `LogMessageNotification` instead  
❌ `ShowMessage` - Use `ShowMessageRequest` or `ShowMessageNotification`  
❌ `Initialized` - Use `InitializeResponse`  
❌ `Shutdown` - Use `ShutdownResponse`  
❌ `Completion` - Use `CompletionResponse`  
❌ `Definition` - Use `DefinitionResponse`  
❌ `PublishDiagnostics` - Use `PublishDiagnosticsNotification`

---

## Complete Import Map for Each File

### **dlg.py**

```python
# Top of file imports
from lsprotocol.types import (
    MarkupKind,     # For Hint dialog
    MessageType,    # For severity mapping (enum with Error, Warning, Info, Log)
)

# DO NOT import these - they don't exist:
# ❌ LogMessage
# ❌ ShowMessage

# LogMsg namedtuple is defined in dlg.py itself:
LogMsg = namedtuple('LogMsg', 'msg type severity')
```

### **language.py**

```python
# At top of file
from lsprotocol import types as lsp_types

# From sansio_lsp_client - only these custom ones
from .sansio_lsp_client.events import (
    ResponseError,  # Custom error class
    Metadata,       # Custom OmniSharp extension
)

# From dlg.py
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
    LogMsg,  # Namedtuple for creating log messages
)

# Then use lsp_types.* for everything else:
# lsp_types.CompletionResponse
# lsp_types.Hover
# lsp_types.LogMessageNotification
# etc.
```

### **tree.py**

```python
# Change one import at top
from lsprotocol.types import (
    SymbolKind,
    DocumentSymbol,
    SymbolInformation,
)
```

### **lsp.py**

```python
# Add this import
from lsprotocol import types as lsp_types

# Everything else stays the same
```

### **book.py**

```python
# No changes needed!
# But if it imports from structs, change to:
from lsprotocol import types as lsp_types
```

---

## Pattern: Creating LogMsg for Logging

In `language.py`, when handling log/show messages:

```python
# When you receive a LogMessageNotification:
elif msgtype == lsp_types.LogMessageNotification:
    params = msg.params if hasattr(msg, 'params') else msg
    
    # params.type is MessageType enum (Error=1, Warning=2, Info=3, Log=4)
    # params.message is the text string
    
    # Get severity string from enum value
    severity = SEVERITY_MAP.get(params.type.value, SEVERITY_LOG)
    
    # Create LogMsg namedtuple
    log_msg = LogMsg(
        msg=params.message,      # The message text
        type=params.type,         # MessageType enum
        severity=severity         # SEVERITY_ERR, SEVERITY_LOG, etc.
    )
    
    # Log it
    self.plog.log(log_msg)
```

---

## Quick Verification Checklist

After fixing imports, verify:

✅ `dlg.py` imports only `MarkupKind` and `MessageType` from lsprotocol  
✅ `dlg.py` does NOT import `LogMessage` or `ShowMessage`  
✅ `language.py` imports `lsp_types` and uses `lsp_types.LogMessageNotification`  
✅ `language.py` imports `LogMsg` from `dlg`  
✅ `language.py` creates `LogMsg(msg=..., type=..., severity=...)` when logging  
✅ No import errors on CudaText startup  

---

## Error → Solution Map

| Error Message | Solution |
|---------------|----------|
| `cannot import name 'LogMessage'` | Change to `MessageType` or remove import |
| `cannot import name 'ShowMessage'` | Use `ShowMessageRequest` or `ShowMessageNotification` |
| `'LogMessageNotification' has no attribute 'message'` | Access via `msg.params.message` |
| `'InitializeResponse' has no attribute 'capabilities'` | Access via `msg.result.capabilities` |
| `AttributeError: 'dict' has no attribute 'params'` | Use defensive check: `msg.params if hasattr(msg, 'params') else msg` |

---

## Testing Commands

After fixing imports:

```bash
# Test import syntax
python -c "from lsprotocol import types as lsp_types; print(lsp_types.MessageType)"

# Test in CudaText (Console tab)
import lsprotocol.types as lsp_types
print(dir(lsp_types))  # See what's available
print(lsp_types.MessageType.Error)  # Should print MessageType.Error
```
