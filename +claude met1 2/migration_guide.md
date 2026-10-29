# Migration Guide: Using lsprotocol Exclusively

## Overview
This guide consolidates `events.py`, `structs.py`, and `io_handler.py` into `client.py` and migrates to use `lsprotocol` types exclusively.

## Files to Delete
1. `sansio_lsp_client/events.py`
2. `sansio_lsp_client/structs.py`
3. `sansio_lsp_client/io_handler.py`

## Files to Update

### 1. `sansio_lsp_client/client.py`
**Replace entirely with the new consolidated version provided.**

Key features:
- **Kept type aliases**: `JSONDict`, `JSONList`, `Id` for code readability
- Merged IO handler functions with all original comments preserved
- Only 2 custom types: `ResponseError` and `Metadata` (for OmniSharp)
- All other types use `lsprotocol` directly
- **No reply() methods**: Use client directly in language.py

### 2. `language.py`

#### Import Changes
```python
# OLD:
from .sansio_lsp_client import client as lsp
from .sansio_lsp_client import events
from .sansio_lsp_client.events import ShowMessage, LogMessage

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
| `events.MDocumentSymbols` | `lsp_types.DocumentSymbolResponse` |
| `events.MCallHierarchItems` | `lsp_types.PrepareCallHierarchyResponse` |
| `events.MWorkspaceSymbols` | `lsp_types.WorkspaceSymbolResponse` |
| `events.MFoldingRanges` | `lsp_types.FoldingRangeResponse` |
| `events.MInlayHints` | `lsp_types.InlayHintResponse` |
| `events.WillSaveWaitUntilEdits` | `lsp_types.WillSaveTextDocumentWaitUntilResponse` |
| `events.WorkspaceEdit` | `lsp_types.RenameResponse` |

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
hint = msg.get_hint_str()
signatures, active_signature, active_parameter = msg.get_signatures()

# NEW:
result = msg.result
if result and result.signatures:
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

**DocumentSymbol Response:**
```python
# OLD:
msg.result  # already correct

# NEW:
msg.result  # same - direct access to list
```

#### Server Request/Notification Reply Changes

**REMOVE all `msg.reply()` calls and use `self.client` instead:**

```python
# OLD:
elif msgtype == events.RegisterCapabilityRequest:
    self.scfg.on_register(msg)
    msg.reply()  # ❌ REMOVE
    self.process_queues()

# NEW:
elif msgtype == lsp_types.RegisterCapabilityRequest:
    self.scfg.on_register(msg)
    self.client._send_response(id=msg.id, result={})  # ✅ Use client
    self.process_queues()
```

```python
# OLD:
elif msgtype == events.WorkspaceFolders:
    msg.reply(folders=self.workspace_folders)  # ❌ REMOVE

# NEW:
elif msgtype == lsp_types.WorkspaceFoldersRequest:
    result = None if self.workspace_folders is None else [lsp.Converter.unstructure(f) for f in self.workspace_folders]
    self.client._send_response(id=msg.id, result=result)  # ✅ Use client
```

```python
# OLD:
elif msgtype == events.ConfigurationRequest:
    cfgs = [ServerConfig.get_configuration(self._cfg, cfgitem) for cfgitem in msg.items]
    msg.reply(cfgs)  # ❌ REMOVE

# NEW:
elif msgtype == lsp_types.ConfigurationRequest:
    cfgs = [ServerConfig.get_configuration(self._cfg, cfgitem) for cfgitem in msg.params.items]
    self.client._send_response(id=msg.id, result=cfgs)  # ✅ Use client
```

```python
# OLD:
elif msgtype == events.WorkDoneProgressCreate:
    token = msg.token
    msg.reply()  # ❌ REMOVE

# NEW:
elif msgtype == lsp_types.WorkDoneProgressCreateRequest:
    token = msg.params.token
    self.client._send_response(id=msg.id, result=None)  # ✅ Use client
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
        title = val.title
```

Complete progress handler:
```python
def _on_progress(self, msg):
    if isinstance(msg, lsp_types.WorkDoneProgressCreateRequest):
        token = msg.params.token
        self.progresses.setdefault(token, None)
        self.client._send_response(id=msg.id, result=None)

    elif isinstance(msg, lsp_types.ProgressNotification):
        val = msg.params.value
        token = msg.params.token
        title = None
        
        if isinstance(val, lsp_types.WorkDoneProgressBegin):
            self.progresses[token] = msg
            title = val.title
            msg_str = f': {val.message}' if val.message else ''

        elif isinstance(val, lsp_types.WorkDoneProgressReport):
            if token in self.progresses:
                start_msg = self.progresses[token]
                title = start_msg.params.value.title
            msg_str = ''
            if val.message:
                msg_str = f': {val.message}'
            elif val.percentage is not None:
                msg_str = f' [{val.percentage}%]'

        elif isinstance(val, lsp_types.WorkDoneProgressEnd):
            if token in self.progresses:
                start_msg = self.progresses.pop(token)
                title = start_msg.params.value.title
            msg_str = f': {val.message}' if val.message else ' [Done]'

        if title:
            msg_status(f'{LOG_NAME}: {self.lang_str} - {title + msg_str}')
```

### 3. Update GOTO_EVENT_TYPES in `language.py`
```python
GOTO_EVENT_TYPES = {
    lsp_types.DefinitionResponse,
    lsp_types.ReferencesResponse,
    lsp_types.ImplementationResponse,
    lsp_types.TypeDefinitionResponse,
    lsp_types.DeclarationResponse,
}
```

### 4. ServerConfig Changes

**ONLY use new code - no backward compatibility:**

```python
def __init__(self, initialized, langids, lang_str):
    # initialized is lsp_types.InitializeResponse
    capabilities = initialized.result.capabilities
    
    # rest of the code remains the same
    ...
```

### 5. Complete _on_lsp_msg Example

```python
def _on_lsp_msg(self, msg, message_id=None):
    if DEBUG_MESSAGES:
        self._dbg_msgs = (self._dbg_msgs + [msg])[-128:]

    msgtype = type(msg)

    if msgtype == lsp_types.InitializeResponse:
        self.scfg = ServerConfig(msg, self.langids, self.lang_str)
        app_proc(PROC_EXEC_PLUGIN, 'cuda_lsp,on_lang_inited,'+self.name)

    elif msgtype == lsp_types.RegisterCapabilityRequest:
        self.scfg.on_register(msg)
        self.client._send_response(id=msg.id, result={})
        self.process_queues()
        app_proc(PROC_EXEC_PLUGIN, 'cuda_lsp,on_lang_inited,'+self.name)

    elif msgtype == lsp_types.WorkspaceFoldersRequest:
        result = None if self.workspace_folders is None else [lsp.Converter.unstructure(f) for f in self.workspace_folders]
        self.client._send_response(id=msg.id, result=result)

    elif msgtype == lsp_types.CompletionResponse:
        reqpos = self.request_positions.pop(message_id, None)
        
        result = msg.result
        if result:
            if isinstance(result, lsp_types.CompletionList):
                items = result.items
                is_incomplete = result.is_incomplete or False
            elif isinstance(result, list):
                items = result
                is_incomplete = False
            else:
                items = []
                is_incomplete = False
        else:
            items = []
            is_incomplete = False

        if reqpos:
            try:
                compl = CompletionMan(self, carets=reqpos.carets, h_ed=reqpos.h_ed)
                _last_complete = compl.prepare_complete(message_id, items, is_incomplete)
                if _last_complete:
                    self._last_complete = _last_complete
                    compl.show_complete(self._last_complete.message_id, self._last_complete.filtered_items)
            except AssertionError as e:
                print("NOTE:",e)

    # ... other message types
```

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
6. **Cleaner architecture**: Direct use of client instead of hidden reply() methods
7. **Type aliases preserved**: `JSONDict`, `JSONList`, `Id` kept for readability
