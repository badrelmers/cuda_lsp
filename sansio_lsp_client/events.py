import typing as t

from lsprotocol import types as lsp_types

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

if t.TYPE_CHECKING:  # avoid import cycle at runtime
    from .client import Client


class Event(lsp_types.LSPTypedDict):
    pass


class MethodResponse(Event):
    message_id: t.Optional[Id] = None


class ResponseError(Event):
    message_id: t.Optional[Id] = None
    code: int
    message: str
    data: t.Optional[t.Union[str, int, float, bool, t.List[t.Any], JSONDict, None]] = None


class ServerRequest(Event):
    _client: "Client"
    _id: Id


class ServerNotification(Event):
    pass


class Initialized(Event):
    capabilities: JSONDict


class Shutdown(Event):
    pass


class ShowMessage(ServerNotification):
    type: MessageType
    message: str


class ShowMessageRequest(ServerRequest):
    type: MessageType
    message: str
    actions: t.Optional[t.List[MessageActionItem]] = None

    def reply(self, action: t.Optional[MessageActionItem] = None) -> None:
        result = None if action is None else unstructure(action)
        self._client._send_response(id=self._id, result=result)


class LogMessage(ServerNotification):
    type: MessageType
    message: str


class WorkDoneProgressCreate(ServerRequest):
    token: ProgressToken

    def reply(self) -> None:
        self._client._send_response(id=self._id, result=None)


class Progress(ServerNotification):
    token: ProgressToken
    value: t.Union[
        WorkDoneProgressBeginValue,
        WorkDoneProgressReportValue,
        WorkDoneProgressEndValue,
    ]


class WorkDoneProgress(Progress):
    pass


class WorkDoneProgressBegin(WorkDoneProgress):
    value: WorkDoneProgressBeginValue


class WorkDoneProgressReport(WorkDoneProgress):
    value: WorkDoneProgressReportValue


class WorkDoneProgressEnd(WorkDoneProgress):
    value: WorkDoneProgressEndValue


class Completion(Event):
    message_id: Id
    completion_list: t.Optional[t.Dict[str, t.Any]] = None


class WillSaveWaitUntilEdits(Event):
    edits: t.Optional[t.List[TextEdit]] = None


class PublishDiagnostics(ServerNotification):
    uri: str
    diagnostics: t.List[Diagnostic]


class WorkspaceProjectInitializationComplete(ServerNotification):
    pass


class Hover(MethodResponse):
    contents: t.Union[
        t.List[t.Union[MarkedString, str]], MarkedString, MarkupContent, str
    ]
    range: t.Optional[Range] = None

    def m_str(self) -> str:
        def item_str(item: t.Union[MarkedString, MarkupContent, str]) -> str:
            if isinstance(item, MarkedString):
                return f"[{item.language}]\n{item.value}"
            if isinstance(item, MarkupContent):
                return f"[{item.kind}]\n{item.value}"
            return item

        if isinstance(self.contents, list):
            return "\n".join(item_str(item) for item in self.contents)
        return item_str(self.contents)


class SignatureHelp(MethodResponse):
    signatures: t.List[SignatureInformation]
    activeSignature: t.Optional[int] = None
    activeParameter: t.Optional[int] = None

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


class SemanticTokens(Event):
    message_id: t.Optional[Id] = None
    resultId: t.Optional[str] = None
    data: t.List[int]


class Definition(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None] = None


class WorkspaceEdit(MethodResponse):
    changes: t.Optional[t.Dict[str, t.List[TextEdit]]] = None
    documentChanges: t.Optional[t.List[TextDocumentEdit]] = None


class References(MethodResponse):
    result: t.Union[t.List[Location], None]


class MCallHierarchItems(Event):
    result: t.Union[t.List[CallHierarchyItem], None]


class Implementation(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None]


class MWorkspaceSymbols(MethodResponse):
    result: t.Union[t.List[SymbolInformation], None]


class MFoldingRanges(MethodResponse):
    result: t.Optional[t.List[FoldingRange]] = None


class MInlayHints(MethodResponse):
    result: t.Optional[t.List[InlayHint]] = None


class MDocumentSymbols(MethodResponse):
    result: t.Union[t.List[SymbolInformation], t.List[DocumentSymbol], None] = None


class Declaration(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None]


class TypeDefinition(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None]


class RegisterCapabilityRequest(ServerRequest):
    registrations: t.List[Registration]

    def reply(self) -> None:
        self._client._send_response(id=self._id, result={})


class DocumentFormatting(MethodResponse):
    result: t.Union[t.List[TextEdit], None] = None


class WorkspaceFolders(ServerRequest):
    result: t.Optional[t.List[WorkspaceFolder]] = None

    def reply(self, folders: t.Optional[t.List[WorkspaceFolder]] = None) -> None:
        result = None if folders is None else [unstructure(f) for f in folders]
        self._client._send_response(id=self._id, result=result)


class ConfigurationRequest(ServerRequest):
    items: t.List[ConfigurationItem]

    def reply(self, result: t.List[t.Any]) -> None:
        self._client._send_response(id=self._id, result=result)


class Metadata(Event):
    message_id: t.Optional[Id] = None
    result: t.Optional[JSONDict] = None
