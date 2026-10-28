# Debugging Guide: LSP Servers Not Working

## Problem
After Pydantic removal, OmniSharp works but Python/JavaScript/C++ LSP servers don't work.

## Root Cause
The issue is likely in how we're parsing server responses. Different servers send slightly different response formats.

## Quick Fixes Applied

### 1. Hover Contents Parsing
**Fixed:** Added `_parse_hover_contents()` method to properly handle various hover formats:
- String
- MarkupContent (dict with 'kind' and 'value')
- MarkedString (dict with 'language' and 'value')
- List of any of the above

### 2. Hover.m_str() Method
**Fixed:** Updated to handle dict fallback and MarkupKind enum values properly.

## Debugging Steps

### Step 1: Enable Debug Messages
In your `lsp.py` file, set:
```python
DEBUG_MESSAGES = True
```

This will store all LSP messages in `lang._dbg_msgs`.

### Step 2: Check What's Failing
Add this debug code at the start of `_handle_response()` in client.py:

```python
def _handle_response(self, response: Response) -> Event:
    # DEBUG: Print response
    import sys
    print(f"DEBUG: method={request.method}, result type={type(response.result)}", file=sys.stderr)
    if response.error:
        print(f"DEBUG: ERROR: {response.error}", file=sys.stderr)
```

### Step 3: Check Specific Responses

Add to `language.py` in `_on_lsp_msg()`:

```python
def _on_lsp_msg(self, msg):
    # DEBUG: Log message types
    print(f"DEBUG: Received message type: {type(msg).__name__}")
    if hasattr(msg, 'result'):
        print(f"DEBUG: Result: {msg.result}")
```

## Common Issues and Fixes

### Issue 1: "NoneType has no attribute X"
**Cause:** Response.result is None but we're trying to access fields
**Fix:** Always check `if response.result is not None` before accessing

### Issue 2: "Expected X but got dict"
**Cause:** We're keeping raw dicts instead of parsing to objects
**Fix:** This is usually intentional - check if the consuming code expects dicts

### Issue 3: "KeyError: 'someField'"
**Cause:** Server didn't send expected field
**Fix:** Use `.get('field', default)` instead of `['field']`

## Server-Specific Debugging

### Python LSP (Jedi/Pylsp)
**Common issues:**
- Completion items might be in different format
- Diagnostics might have additional fields

**Test:**
```python
# Open Python file and trigger completion
# Check console for errors
```

### JavaScript/TypeScript LSP
**Common issues:**
- Location links vs Location
- Complex completion item structures

**Test:**
```javascript
// Open JS file and trigger completion
console.log("test");
```

### C++ LSP (clangd)
**Common issues:**
- Semantic tokens format differences
- Diagnostics with related information

**Test:**
```cpp
// Open C++ file
#include <iostream>
int main() {}
```

## Systematic Fix Process

### 1. Identify Failing Method
Run the server and note which LSP method fails. Example:
```
ERROR in _handle_response: method=textDocument/completion
```

### 2. Check Response Format
Add debug print before the failing section:
```python
elif method == "textDocument/completion":
    print(f"DEBUG completion result: {response.result}")
    # ... rest of code
```

### 3. Compare with Spec
Check LSP specification: https://microsoft.github.io/language-server-protocol/specifications/specification-current/

### 4. Add Proper Parsing
Based on what the server actually sends, parse appropriately.

## Quick Patch for Common Responses

### Completion
```python
elif method == "textDocument/completion":
    completion_list = None
    
    if response.result is None:
        completion_list = {'isIncomplete': False, 'items': []}
    elif isinstance(response.result, dict):
        completion_list = response.result
    elif isinstance(response.result, list):
        completion_list = {
            'isIncomplete': False,
            'items': response.result,
        }
    
    event = Completion(
        message_id=response.id,
        completion_list=completion_list
    )
```

### SignatureHelp
```python
elif method == "textDocument/signatureHelp":
    if response.result is not None and isinstance(response.result, dict):
        sigs = []
        for s in response.result.get('signatures', []):
            try:
                sigs.append(parse_signature_information(s))
            except Exception as e:
                print(f"DEBUG: Failed to parse signature: {e}")
                # Fallback: create minimal signature
                from .structs import SignatureInformation
                sigs.append(SignatureInformation(label=s.get('label', 'unknown')))
        
        event = SignatureHelp(
            signatures=sigs,
            activeSignature=response.result.get('activeSignature'),
            activeParameter=response.result.get('activeParameter')
        )
    else:
        event = SignatureHelp(signatures=[])
    event.message_id = response.id
```

### Definition/References
```python
elif method == "textDocument/definition":
    try:
        result = parse_location_or_link_list(response.result)
    except Exception as e:
        print(f"DEBUG: Failed to parse definition: {e}")
        result = None
    event = Definition(result=result)
    event.message_id = response.id
```

## Emergency Rollback for Specific Method

If one method is completely broken, you can temporarily disable it:

```python
elif method == "textDocument/problematicMethod":
    print(f"WARNING: {method} temporarily disabled")
    # Return empty/null event
    event = SomeEvent(result=None)
    event.message_id = response.id
```

## Testing Checklist

For each server, test:
- [ ] Server starts (check console)
- [ ] Completion triggers (Ctrl+Space)
- [ ] Completion items display
- [ ] Hover shows (mouse hover or explicit call)
- [ ] Diagnostics appear (introduce error)
- [ ] Go to definition works
- [ ] Find references works (if supported)

## Getting More Info

### Check Server Output
In `language.py`, the `_err_read_loop()` captures server stderr. Check the log panel.

### Check Sent Requests
Add to `_send_request()`:
```python
def _send_request(self, method: str, params: Optional[JSONDict] = None) -> Id:
    print(f"DEBUG: Sending {method}")
    # ... rest of code
```

### Check Received Responses
Already added in Step 2 above.

## Likely Culprits by Server

### Python (Jedi-language-server or pylsp)
**Most likely issue:** Completion items format
**Check:** `textDocument/completion` response parsing

### JavaScript/TypeScript
**Most likely issue:** Location vs LocationLink in goto methods
**Check:** `textDocument/definition` response parsing

### C++ (clangd)
**Most likely issue:** Diagnostics with relatedInformation
**Check:** `textDocument/publishDiagnostics` request parsing

## Report Template

If you find an issue, report with:
```
Server: [Python/JavaScript/C++/etc]
Method: [textDocument/completion/etc]
Error: [exact error message]
Response.result type: [dict/list/None]
Response.result content: [first few lines]
```

## Next Steps

1. Apply the hover fix (already in updated client.py)
2. Test each server one by one
3. When one fails, follow debugging steps above
4. Add error handling / parsing for that specific case
5. Repeat until all work

The key is: **we're not changing the protocol, just parsing responses correctly**.
