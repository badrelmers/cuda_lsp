# Immediate Fix for ImportError

## Your Error
```
ImportError: cannot import name 'LogMessage' from 'lsprotocol.types'
```

**Location**: `dlg.py` line ~397, in `PanelLog.__init__`

---

## Step-by-Step Fix

### Step 1: Open `dlg.py`

### Step 2: Find and Remove Bad Import (around line 397)

**Find this code** in `PanelLog.__init__` method:
```python
def __init__(self, panel_name, state=None):
    global LogMessage, ShowMessage
    from .sansio_lsp_client import LogMessage, ShowMessage
    # OR
    from lsprotocol.types import LogMessage, ShowMessage  # <-- THIS LINE IS THE PROBLEM
```

**Delete these lines** completely. The entire `from ... import LogMessage, ShowMessage` statement.

### Step 3: Update Imports at Top of dlg.py (around line 1-20)

**Find the imports section at the very top:**
```python
from cudatext import *
import cudax_lib as apx
import cudatext_cmd as cmds
```

**Add these imports** (if not already there):
```python
from lsprotocol.types import MarkupKind, MessageType
```

**Remove any old imports** like:
```python
# DELETE THESE if they exist:
from .sansio_lsp_client.structs import MarkupKind  # OLD
from .sansio_lsp_client import LogMessage, ShowMessage  # OLD
```

### Step 4: Remove type_captions Dictionary

**Find this in `PanelLog.__init__`** (still around line 397-405):
```python
PanelLog.type_captions = {
    ShowMessage: TYPE_MSG,
    LogMessage: TYPE_LOG,
}
```

**Delete or comment out** these lines completely. They're not needed anymore.

### Step 5: Update `log()` Method (around line 550)

**Find the `log()` method:**
```python
def log(self, msg):   # events: ShowMessage, LogMessage
```

**Replace it with:**
```python
def log(self, msg):
    """Logs a message. msg should be LogMsg namedtuple with (msg, type, severity)"""
    if isinstance(msg, LogMsg):
        # msg is LogMsg(msg=text, type=MessageType, severity=SEVERITY_*)
        self.log_str(msg.msg, type_=msg.type, severity=msg.severity, scroll=True)
    else:
        # Fallback for unexpected types
        severity_str = SEVERITY_MAP.get(getattr(msg, 'type', 4), SEVERITY_LOG) if hasattr(msg, 'type') else SEVERITY_LOG
        message_text = getattr(msg, 'message', str(msg))
        self.log_str(message_text, type_=type(msg), severity=severity_str, scroll=True)
```

---

## Verification

After making these changes, restart CudaText. The error should be gone.

If you still get errors, check:

1. ✅ `dlg.py` line ~397: No `import LogMessage` or `import ShowMessage`
2. ✅ `dlg.py` top: Has `from lsprotocol.types import MarkupKind, MessageType`
3. ✅ `dlg.py` PanelLog.__init__: No `type_captions` dictionary
4. ✅ `language.py`: Imports `LogMsg` from `.dlg`

---

## Next Error You Might See

If you now get an error like:
```
AttributeError: 'LogMessageNotification' object has no attribute 'message'
```

This means `language.py` needs updating. See artifact `language_py_logmsg_fix` for the solution.

The pattern is:
```python
# In language.py _on_lsp_msg:
elif msgtype == lsp_types.LogMessageNotification:
    params = msg.params  # Access through params!
    log_msg = LogMsg(
        msg=params.message,    # params.message, not msg.message
        type=params.type,       # MessageType enum
        severity=SEVERITY_MAP.get(params.type.value, SEVERITY_LOG)
    )
    self.plog.log(log_msg)
```

---

## Quick Test

After the fix, open CudaText console and run:
```python
from lsprotocol.types import MessageType
print(MessageType.Error)  # Should print: MessageType.Error
```

If this works, your imports are correct! ✅
