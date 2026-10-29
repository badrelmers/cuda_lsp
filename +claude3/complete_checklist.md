# Complete Migration Checklist

Follow these steps in order. Check off each item as you complete it.

---

## 🟢 Step 1: Replace sansio_lsp_client Files (Easy)

- [ ] **1.1** Backup current files
- [ ] **1.2** Replace `sansio_lsp_client/client.py` with `client_py_updated` artifact
- [ ] **1.3** Replace `sansio_lsp_client/events.py` with `events_py_updated` artifact
- [ ] **1.4** Replace `sansio_lsp_client/structs.py` with `structs_py_updated` artifact
- [ ] **1.5** Keep `sansio_lsp_client/io_handler.py` unchanged

---

## 🟡 Step 2: Fix dlg.py (Medium)

- [ ] **2.1** At top of file, change imports:
  ```python
  # FROM:
  from .sansio_lsp_client.structs import MarkupKind
  # TO:
  from lsprotocol.types import MarkupKind, MessageType
  ```

- [ ] **2.2** In `PanelLog.__init__` (line ~397), **DELETE** these lines:
  ```python
  global LogMessage, ShowMessage
  from .sansio_lsp_client import LogMessage, ShowMessage
  # OR
  from lsprotocol.types import LogMessage, ShowMessage
  ```

- [ ] **2.3** In `PanelLog.__init__`, **DELETE** or comment out:
  ```python
  PanelLog.type_captions = {
      ShowMessage: TYPE_MSG,
      LogMessage: TYPE_LOG,
  }
  ```

- [ ] **2.4** Update `PanelLog.log()` method (line ~550):
  ```python
  def log(self, msg):
      """Logs a message. msg should be LogMsg namedtuple"""
      if isinstance(msg, LogMsg):
          self.log_str(msg.msg, type_=msg.type, severity=msg.severity, scroll=True)
      else:
          # Fallback
          self.log_str(str(msg), type_='unknown', severity=SEVERITY_LOG, scroll=True)
  ```

---

## 🔴 Step 3: Fix language.py Imports (Complex)

- [ ] **3.1** At the very top, **REPLACE** entire import section with:
  ```python
  from lsprotocol import types as lsp_types
  ```

- [ ] **3.2** **KEEP ONLY** these sansio imports:
  ```python
  from .sansio_lsp_client import client as lsp
  from .sansio_lsp_client.events import ResponseError, Metadata
  from .sansio_lsp_client.structs import unstructure
  ```

- [ ] **3.3** **DELETE** all other `from .sansio_lsp_client.structs import ...`

- [ ] **3.4** **ADD** to dlg imports:
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

## 🔴 Step 4: Search & Replace in language.py

Use your editor's Find & Replace (Ctrl+H). Do these in order:

### Core Types
- [ ] **4.1** `WorkspaceFolder(` → `lsp_types.WorkspaceFolder(`
- [ ] **4.2** `CompletionItemKind.` → `lsp_types.CompletionItemKind.`
- [ ] **4.3** `CompletionTriggerKind.` → `lsp_types.CompletionTriggerKind.`
- [ ] **4.4** `TextDocumentSyncKind.` → `lsp_types.TextDocumentSyncKind.`
- [ ] **4.5** `DiagnosticSeverity.` → `lsp_types.DiagnosticSeverity.`
- [ ] **4.6** `InsertTextFormat.` → `lsp_types.InsertTextFormat.`
- [ ] **4.7** `MarkupKind.` → `lsp_types.MarkupKind.`

### Type Checks
- [ ] **4.8** `isinstance(link, Location)` → `isinstance(link, lsp_types.Location)`
- [ ] **4.9** `isinstance(link, LocationLink)` → `isinstance(link, lsp_types.LocationLink)`
- [ ] **4.10** `isinstance(item, MarkupContent)` → `isinstance(item, lsp_types.MarkupContent)`

### Event Types
- [ ] **4.11** `msgtype == events.Initialized` → `msgtype == lsp_types.InitializeResponse`
- [ ] **4.12** `msgtype == events.Completion` → `msgtype == lsp_types.CompletionResponse`
- [ ] **4.13** `msgtype == events.SignatureHelp` → `msgtype == lsp_types.SignatureHelpResponse`
- [ ] **4.14** `msgtype == events.Definition` → `msgtype == lsp_types.DefinitionResponse`
- [ ] **4.15** `msgtype == events.References` → `msgtype == lsp_types.ReferencesResponse`
- [ ] **4.16** `msgtype == events.Implementation` → `msgtype == lsp_types.ImplementationResponse`
- [ ] **4.17** `msgtype == events.TypeDefinition` → `msgtype == lsp_types.TypeDefinitionResponse`
- [ ] **4.18** `msgtype == events.Declaration` → `msgtype == lsp_types.DeclarationResponse`
- [ ] **4.19** `msgtype == events.PublishDiagnostics` → `msgtype == lsp_types.PublishDiagnosticsNotification`
- [ ] **4.20** `msgtype == events.LogMessage` → `msgtype == lsp_types.LogMessageNotification`
- [ ] **4.21** `msgtype == events.ShowMessage` → `msgtype == lsp_types.ShowMessageRequest`
- [ ] **4.22** `msgtype == events.Shutdown` → `msgtype == lsp_types.ShutdownResponse`

---

## 🔴 Step 5: Manual Edits in language.py

### Constants (lines 50-100)
- [ ] **5.1** Update `GOTO_EVENT_TYPES` set with `lsp_types.*Response`
- [ ] **5.2** Update `GOTO_TITLES` dict with `lsp_types.*Response` keys
- [ ] **5.3** Update `CALLABLE_COMPLETIONS` set with `lsp_types.CompletionItemKind.*`

### _on_lsp_msg method (lines 400-700)
- [ ] **5.4** `InitializeResponse`: Access `msg.result` for capabilities
- [ ] **5.5** `CompletionResponse`: Access `msg.result` (CompletionList or list)
- [ ] **5.6** `Hover`: Access `msg.contents` directly
- [ ] **5.7** `SignatureHelpResponse`: Access `msg.result`
- [ ] **5.8** `SemanticTokensResponse`: Access `msg.result.data`
- [ ] **5.9** All GOTOs: Access `msg.result` for locations
- [ ] **5.10** `DocumentSymbolResponse`: Access `msg.result`
- [ ] **5.11** `DocumentFormattingResponse`: Access `msg.result`
- [ ] **5.12** `PublishDiagnosticsNotification`: Access `msg.params.uri` and `msg.params.diagnostics`
- [ ] **5.13** `ConfigurationRequest`: Access `msg.params.items`
- [ ] **5.14** `LogMessageNotification`: Create `LogMsg(msg=params.message, type=params.type, severity=...)`
- [ ] **5.15** `ShowMessageRequest`: Same as LogMessage
- [ ] **5.16** `RegisterCapabilityRequest`: Access `msg.params`, reply with `msg._client._send_response()`
- [ ] **5.17** `WorkspaceFoldersRequest`: Reply with `msg._client._send_response()`

### _on_progress method
- [ ] **5.18** Handle `WorkDoneProgressCreateRequest`: Access `msg.params.token`
- [ ] **5.19** Handle `ProgressNotification`: Access `msg.params.value.kind`

### ServerConfig.__init__
- [ ] **5.20** Handle both `InitializeResult` object and dict:
  ```python
  if hasattr(initialized_result, 'capabilities'):
      capabilities = initialized_result.capabilities
  else:
      capabilities = initialized_result
  ```

### CompletionMan
- [ ] **5.21** `prepare_complete`: Convert lsp_types.CompletionItem to dict
- [ ] **5.22** `show_complete`: Use `lsp_types.CompletionItemKind(item['kind'])`
- [ ] **5.23** `do_complete`: Check `item.get('insertTextFormat') == lsp_types.InsertTextFormat.Snippet`

---

## 🟢 Step 6: Fix tree.py (Easy)

- [ ] **6.1** Change imports:
  ```python
  # FROM:
  from .sansio_lsp_client.structs import SymbolKind, DocumentSymbol, SymbolInformation
  # TO:
  from lsprotocol.types import SymbolKind, DocumentSymbol, SymbolInformation
  ```

---

## 🟢 Step 7: Fix lsp.py (Easy)

- [ ] **7.1** Add import at top:
  ```python
  from lsprotocol import types as lsp_types
  ```

---

## ✅ Step 8: Test Everything

### Basic Tests
- [ ] **8.1** CudaText starts without errors
- [ ] **8.2** Open a file with LSP support
- [ ] **8.3** Check console for import errors
- [ ] **8.4** LSP server initializes (check console)

### Feature Tests
- [ ] **8.5** Code completion works (Ctrl+Space)
- [ ] **8.6** Hover info works (mouse hover)
- [ ] **8.7** Signature help works (type `func(` and wait)
- [ ] **8.8** Go to definition works (Ctrl+click)
- [ ] **8.9** Find references works
- [ ] **8.10** Diagnostics appear (try syntax error)
- [ ] **8.11** Format document works
- [ ] **8.12** Code tree/outline works

### Console Check
- [ ] **8.13** No "unknown Message type" errors
- [ ] **8.14** No "cannot import" errors
- [ ] **8.15** No "AttributeError" errors

---

## 🔧 Common Issues & Fixes

### Issue: `NameError: name 'WorkspaceFolder' is not defined`
**Fix:** Search for `WorkspaceFolder(` and replace with `lsp_types.WorkspaceFolder(`

### Issue: `'CompletionResponse' object has no attribute 'completion_list'`
**Fix:** Access through `msg.result` instead

### Issue: `'LogMessageNotification' object has no attribute 'message'`
**Fix:** Access through `msg.params.message` instead

### Issue: `cannot import name 'LogMessage'`
**Fix:** Remove the import from dlg.py, use `MessageType` instead

### Issue: `'InitializeResponse' object has no attribute 'capabilities'`
**Fix:** Access through `msg.result.capabilities`

---

## 📊 Progress Tracker

**Estimated time:** 1-2 hours for careful migration

- **Easy tasks (30 min):** Steps 1, 2, 6, 7
- **Medium tasks (30 min):** Steps 3, 4  
- **Complex tasks (30-60 min):** Step 5
- **Testing (30 min):** Step 8

---

## 🎯 Success Criteria

✅ All files saved  
✅ No import errors on startup  
✅ LSP server initializes  
✅ Completion works  
✅ Hover works  
✅ No console errors during normal use  

---

## 🆘 If You Get Stuck

1. **Check artifacts:**
   - `language_py_complete_changes` - Line-by-line examples
   - `search_replace_guide` - Quick search & replace
   - `import_reference` - What imports where

2. **Verify imports:**
   ```python
   from lsprotocol import types as lsp_types
   print(dir(lsp_types))  # See what's available
   ```

3. **Test incrementally:**
   - Comment out complex code
   - Test basic startup
   - Uncomment and fix errors one by one

4. **Ask for help with:**
   - Specific error message
   - File and line number
   - Code snippet causing the error
