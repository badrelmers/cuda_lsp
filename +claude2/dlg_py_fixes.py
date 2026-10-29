# Fix for dlg.py - line ~397 in __init__ method

# REMOVE this import (line ~397):
# from lsprotocol.types import LogMessage, ShowMessage

# REPLACE with:
from lsprotocol.types import (
    MessageType,  # This is what we actually need
    MarkupKind,   # Keep this
)

# The PanelLog class doesn't need LogMessage/ShowMessage classes
# It only needs MessageType enum for severity mapping

# In PanelLog.__init__, the global import statement should look like:
def __init__(self, panel_name, state=None):
    # NO IMPORT HERE - MessageType is already imported at top
    
    PanelLog.panels[panel_name] = self
    
    # Remove this line completely:
    # from lsprotocol.types import LogMessage, ShowMessage
    
    # The type_captions dict is not needed anymore since we're using
    # a different approach. Just remove these lines:
    # PanelLog.type_captions = {
    #     ShowMessage: TYPE_MSG,
    #     LogMessage: TYPE_LOG,
    # }
    
    self.name = panel_name
    # ... rest of __init__ continues as before
