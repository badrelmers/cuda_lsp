# client.py Conversion Guide

Due to the file's length, here are the key changes needed for `client.py`:

## Main Changes Required

### 1. Remove Pydantic Imports
```python
# OLD:
from pydantic import ValidationError, TypeAdapter

# NEW:
# Remove these imports entirely
```

### 2. Replace model_validate() Calls

**Pattern 1: Simple validation**
```python
# OLD:
event = Initialized.model_validate(response.result)

# NEW:
event = Initialized.from_dict(response.result)
```

**Pattern 2: Error handling**
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

### 3. Replace TypeAdapter Usage

**Pattern 1: List parsing**
```python
# OLD:
list_adapter = TypeAdapter(List[CompletionItem])
items = list_adapter.validate_python(response.result)

# NEW:
items = response.result  # Already a list of dicts
```

**Pattern 2: Union type parsing**
```python
# OLD:
event = TypeAdapter(Definition).validate_python({"result": response.result})

# NEW:
event = Definition(result=response.result)
```

**Pattern 3: Complex object parsing**
```python
# OLD:
event = TypeAdapter(MInlayHints).validate_python(response)

# NEW:  
event = MInlayHints(result=response.result if response.result else None)
```

### 4. Replace model_dump() Calls

```python
# OLD:
self._send_notification("initialized", params={})
self._send_notification("workspace/didChangeConfiguration", params={
    "settings": self.settings
})

# NEW: (same - params are already dicts)
```

For WorkspaceFolder:
```python
# OLD:
"workspaceFolders": (
    None if workspace_folders is None 
    else [f.model_dump() for f in workspace_folders]
)

# NEW:
"workspaceFolders": (
    None if workspace_folders is None 
    else [f.to_dict() for f in workspace_folders]
)
```

### 5. Key Sections to Update in client.py

1. **Lines with `model_validate`**: ~25 occurrences
2. **Lines with `TypeAdapter`**: ~15 occurrences  
3. **Lines with `model_dump`**: ~10 occurrences
4. **Import of `ValidationError`**: Remove try/except or create simple exception

### 6. Helper Functions to Add

```python
def _parse_hover(data: dict) -> Hover:
    """Parse hover response from dict."""
    if not data:
        return Hover(contents=[])
    
    contents = data.get('contents', [])
    range_data = data.get('range')
    range_obj = Range.from_dict(range_data) if range_data else None
    
    return Hover(contents=contents, range=range_obj)

def _parse_signature_help(data: dict) -> SignatureHelp:
    """Parse signature help from dict."""
    if not data:
        return SignatureHelp(signatures=[])
    
    # Parse SignatureInformation objects
    sigs = []
    for sig_dict in data.get('signatures', []):
        sig = SignatureInformation(
            label=sig_dict['label'],
            documentation=sig_dict.get('documentation'),
            parameters=sig_dict.get('parameters'),
            activeParameter=sig_dict.get('activeParameter')
        )
        sigs.append(sig)
    
    return SignatureHelp(
        signatures=sigs,
        activeSignature=data.get('activeSignature'),
        activeParameter=data.get('activeParameter')
    )
```

## Complete Replacement Strategy

The safest approach:
1. Keep response.result/response.error as raw dicts/lists
2. Only parse when you need strong typing
3. For most cases, pass dicts directly to CudaText code
4. Add parsing helpers only where type safety is critical

## Testing Checklist

- [ ] Initialization handshake works
- [ ] Completion returns items
- [ ] Hover shows content
- [ ] Diagnostics display correctly
- [ ] Go to definition works
- [ ] Document symbols work
- [ ] Semantic tokens work (if used)
