from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:  # avoid import cycle at runtime
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

Id = Union[int, str]


@dataclass
class Event:
    pass


@dataclass
class MethodResponse(Event):
    message_id: Optional[Id] = None


@dataclass
class ResponseError(Event):
    message_id: Optional[Id] = None
    code: int = 0
    message: str = ""
    data: Optional[Union[str, int, float, bool, List[Any], JSONDict, None]] = None


@dataclass
class ServerRequest(Event):
    _client: Optional['Client'] = field(default=None, repr=False, compare=False)
    _id: Optional[Id] = field(default=None, repr=False, compare=False)


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
    actions: Optional[List[MessageActionItem]] = None

    def reply(self, action: Optional[MessageActionItem] = None) -> None:
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
    value: Union[WorkDoneProgressBeginValue, WorkDoneProgressReportValue, 
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
    completion_list: Optional[Dict[str, Any]] = None


@dataclass
class WillSaveWaitUntilEdits(Event):
    edits: Optional[List[TextEdit]] = None


@dataclass
class PublishDiagnostics(ServerNotification):
    uri: str = ""
    diagnostics: List[Diagnostic] = field(default_factory=list)


@dataclass
class WorkspaceProjectInitializationComplete(ServerNotification):
    pass


@dataclass
class Hover(MethodResponse):
    contents: Union[List[Union[MarkedString, str]], MarkedString, MarkupContent, str] = ""
    range: Optional[Range] = None

    def m_str(self):
        """Return hover contents as markdown-compatible string."""
        def item_str(item):
            if isinstance(item, MarkedString):
                return f'[{item.language}]\n{item.value}'
            elif isinstance(item, MarkupContent):
                return f'[{item.kind}]\n{item.value}'
            return item

        if isinstance(self.contents, list):
            return '\n'.join((item_str(item) for item in self.contents))
        return item_str(self.contents)


@dataclass
class SignatureHelp(MethodResponse):
    signatures: List[SignatureInformation] = field(default_factory=list)
    activeSignature: Optional[int] = None
    activeParameter: Optional[int] = None

    def get_hint_str(self) -> Optional[str]:
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
    data: List[int] = field(default_factory=list)
    message_id: Optional[Id] = None
    resultId: Optional[str] = None


@dataclass
class Definition(MethodResponse):
    result: Union[Location, List[Union[Location, LocationLink]], None] = None


@dataclass
class WorkspaceEdit(MethodResponse):
    changes: Optional[Dict[str, List[TextEdit]]] = None
    documentChanges: Optional[List[TextDocumentEdit]] = None


@dataclass
class References(MethodResponse):
    result: Union[List[Location], None] = None


@dataclass
class MCallHierarchItems(Event):
    result: Union[List[CallHierarchyItem], None] = None


@dataclass
class Implementation(MethodResponse):
    result: Union[Location, List[Union[Location, LocationLink]], None] = None


@dataclass
class MWorkspaceSymbols(MethodResponse):
    result: Union[List[SymbolInformation], None] = None


@dataclass
class MFoldingRanges(MethodResponse):
    result: Optional[List[FoldingRange]] = None


@dataclass
class MInlayHints(MethodResponse):
    result: Optional[List[InlayHint]] = None


@dataclass
class MDocumentSymbols(MethodResponse):
    result: Union[List[SymbolInformation], List[DocumentSymbol], None] = None


@dataclass
class Declaration(MethodResponse):
    result: Union[Location, List[Union[Location, LocationLink]], None] = None


@dataclass
class TypeDefinition(MethodResponse):
    result: Union[Location, List[Union[Location, LocationLink]], None] = None


@dataclass
class RegisterCapabilityRequest(ServerRequest):
    registrations: List[Registration] = field(default_factory=list)

    def reply(self) -> None:
        if self._client:
            self._client._send_response(id=self._id, result={})


@dataclass
class DocumentFormatting(MethodResponse):
    result: Union[List[TextEdit], None] = None


@dataclass
class WorkspaceFolders(ServerRequest):
    result: Optional[List[WorkspaceFolder]] = None

    def reply(self, folders: Optional[List[WorkspaceFolder]] = None) -> None:
        if self._client:
            result = [f.to_dict() for f in folders] if folders is not None else None
            self._client._send_response(id=self._id, result=result)


@dataclass
class ConfigurationRequest(ServerRequest):
    items: List[ConfigurationItem] = field(default_factory=list)

    def reply(self, result: List[Any]) -> None:
        if self._client:
            self._client._send_response(id=self._id, result=result)


@dataclass
class Metadata(Event):
    message_id: Optional[Id] = None
    result: Optional[JSONDict] = None
