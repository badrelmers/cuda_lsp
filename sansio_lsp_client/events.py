import typing as t
from lsprotocol import types as lsp_types

import attrs

from .structs import (
    CallHierarchyItem,
    CompletionList,
    ConfigurationItem,
    Diagnostic,
    DocumentSymbol,
    FoldingRange,
    Id,
    InlayHint,
    JSONDict,
    Location,
    LocationLink,
    MarkedString,
    MarkupContent,
    MessageActionItem,
    MessageType,
    ProgressToken,
    Range,
    Registration,
    SignatureInformation,
    SymbolInformation,
    TextDocumentEdit,
    TextEdit,
    WorkspaceFolder,
    WorkDoneProgressBeginValue,
    WorkDoneProgressEndValue,
    WorkDoneProgressKind,
    WorkDoneProgressReportValue,
    structure,
    unstructure,
)

if t.TYPE_CHECKING:  # avoid import cycle at runtime, Only imported during type checking, not at runtime!
    from .client import Client


@attrs.define
class Event:
    pass


@attrs.define(kw_only=True)
class MethodResponse(Event):
    message_id: t.Optional[Id] = None


@attrs.define
class ResponseError(Event):
    code: int = attrs.field()
    message: str = attrs.field()
    data: t.Optional[
        t.Union[str, int, float, bool, t.List[t.Any], JSONDict, None]
    ] = attrs.field(default=None)
    message_id: t.Optional[Id] = attrs.field(default=None)


@attrs.define
class ServerRequest(Event):
    # mimic Pydantic's PrivateAttr(). 
    # Pydantic's PrivateAttr is invisible to validation, Pydantic excludes private attributes from the generated constructor and the validation logic. It only looks for "Public" fields. init=False make attrs behave like Pydantic. an alternative is to use 'from __future__ import annotations'
    # init=False tells attrs not to expect those fields in the constructor, so Converter.structure(params, WorkDoneProgressCreate) will succeed when params only contains the LSP fields (like token)
    # we need also to make it optional t.Optional["Client"] to prevent this error: NameError: name 'Client' is not defined. The error is happening because attrs is trying to resolve the forward reference "Client" at runtime (during Converter.structure), but Client isn't available since it's only imported under TYPE_CHECKING.
    _client: t.Optional["Client"] = attrs.field(init=False)
    _id: t.Optional[Id] = attrs.field(init=False)
    
    
@attrs.define
class ServerNotification(Event):
    pass


@attrs.define
class Initialized(Event):
    capabilities: JSONDict = attrs.field()


@attrs.define
class Shutdown(Event):
    pass


@attrs.define
class ShowMessage(ServerNotification):
    type: MessageType = attrs.field()
    message: str = attrs.field()


@attrs.define
class ShowMessageRequest(ServerRequest):
    type: MessageType = attrs.field()
    message: str = attrs.field()
    actions: t.Optional[t.List[MessageActionItem]] = attrs.field(default=None)

    def reply(self, action: t.Optional[MessageActionItem] = None) -> None:
        result = None if action is None else unstructure(action)
        self._client._send_response(id=self._id, result=result)


@attrs.define
class LogMessage(ServerNotification):
    type: MessageType = attrs.field()
    message: str = attrs.field()


@attrs.define
class WorkDoneProgressCreate(ServerRequest):
    token: ProgressToken = attrs.field()

    def reply(self) -> None:
        self._client._send_response(id=self._id, result=None)


@attrs.define
class Progress(ServerNotification):
    token: ProgressToken = attrs.field()
    value: t.Union[
        WorkDoneProgressBeginValue,
        WorkDoneProgressReportValue,
        WorkDoneProgressEndValue,
    ] = attrs.field()


@attrs.define
class WorkDoneProgress(Progress):
    pass


@attrs.define
class WorkDoneProgressBegin(WorkDoneProgress):
    value: WorkDoneProgressBeginValue = attrs.field()


@attrs.define
class WorkDoneProgressReport(WorkDoneProgress):
    value: WorkDoneProgressReportValue = attrs.field()


@attrs.define
class WorkDoneProgressEnd(WorkDoneProgress):
    value: WorkDoneProgressEndValue = attrs.field()


@attrs.define
class Completion(Event):
    message_id: Id = attrs.field()
    completion_list: t.Optional[t.Dict[str, t.Any]] = attrs.field(default=None)


@attrs.define
class WillSaveWaitUntilEdits(Event):
    edits: t.Optional[t.List[TextEdit]] = attrs.field(default=None)


@attrs.define
class PublishDiagnostics(ServerNotification):
    uri: str = attrs.field()
    diagnostics: t.List[Diagnostic] = attrs.field()


@attrs.define
class WorkspaceProjectInitializationComplete(ServerNotification):
    pass



@attrs.define(kw_only=True)
class SignatureHelp(MethodResponse):
    signatures: t.List[SignatureInformation] = attrs.field()
    activeSignature: t.Optional[int] = attrs.field(default=None)
    activeParameter: t.Optional[int] = attrs.field(default=None)

    def get_hint_str(self) -> t.Optional[str]:
        if len(self.signatures) == 0:
            return None
        active_sig = self.activeSignature or 0
        sig = self.signatures[active_sig]
        return sig.label

    def get_signatures(self):
        if len(self.signatures) == 0:
            return None
        return self.signatures, self.activeSignature, self.activeParameter


@attrs.define
class SemanticTokens(Event):
    data: t.List[int] = attrs.field()
    message_id: t.Optional[Id] = attrs.field(default=None)
    resultId: t.Optional[str] = attrs.field(default=None)


@attrs.define
class Definition(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None] = attrs.field(
        default=None
    )


@attrs.define
class WorkspaceEdit(MethodResponse):
    documentChanges: t.Optional[t.List[TextDocumentEdit]] = attrs.field(default=None)
    changes: t.Optional[t.Dict[str, t.List[TextEdit]]] = attrs.field(default=None)


@attrs.define(kw_only=True)
class References(MethodResponse):
    result: t.Union[t.List[Location], None] = attrs.field()


@attrs.define
class MCallHierarchItems(Event):
    result: t.Union[t.List[CallHierarchyItem], None] = attrs.field()


@attrs.define
class Implementation(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None] = attrs.field()


@attrs.define
class MWorkspaceSymbols(MethodResponse):
    result: t.Union[t.List[SymbolInformation], None] = attrs.field()


@attrs.define
class MFoldingRanges(MethodResponse):
    result: t.Optional[t.List[FoldingRange]] = attrs.field(default=None)


@attrs.define
class MInlayHints(MethodResponse):
    result: t.Optional[t.List[InlayHint]] = attrs.field(default=None)


@attrs.define
class MDocumentSymbols(MethodResponse):
    result: t.Union[t.List[SymbolInformation], t.List[DocumentSymbol], None] = attrs.field(
        default=None
    )


@attrs.define
class Declaration(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None] = attrs.field()


@attrs.define
class TypeDefinition(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None] = attrs.field()


@attrs.define
class RegisterCapabilityRequest(ServerRequest):
    registrations: t.List[Registration] = attrs.field()

    def reply(self) -> None:
        self._client._send_response(id=self._id, result={})


@attrs.define
class DocumentFormatting(MethodResponse):
    result: t.Union[t.List[TextEdit], None] = attrs.field(default=None)


@attrs.define
class WorkspaceFolders(ServerRequest):
    result: t.Optional[t.List[WorkspaceFolder]] = attrs.field(default=None)

    def reply(self, folders: t.Optional[t.List[WorkspaceFolder]] = None) -> None:
        result = None if folders is None else [unstructure(f) for f in folders]
        self._client._send_response(id=self._id, result=result)


@attrs.define
class ConfigurationRequest(ServerRequest):
    items: t.List[ConfigurationItem] = attrs.field()

    def reply(self, result: t.List[t.Any]) -> None:
        self._client._send_response(id=self._id, result=result)


@attrs.define
class Metadata(Event):
    message_id: t.Optional[Id] = attrs.field(default=None)
    result: t.Optional[JSONDict] = attrs.field(default=None)
