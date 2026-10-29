import typing as t
import attrs
from lsprotocol import converters

JSONDict = t.Dict[str, t.Any]
JSONList = t.List[t.Any]
Id = t.Union[int, str]

Converter = converters.get_converter()

@attrs.define
class Request:
    jsonrpc: str = attrs.field(default="2.0", init=False)
    method: str
    params: t.Optional[t.Union[JSONDict, JSONList]] = None
    id: t.Optional[Id] = None


@attrs.define
class Response:
    jsonrpc: str = attrs.field(default="2.0", init=False)
    id: t.Optional[Id]
    result: t.Optional[t.Union[JSONDict, JSONList]] = None
    error: t.Optional[JSONDict] = None


def unstructure(obj: t.Any) -> t.Any:
    return Converter.unstructure(obj)


def structure(data: t.Any, typ: t.Type[t.Any]) -> t.Any:
    return Converter.structure(data, typ)
