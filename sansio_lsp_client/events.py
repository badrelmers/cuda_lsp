import typing as t
import attrs
from .structs import Id, JSONDict

# Only keep custom events that don't exist in lsprotocol

@attrs.define
class ResponseError:
    """Custom error response"""
    code: int = attrs.field()
    message: str = attrs.field()
    data: t.Optional[t.Union[str, int, float, bool, t.List[t.Any], JSONDict, None]] = attrs.field(default=None)
    message_id: t.Optional[Id] = attrs.field(default=None)


@attrs.define
class Metadata:
    """Custom OmniSharp metadata response"""
    message_id: t.Optional[Id] = attrs.field(default=None)
    result: t.Optional[JSONDict] = attrs.field(default=None)


# Markers for server requests/notifications - not needed anymore but kept for compatibility
class ServerRequest:
    pass

class ServerNotification:
    pass
