import typing as t

import attrs

from .attr_model import AttrsModel

if t.TYPE_CHECKING:  # avoid import cycle at runtime
    from .client import Client
from .structs import (
    FoldingRange,
    InlayHint,
    JSONDict,
    Diagnostic,
    MessageType,
    MessageActionItem,
    CompletionList,
    TextEdit,
    TextDocumentEdit,
    MarkupContent,
    Range,
    Location,
    MarkedString,
    SignatureInformation,
    LocationLink,
    CallHierarchyItem,
    SymbolInformation,
    Registration,
    DocumentSymbol,
    WorkspaceFolder,
    ProgressToken,
    WorkDoneProgressBeginValue,
    WorkDoneProgressReportValue,
    WorkDoneProgressEndValue,
    ConfigurationItem,
)

Id = t.Union[int, str]


@attrs.define(slots=True)
class Event(AttrsModel):
    pass


@attrs.define(slots=True)
class MethodResponse(Event):
    message_id: t.Optional[Id] = None


@attrs.define(slots=True)
class ResponseError(Event):
    message_id: t.Optional[Id] = None
    code: int = attrs.field()
    message: str = attrs.field()
    data: t.Optional[t.Union[str, int, float, bool, t.List[t.Any], JSONDict, None]] = None


@attrs.define(slots=True)
class ServerRequest(Event):
    _client: "Client" = attrs.field(default=None, init=False, repr=False, metadata={"private": True})
    _id: Id = attrs.field(default=None, init=False, repr=False, metadata={"private": True})


@attrs.define(slots=True)
class ServerNotification(Event):
    pass


@attrs.define(slots=True)
class Initialized(Event):
    capabilities: JSONDict


@attrs.define(slots=True)
class Shutdown(Event):
    pass


@attrs.define(slots=True)
class ShowMessage(ServerNotification):
    type: MessageType
    message: str


@attrs.define(slots=True)
class ShowMessageRequest(ServerRequest):
    type: MessageType
    message: str
    actions: t.Optional[t.List[MessageActionItem]] = None

    def reply(self, action: t.Optional[MessageActionItem] = None) -> None:
        """
        Reply to the ShowMessageRequest with the user's selection.

        No bytes are actually returned from this method, the reply's bytes
        are added to the client's internal send buffer.
        """
        self._client._send_response(
            id=self._id, result=action.model_dump() if action is not None else None
        )


@attrs.define(slots=True)
class LogMessage(ServerNotification):
    type: MessageType
    message: str


@attrs.define(slots=True)
class WorkDoneProgressCreate(ServerRequest):
    token: ProgressToken

    def reply(self) -> None:
        self._client._send_response(id=self._id, result=None)


@attrs.define(slots=True)
class Progress(ServerNotification):
    token: ProgressToken
    value: t.Union[
        WorkDoneProgressBeginValue,
        WorkDoneProgressReportValue,
        WorkDoneProgressEndValue,
    ]


@attrs.define(slots=True)
class WorkDoneProgress(Progress):
    pass


@attrs.define(slots=True)
class WorkDoneProgressBegin(WorkDoneProgress):
    value: WorkDoneProgressBeginValue


@attrs.define(slots=True)
class WorkDoneProgressReport(WorkDoneProgress):
    value: WorkDoneProgressReportValue


@attrs.define(slots=True)
class WorkDoneProgressEnd(WorkDoneProgress):
    value: WorkDoneProgressEndValue


# XXX: should these two be just Events or?
@attrs.define(slots=True)
class Completion(Event):
    message_id: Id
    completion_list: t.Optional[t.Dict[str, t.Any]] = None


# XXX: not sure how to name this event.
@attrs.define(slots=True)
class WillSaveWaitUntilEdits(Event):
    edits: t.Optional[t.List[TextEdit]] = None


@attrs.define(slots=True)
class PublishDiagnostics(ServerNotification):
    uri: str
    diagnostics: t.List[Diagnostic]


@attrs.define(slots=True)
class WorkspaceProjectInitializationComplete(ServerNotification):
    """Notification, exclusive to the Roslyn language server to indicate that the solution has been loaded."""

    pass


""" Hover:
    * contents: MarkedString | MarkedString[] | MarkupContent;
    * range?: Range;
"""
@attrs.define(slots=True)
class Hover(MethodResponse):
    contents: t.Union[
        t.List[t.Union[MarkedString, str]], MarkedString, MarkupContent, str
    ]
    range: t.Optional[Range] = None

    # DBG
    def m_str(self):
        """Return hover contents as markdown-compatible string."""
        def item_str(item): #SKIP
            if isinstance(item, MarkedString):
                return f'[{item.language}]\n{item.value}'
            elif isinstance(item, MarkupContent):
                return f'[{item.kind}]\n{item.value}'
            return item # str

        if isinstance(self.contents, list):
            return '\n'.join((item_str(item) for item in self.contents))
        return item_str(self.contents)

@attrs.define(slots=True)
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


@attrs.define(slots=True)
class SemanticTokens(Event):
    message_id: t.Optional[Id] = None
    resultId: t.Optional[str] = None
    data: t.List[int]
    

@attrs.define(slots=True)
class Definition(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None] = None


@attrs.define(slots=True)
class WorkspaceEdit(MethodResponse):
    changes: t.Optional[t.Dict[str, t.List[TextEdit]]] = None
    documentChanges: t.Optional[t.List[TextDocumentEdit]] = None


# result is a list, so putting in a custom class
@attrs.define(slots=True)
class References(MethodResponse):
    result: t.Union[t.List[Location], None]


@attrs.define(slots=True)
class MCallHierarchItems(Event):
    result: t.Union[t.List[CallHierarchyItem], None]


@attrs.define(slots=True)
class Implementation(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None]


@attrs.define(slots=True)
class MWorkspaceSymbols(MethodResponse):
    result: t.Union[t.List[SymbolInformation], None]


@attrs.define(slots=True)
class MFoldingRanges(MethodResponse):
    result: t.Optional[t.List[FoldingRange]] = None


@attrs.define(slots=True)
class MInlayHints(MethodResponse):
    result: t.Optional[t.List[InlayHint]] = None


@attrs.define(slots=True)
class MDocumentSymbols(MethodResponse):
    result: t.Union[t.List[SymbolInformation], t.List[DocumentSymbol], None] = None


@attrs.define(slots=True)
class Declaration(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None]


@attrs.define(slots=True)
class TypeDefinition(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None]


@attrs.define(slots=True)
class RegisterCapabilityRequest(ServerRequest):
    registrations: t.List[Registration]

    def reply(self) -> None:
        self._client._send_response(id=self._id, result={})


@attrs.define(slots=True)
class DocumentFormatting(MethodResponse):
    result: t.Union[t.List[TextEdit], None] = None


@attrs.define(slots=True)
class WorkspaceFolders(ServerRequest):
    result: t.Optional[t.List[WorkspaceFolder]] = None

    def reply(self, folders: t.Optional[t.List[WorkspaceFolder]] = None) -> None:
        """
        Reply to the WorkspaceFolder with workspace folders.

        No bytes are actually returned from this method, the reply's bytes
        are added to the client's internal send buffer.
        """
        self._client._send_response(
            id=self._id,
            result=[f.model_dump() for f in folders] if folders is not None else None,
        )


@attrs.define(slots=True)
class ConfigurationRequest(ServerRequest):
    items: t.List[ConfigurationItem]

    def reply(self, result: t.List[t.Any]) -> None:
        self._client._send_response(id=self._id, result=result)

@attrs.define(slots=True)
class Metadata(Event):
    message_id: t.Optional[Id] = None
    result: t.Optional[JSONDict] = None
    
