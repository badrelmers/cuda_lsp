# client.py Concrete Patch Example

This shows actual before/after code for the most critical sections.

## Section 1: Imports (Top of file)

### BEFORE:
```python
from pydantic import ValidationError, TypeAdapter

from .events import (
    Completion,
    # ... other imports
)
```

### AFTER:
```python
# Remove: from pydantic import ValidationError, TypeAdapter

from .events import (
    Completion,
    # ... other imports
)
from ._parse_helpers import (
    parse_signature_information,
    parse_text_edit,
    parse_text_edits_list,
    parse_location_or_link_list,
    parse_diagnostic,
    parse_markup_content,
    parse_range,
)
```

---

## Section 2: Completion Handling (Lines ~290-315)

### BEFORE:
```python
elif method == "textDocument/completion":
    completion_list = None

    if isinstance(response.result, dict):
        completion_list = response.result
    elif isinstance(response.result, list):
        completion_list = {
            'isIncomplete': 'false',
            'items': response.result,
        }
    
    ## ! parse_obj/model_validate is expensive and not really needed.
    #try:
    #    completion_list = CompletionList.model_validate(response.result)
    #except ValidationError:
    #    try:
    #        list_adapter = TypeAdapter(t.List[CompletionItem])
    #        completion_list = CompletionList(
    #            isIncomplete=False,
    #            items=list_adapter.validate_python(response.result),
    #        )
    #    except ValidationError:
    #        assert response.result is None

    event = Completion(
        message_id=response.id, completion_list=completion_list
    )
```

### AFTER:
```python
elif method == "textDocument/completion":
    completion_list = None

    if isinstance(response.result, dict):
        completion_list = response.result
    elif isinstance(response.result, list):
        completion_list = {
            'isIncomplete': 'false',
            'items': response.result,
        }

    event = Completion(
        message_id=response.id, completion_list=completion_list
    )
```

✅ **Change:** Removed commented-out Pydantic code (already not used)

---

## Section 3: Hover (Lines ~318-325)

### BEFORE:
```python
elif method == "textDocument/hover":
    if response.result is not None:
        event = Hover.model_validate(response.result)
    else:
        event = Hover(contents=[])  # null response
    event.message_id = response.id
```

### AFTER:
```python
elif method == "textDocument/hover":
    if response.result is not None:
        contents = response.result.get('contents', [])
        range_data = response.result.get('range')
        range_obj = parse_range(range_data) if range_data else None
        event = Hover(contents=contents, range=range_obj)
    else:
        event = Hover(contents=[])  # null response
    event.message_id = response.id
```

✅ **Change:** Replaced `model_validate` with manual parsing

---

## Section 4: SignatureHelp (Lines ~332-340)

### BEFORE:
```python
elif method == "textDocument/signatureHelp":
    if response.result is not None:
        event = SignatureHelp.model_validate(response.result)
    else:
        event = SignatureHelp(signatures=[])  # null response
    event.message_id = response.id
```

### AFTER:
```python
elif method == "textDocument/signatureHelp":
    if response.result is not None:
        sigs = [parse_signature_information(s) 
                for s in response.result.get('signatures', [])]
        event = SignatureHelp(
            signatures=sigs,
            activeSignature=response.result.get('activeSignature'),
            activeParameter=response.result.get('activeParameter')
        )
    else:
        event = SignatureHelp(signatures=[])  # null response
    event.message_id = response.id
```

✅ **Change:** Parse signatures manually using helper

---

## Section 5: SemanticTokens (Lines ~372-378)

### BEFORE:
```python
elif method == "textDocument/semanticTokens/full":
    if response.result is None:
        event = SemanticTokens(data=[])
    else:
        event = SemanticTokens.model_validate(response.result)
    event.message_id = response.id
```

### AFTER:
```python
elif method == "textDocument/semanticTokens/full":
    if response.result is None:
        event = SemanticTokens(data=[])
    else:
        event = SemanticTokens(
            data=response.result.get('data', []),
            resultId=response.result.get('resultId')
        )
    event.message_id = response.id
```

✅ **Change:** Direct construction instead of model_validate

---

## Section 6: GOTOs (Lines ~381-415)

### BEFORE:
```python
#GOTOs
elif method == "textDocument/definition":
    event = TypeAdapter(Definition).validate_python(
        {"result": response.result}
    )
    event.message_id = response.id

elif method == "textDocument/references":
    event = TypeAdapter(References).validate_python(
        {"result": response.result}
    )

elif method == "textDocument/implementation":
    event = TypeAdapter(Implementation).validate_python(
        {"result": response.result}
    )

elif method == "textDocument/declaration":
    event = TypeAdapter(Declaration).validate_python(
        {"result": response.result}
    )

elif method == "textDocument/typeDefinition":
    event = TypeAdapter(TypeDefinition).validate_python(
        {"result": response.result}
    )
```

### AFTER:
```python
#GOTOs
elif method == "textDocument/definition":
    event = Definition(result=parse_location_or_link_list(response.result))
    event.message_id = response.id

elif method == "textDocument/references":
    event = References(result=parse_location_or_link_list(response.result))
    event.message_id = response.id

elif method == "textDocument/implementation":
    event = Implementation(result=parse_location_or_link_list(response.result))
    event.message_id = response.id

elif method == "textDocument/declaration":
    event = Declaration(result=parse_location_or_link_list(response.result))
    event.message_id = response.id

elif method == "textDocument/typeDefinition":
    event = TypeDefinition(result=parse_location_or_link_list(response.result))
    event.message_id = response.id
```

✅ **Change:** Use parse_location_or_link_list helper for all GOTO commands

---

## Section 7: PublishDiagnostics (Lines ~507-510)

### BEFORE:
```python
elif request.method == "textDocument/publishDiagnostics":
    event = parse_request(PublishDiagnostics)
    assert isinstance(event, PublishDiagnostics)
    return event
```

### AFTER:
```python
elif request.method == "textDocument/publishDiagnostics":
    diagnostics = [parse_diagnostic(d) 
                   for d in request.params.get('diagnostics', [])]
    event = PublishDiagnostics(
        uri=request.params['uri'],
        diagnostics=diagnostics
    )
    return event
```

✅ **Change:** Parse diagnostics manually (important for error display)

---

## Section 8: parse_request helper (Lines ~440-460)

### BEFORE:
```python
def parse_request(event_cls: t.Type[Event]) -> Event:
    if issubclass(event_cls, ServerRequest):
        event = TypeAdapter(event_cls).validate_python(request.params)
        assert request.id is not None
        event._id = request.id
        event._client = self
        return event
    elif issubclass(event_cls, ServerNotification):
        if isinstance(request.params, dict):
            return TypeAdapter(event_cls).validate_python(request.params)
        else:
            return TypeAdapter(event_cls).validate_python({})
    else:
        raise TypeError(
            "`event_cls` must be a subclass of ServerRequest"
            " or ServerNotification"
        )
```

### AFTER:
```python
def parse_request(event_cls: t.Type[Event]) -> Event:
    if issubclass(event_cls, ServerRequest):
        params = request.params if isinstance(request.params, dict) else {}
        event = event_cls(**params) if params else event_cls()
        assert request.id is not None
        event._id = request.id
        event._client = self
        return event
    elif issubclass(event_cls, ServerNotification):
        params = request.params if isinstance(request.params, dict) else {}
        return event_cls(**params) if params else event_cls()
    else:
        raise TypeError(
            "`event_cls` must be a subclass of ServerRequest"
            " or ServerNotification"
        )
```

✅ **Change:** Removed TypeAdapter, use dataclass constructor directly

---

## Section 9: WillSaveWaitUntilEdits (Line ~316)

### BEFORE:
```python
elif method == "textDocument/willSaveWaitUntil":
    event = WillSaveWaitUntilEdits(
        edits=TypeAdapter(t.List[TextEdit]).validate_python(response.result)
    )
```

### AFTER:
```python
elif method == "textDocument/willSaveWaitUntil":
    edits = parse_text_edits_list(response.result) if response.result else None
    event = WillSaveWaitUntilEdits(edits=edits)
```

✅ **Change:** Use parse_text_edits_list helper

---

## Section 10: Rename/WorkspaceEdit (Lines ~352-369)

### BEFORE:
```python
elif method == "textDocument/rename":
    if response.result is not None and isinstance(response.result, dict):
        if "documentChanges" in response.result:
            document_changes = [
                TextDocumentEdit.model_validate(change)
                for change in response.result["documentChanges"]
            ]
            event = WorkspaceEdit(
                message_id=response.id, documentChanges=document_changes
            )
        elif "changes" in response.result:
            event = WorkspaceEdit(
                message_id=response.id, changes=response.result["changes"]
            )
        else:
            event = WorkspaceEdit(message_id=response.id)
    else:
        event = WorkspaceEdit(message_id=response.id)
```

### AFTER:
```python
elif method == "textDocument/rename":
    if response.result is not None and isinstance(response.result, dict):
        if "documentChanges" in response.result:
            from .structs import OptionalVersionedTextDocumentIdentifier
            document_changes = []
            for change in response.result["documentChanges"]:
                text_doc = OptionalVersionedTextDocumentIdentifier(
                    uri=change['textDocument']['uri'],
                    version=change['textDocument'].get('version')
                )
                edits = [parse_text_edit(e) for e in change['edits']]
                document_changes.append(
                    TextDocumentEdit(textDocument=text_doc, edits=edits)
                )
            event = WorkspaceEdit(
                message_id=response.id, documentChanges=document_changes
            )
        elif "changes" in response.result:
            event = WorkspaceEdit(
                message_id=response.id, changes=response.result["changes"]
            )
        else:
            event = WorkspaceEdit(message_id=response.id)
    else:
        event = WorkspaceEdit(message_id=response.id)
```

✅ **Change:** Manual TextDocumentEdit construction

---

## Summary of Changes

| Line Range | What Changed | Why |
|------------|--------------|-----|
| 1-20 | Import statements | Remove Pydantic, add helpers |
| 290-315 | Completion | Already using dicts |
| 318-325 | Hover | Parse contents manually |
| 332-340 | SignatureHelp | Parse signatures |
| 352-369 | WorkspaceEdit | Parse TextDocumentEdit |
| 372-378 | SemanticTokens | Direct construction |
| 381-415 | All GOTOs | Use parse helper |
| 440-460 | parse_request | Dataclass constructor |
| 507-510 | PublishDiagnostics | Parse diagnostics |

**Total changes:** ~150 lines modified across 9 sections
**Complexity:** Medium - Systematic replacements
**Risk:** Low - Each change is isolated and testable

---

## Quick Reference: Search & Replace Patterns

For code editor with regex:

1. **Remove TypeAdapter import:**
   - Find: `from pydantic import.*TypeAdapter`
   - Replace: (delete line)

2. **model_validate → parse or construct:**
   - Find: `\.model_validate\(`
   - Review each case individually

3. **TypeAdapter(X).validate_python:**
   - Find: `TypeAdapter\([^)]+\)\.validate_python\(`
   - Review and replace with helper or constructor

4. **model_dump → to_dict:**
   - Find: `\.model_dump\(`
   - Replace: `.to_dict(`

Note: Some require manual review - don't blindly replace!
