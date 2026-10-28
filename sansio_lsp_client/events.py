from dataclasses import dataclass, field
import typing as t

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


@dataclass
class Event:
    pass


@dataclass
class MethodResponse(Event):
    message_id: t.Optional[Id] = None


@dataclass
class ResponseError(Event):
    message_id: t.Optional[Id] = None
    code: int = 0
    message: str = ""
    data: t.Optional[t.Union[str, int, float, bool, t.List[t.Any], JSONDict, None]] = None


@dataclass
class ServerRequest(Event):
    _client: t.Optional['Client'] = field(default=None, repr=False, compare=False)
    _id: t.Optional[Id] = field(default=None, repr=False, compare=False)


@dataclass
class ServerNotification(Event):
    pass


@dataclass
class Initialized(Event):
    capabilities: JSONDict = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(capabilities=data)


@dataclass
class Shutdown(Event):
    pass


@dataclass
class ShowMessage(ServerNotification):
    type: MessageType = MessageType.INFO
    message: str = ""


@dataclass
class ShowMessageRequest(ServerRequest):
    type: MessageType = MessageType.INFO
    message: str = ""
    actions: t.Optional[t.List[MessageActionItem]] = None

    def reply(self, action: t.Optional[MessageActionItem] = None) -> None:
        if self._client:
            result = {'title': action.title} if action is not None else None
            self._client._send_response(id=self._id, result=result)


@dataclass
class LogMessage(ServerNotification):
    type: MessageType = MessageType.INFO
    message: str = ""


@dataclass
class WorkDoneProgressCreate(ServerRequest):
    token: ProgressToken = ""

    def reply(self) -> None:
        if self._client:
            self._client._send_response(id=self._id, result=None)


@dataclass
class Progress(ServerNotification):
    token: ProgressToken = ""
    value: t.Union[WorkDoneProgressBeginValue, WorkDoneProgressReportValue, 
                 WorkDoneProgressEndValue] = None


@dataclass
class WorkDoneProgress(Progress):
    pass


@dataclass
class WorkDoneProgressBegin(WorkDoneProgress):
    value: WorkDoneProgressBeginValue = None


@dataclass
class WorkDoneProgressReport(WorkDoneProgress):
    value: WorkDoneProgressReportValue = None


@dataclass
class WorkDoneProgressEnd(WorkDoneProgress):
    value: WorkDoneProgressEndValue = None


@dataclass
class Completion(Event):
    message_id: Id = 0
    completion_list: t.Optional[t.Dict[str, t.Any]] = None


@dataclass
class WillSaveWaitUntilEdits(Event):
    edits: t.Optional[t.List[TextEdit]] = None


@dataclass
class PublishDiagnostics(ServerNotification):
    uri: str = ""
    diagnostics: t.List[Diagnostic] = field(default_factory=list)


@dataclass
class WorkspaceProjectInitializationComplete(ServerNotification):
    pass


@dataclass
class Hover(MethodResponse):
    contents: t.Union[t.List[t.Union[MarkedString, str]], MarkedString, MarkupContent, str] = ""
    range: t.Optional[Range] = None

    def m_str(self):
        """Return hover contents as markdown-compatible string."""
        def item_str(item):
            if isinstance(item, MarkedString):
                return f'[{item.language}]\n{item.value}'
            elif isinstance(item, MarkupContent):
                return f'[{item.kind.value if hasattr(item.kind, "value") else item.kind}]\n{item.value}'
            elif isinstance(item, dict):
                # Handle raw dict (shouldn't happen but just in case)
                if 'kind' in item:
                    return f'[{item.get("kind", "plaintext")}]\n{item.get("value", "")}'
                elif 'language' in item:
                    return f'[{item.get("language", "")}]\n{item.get("value", "")}'
                return str(item)
            return str(item)

        if isinstance(self.contents, list):
            return '\n'.join((item_str(item) for item in self.contents))
        return item_str(self.contents)


@dataclass
class SignatureHelp(MethodResponse):
    signatures: t.List[SignatureInformation] = field(default_factory=list)
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


@dataclass
class SemanticTokens(Event):
    data: t.List[int] = field(default_factory=list)
    message_id: t.Optional[Id] = None
    resultId: t.Optional[str] = None


@dataclass
class Definition(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None] = None


@dataclass
class WorkspaceEdit(MethodResponse):
    changes: t.Optional[t.Dict[str, t.List[TextEdit]]] = None
    documentChanges: t.Optional[t.List[TextDocumentEdit]] = None


@dataclass
class References(MethodResponse):
    result: t.Union[t.List[Location], None] = None


@dataclass
class MCallHierarchItems(Event):
    result: t.Union[t.List[CallHierarchyItem], None] = None


@dataclass
class Implementation(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None] = None


@dataclass
class MWorkspaceSymbols(MethodResponse):
    result: t.Union[t.List[SymbolInformation], None] = None


@dataclass
class MFoldingRanges(MethodResponse):
    result: t.Optional[t.List[FoldingRange]] = None


@dataclass
class MInlayHints(MethodResponse):
    result: t.Optional[t.List[InlayHint]] = None


@dataclass
class MDocumentSymbols(MethodResponse):
    result: t.Union[t.List[SymbolInformation], t.List[DocumentSymbol], None] = None


@dataclass
class Declaration(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None] = None


@dataclass
class TypeDefinition(MethodResponse):
    result: t.Union[Location, t.List[t.Union[Location, LocationLink]], None] = None


@dataclass
class RegisterCapabilityRequest(ServerRequest):
    registrations: t.List[Registration] = field(default_factory=list)

    def reply(self) -> None:
        if self._client:
            self._client._send_response(id=self._id, result={})


@dataclass
class DocumentFormatting(MethodResponse):
    result: t.Union[t.List[TextEdit], None] = None


@dataclass
class WorkspaceFolders(ServerRequest):
    result: t.Optional[t.List[WorkspaceFolder]] = None

    def reply(self, folders: t.Optional[t.List[WorkspaceFolder]] = None) -> None:
        if self._client:
            result = [f.to_dict() for f in folders] if folders is not None else None
            self._client._send_response(id=self._id, result=result)


@dataclass
class ConfigurationRequest(ServerRequest):
    items: t.List[ConfigurationItem] = field(default_factory=list)

    def reply(self, result: t.List[t.Any]) -> None:
        if self._client:
            self._client._send_response(id=self._id, result=result)


@dataclass
class Metadata(Event):
    message_id: t.Optional[Id] = None
    result: t.Optional[JSONDict] = None