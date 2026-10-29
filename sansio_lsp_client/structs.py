import typing as t

import attrs

JSONDict = t.Dict[str, t.Any]
JSONList = t.List[t.Any]

Id = t.Union[int, str]

@attrs.define
class Request:
    jsonrpc: str = attrs.field(default="2.0", init=False)
    method: str
    params: t.Optional[t.Union[JSONDict, JSONList]] = None
    id: t.Optional[Id] = None
