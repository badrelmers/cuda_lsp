# Complete Pydantic Removal Migration Guide

## Overview
This guide covers removing Pydantic 2 dependency from cuda_lsp plugin to support Python 3.8-3.14+.

## Files Modified

### sansio-lsp-client files (in lsp_modules/sansio_lsp_client/):
1. ✅ **structs.py** - Converted to dataclasses
2. ✅ **events.py** - Converted to dataclasses  
3. ✅ **io_handler.py** - Removed TypeAdapter
4. ⚠️ **client.py** - Needs manual updates (see below)
5. ✅ **_parse_helpers.py** - NEW utility module

### CudaText plugin files (minimal changes):
- **util.py** - May need ValidationError handling
- **language.py** - Should work as-is (uses dicts mostly)
- **book.py** - Should work as-is
- Other files - No changes needed

---

## Step 1: Replace sansio-lsp-client Files

Replace these 4 files in your `lsp_modules/sansio_lsp_client/` directory:

1. `structs.py` → Use converted version
2. `events.py` → Use converted version
3. `io_handler.py` → Use converted version
4. **NEW** `_parse_helpers.py` → Add this new file

---

## Step 2: Update client.py

The `client.py` file is complex and needs careful manual updates. Here's a systematic approach:

### A. Update Imports

```python
# REMOVE these lines:
from pydantic import ValidationError, TypeAdapter

# ADD these lines:
from ._parse_helpers import (
    parse_signature_information,
    parse_text_edit, parse_text_edits_list,
    parse_location_or_link_list,
    parse_diagnostic,
    parse_call_hierarchy_item,
    parse_markup_content,
)
```

### B. Key Method Updates

#### In `_handle_response()` method:

**1. Initialized (line ~280)**
```python
# OLD:
event = Initialized.model_validate(response.result)

# NEW:
event = Initialized.from_dict(response.result)
```

**2. ResponseError (line ~270)**
```python
# OLD:
err = ResponseError.model_validate(response.error)

# NEW:
err = ResponseError(
    code=response.error.get('code', 0),
    message=response.error.get('message', ''),
    data=response.error.get('data')
)
```

**3. Completion (lines ~290-310)**
```python
# OLD:
# Complex Pydantic parsing with ValidationError handling

# NEW:
event = Completion(
    message_id=response.id,
    completion_list=completion_list  # Keep as dict
)
```

**4. WillSaveWaitUntilEdits (line ~315)**
```python
# OLD:
event = WillSaveWaitUntilEdits(
    edits=TypeAdapter(List[TextEdit]).validate_python(response.result)
)

# NEW:
edits = parse_text_edits_list(response.result)
event = WillSaveWaitUntilEdits(edits=edits)
```

**5. Hover (lines ~320-330)**
```python
# OLD:
if response.result is not None:
    event = Hover.model_validate(response.result)
else:
    event = Hover(contents=[])

# NEW:
if response.result is not None:
    contents = response.result.get('contents', [])
    range_data = response.result.get('range')
    from ._parse_helpers import parse_range
    range_obj = parse_range(range_data) if range_data else None
    event = Hover(contents=contents, range=range_obj)
else:
    event = Hover(contents=[])
```

**6. SignatureHelp (lines ~340-350)**
```python
# OLD:
if response.result is not None:
    event = SignatureHelp.model_validate(response.result)
else:
    event = SignatureHelp(signatures=[])

# NEW:
if response.result is not None:
    sigs = [parse_signature_information(s) 
            for s in response.result.get('signatures', [])]
    event = SignatureHelp(
        signatures=sigs,
        activeSignature=response.result.get('activeSignature'),
        activeParameter=response.result.get('activeParameter')
    )
else:
    event = SignatureHelp(signatures=[])
```

**7. SemanticTokens (line ~380)**
```python
# OLD:
event = SemanticTokens.model_validate(response.result)

# NEW:
event = SemanticTokens(
    data=response.result.get('data', []),
    resultId=response.result.get('resultId')
)
```

**8. Definition/References/Implementation/etc (lines ~390-430)**
```python
# OLD:
event = TypeAdapter(Definition).validate_python({"result": response.result})

# NEW:
event = Definition(result=parse_location_or_link_list(response.result))
```

Apply same pattern for: References, Implementation, Declaration, TypeDefinition

**9. TextDocumentEdit parsing (lines ~360-370)**
```python
# OLD:
document_changes = [
    TextDocumentEdit.model_validate(change)
    for change in response.result["documentChanges"]
]

# NEW:
from ._parse_helpers import parse_text_edit
document_changes = []
for change in response.result["documentChanges"]:
    from .structs import OptionalVersionedTextDocumentIdentifier
    text_doc = OptionalVersionedTextDocumentIdentifier(**change['textDocument'])
    edits = [parse_text_edit(e) for e in change['edits']]
    document_changes.append(TextDocumentEdit(textDocument=text_doc, edits=edits))
```

#### In `_handle_request()` method:

**1. Parse request helper (lines ~440-460)**
```python
def parse_request(event_cls):
    if issubclass(event_cls, ServerRequest):
        # Parse params dict into event object
        event = event_cls(**request.params) if request.params else event_cls()
        event._id = request.id
        event._client = self
        return event
    elif issubclass(event_cls, ServerNotification):
        params = request.params if isinstance(request.params, dict) else {}
        return event_cls(**params) if params else event_cls()
    else:
        raise TypeError("Must be ServerRequest or ServerNotification")
```

**2. PublishDiagnostics (line ~530)**
```python
# OLD:
event = parse_request(PublishDiagnostics)

# NEW:  
diagnostics = [parse_diagnostic(d) for d in request.params.get('diagnostics', [])]
event = PublishDiagnostics(
    uri=request.params['uri'],
    diagnostics=diagnostics
)
```

### C. Update model_dump() calls

Replace all `.model_dump()` with `.to_dict()`:

```python
# OLD:
params={"textDocument": text_document.model_dump()}

# NEW:
params={"textDocument": text_document.to_dict()}
```

Search for: `\.model_dump\(`
Replace with: `.to_dict(`

---

## Step 3: Update util.py (if needed)

If `util.py` uses ValidationError:

```python
# At top of file:
class ValidationError(Exception):
    """Simple validation error for LSP protocol parsing."""
    pass
```

---

## Step 4: Testing Checklist

Test each feature systematically:

### Basic functionality:
- [ ] Plugin loads without errors
- [ ] Language servers start correctly
- [ ] Documents open and close

### Completion:
- [ ] Ctrl+Space shows completions
- [ ] Completion items display correctly
- [ ] Selecting completion inserts text
- [ ] Snippets work (if enabled)

### Navigation:
- [ ] Go to Definition (Ctrl+Click)
- [ ] Find References
- [ ] Go to Implementation
- [ ] Go to Declaration
- [ ] Go to Type Definition

### Information:
- [ ] Hover shows documentation
- [ ] Signature help works
- [ ] Diagnostics display
- [ ] Document symbols (code tree)

### Editing:
- [ ] Document formatting
- [ ] Range formatting
- [ ] Rename symbol (if supported)

### Edge cases:
- [ ] Empty/null responses handled
- [ ] Malformed responses don't crash
- [ ] Multiple language servers work
- [ ] Session save/restore works

---

## Step 5: Performance Validation

The converted code should be:
- ✅ **Faster** - No Pydantic overhead
- ✅ **Smaller memory footprint** - Simple dataclasses
- ✅ **Same functionality** - All LSP features work

If you see performance issues, check for:
- Unnecessary deep copying
- Missing dict caching
- Over-parsing (parse only when needed)

---

## Troubleshooting Common Issues

### Issue: AttributeError on dataclass field
**Cause:** Forgot to handle optional fields
**Fix:** Check for None before accessing: `if obj.field is not None:`

### Issue: TypeError on dict access
**Cause:** Expected object but got dict
**Fix:** Keep as dict or parse explicitly

### Issue: Missing method `to_dict()`
**Cause:** Not all dataclasses have it
**Fix:** Add method or use `asdict()` from dataclasses module

### Issue: Completion shows raw dicts
**Cause:** CompletionMan expects dict items
**Fix:** This is intentional - CompletionMan works with dicts

---

## Rollback Plan

If issues arise:
1. Keep original files backed up
2. Test one feature at a time
3. Can mix old/new: Keep structs as Pydantic, just update parsing logic
4. Incremental migration: Start with events.py, then structs.py, then client.py

---

## Benefits Achieved

After migration:
✅ Python 3.8 compatibility (Pydantic v1 support)
✅ Python 3.14+ compatibility (no Pydantic v1)
✅ Faster performance (no validation overhead)
✅ Smaller dependency tree
✅ Easier debugging (simpler code)
✅ Better maintainability

---

## Need Help?

If you encounter issues:
1. Check that all imports are updated
2. Verify dataclass fields match old Pydantic fields
3. Ensure Optional fields default to None
4. Test with simple language server first (e.g., Python)
5. Add print statements to debug parsing
