"""Event types yielded by the client from incoming server messages.

These are thin `attrs` classes; every LSP payload they carry is typed with
classes from `lsprotocol.types` (the canonical LSP type definitions).
"""

import typing as t

import attrs

from lsprotocol import types as lsp

from .io_handler import unstructure

if t.TYPE_CHECKING:  # avoid import cycle at runtime
    from .client import Client

Id = t.Union[int, str]
ProgressToken = t.Union[int, str]
JSONDict = t.Dict[str, t.Any]
JSONList = t.List[t.Any]


@attrs.define(kw_only=True)
class Event:
    pass


@attrs.define(kw_only=True)
class MethodResponse(Event):
    message_id: t.Optional[Id] = None


@attrs.define(kw_only=True)
class ResponseError(Event):
    message_id: t.Optional[Id] = None
    code: int = 0
    message: str = ""
    data: t.Optional[t.Union[str, int, float, bool, JSONList, JSONDict]] = None


@attrs.define(kw_only=True)
class ServerRequest(Event):
    # Set by the client right after construction; not part of the wire data.
    _client: t.Optional["Client"] = attrs.field(
        default=None, init=False, repr=False, eq=False
    )
    _id: Id = attrs.field(default=-1, init=False, repr=False, eq=False)


@attrs.define(kw_only=True)
class ServerNotification(Event):
    pass


@attrs.define(kw_only=True)
class Initialized(Event):
    capabilities: lsp.ServerCapabilities


@attrs.define(kw_only=True)
class Shutdown(Event):
    pass


@attrs.define(kw_only=True)
class ShowMessage(ServerNotification):
    type: lsp.MessageType
    message: str


@attrs.define(kw_only=True)
class ShowMessageRequest(ServerRequest):
    type: lsp.MessageType
    message: str
    actions: t.Optional[t.List[lsp.MessageActionItem]] = None

    def reply(self, action: t.Optional[lsp.MessageActionItem] = None) -> None:
        """
        Reply to the ShowMessageRequest with the user's selection.

        No bytes are actually returned from this method, the reply's bytes
        are added to the client's internal send buffer.
        """
        self._client._send_response(
            id=self._id, result=unstructure(action) if action is not None else None
        )


@attrs.define(kw_only=True)
class LogMessage(ServerNotification):
    type: lsp.MessageType
    message: str


@attrs.define(kw_only=True)
class WorkDoneProgressCreate(ServerRequest):
    token: ProgressToken

    def reply(self) -> None:
        self._client._send_response(id=self._id, result=None)


@attrs.define(kw_only=True)
class Progress(ServerNotification):
    token: ProgressToken
    value: t.Union[
        lsp.WorkDoneProgressBegin,
        lsp.WorkDoneProgressReport,
        lsp.WorkDoneProgressEnd,
    ]


@attrs.define(kw_only=True)
class WorkDoneProgress(Progress):
    pass


@attrs.define(kw_only=True)
class WorkDoneProgressBegin(WorkDoneProgress):
    value: lsp.WorkDoneProgressBegin


@attrs.define(kw_only=True)
class WorkDoneProgressReport(WorkDoneProgress):
    value: lsp.WorkDoneProgressReport


@attrs.define(kw_only=True)
class WorkDoneProgressEnd(WorkDoneProgress):
    value: lsp.WorkDoneProgressEnd


@attrs.define(kw_only=True)
class Completion(Event):
    message_id: t.Optional[Id] = None
    # Raw JSON dict of the server's CompletionList (perf optimization:
    # items are kept as raw dicts and never structured into objects).
    completion_list: t.Optional[t.Dict[str, t.Any]] = None


@attrs.define(kw_only=True)
class WillSaveWaitUntilEdits(Event):
    edits: t.Optional[t.List[lsp.TextEdit]] = None


@attrs.define(kw_only=True)
class PublishDiagnostics(ServerNotification):
    uri: str
    diagnostics: t.List[lsp.Diagnostic]


@attrs.define(kw_only=True)
class WorkspaceProjectInitializationComplete(ServerNotification):
    """Notification, exclusive to the Roslyn language server to indicate that
    the solution has been loaded."""


@attrs.define(kw_only=True)
class Hover(MethodResponse):
    contents: t.Union[
        t.List[t.Union[lsp.MarkedStringWithLanguage, str]],
        lsp.MarkedStringWithLanguage,
        lsp.MarkupContent,
        str,
    ]
    range: t.Optional[lsp.Range] = None

    def m_str(self) -> str:
        """Return hover contents as markdown-compatible string."""

        def item_str(item):  # SKIP
            if isinstance(item, lsp.MarkedStringWithLanguage):
                return f'[{item.language}]\n{item.value}'
            elif isinstance(item, lsp.MarkupContent):
                return f'[{item.kind}]\n{item.value}'
            return item  # str

        if isinstance(self.contents, list):
            return '\n'.join((item_str(item) for item in self.contents))
        return item_str(self.contents)


@attrs.define(kw_only=True)
class SignatureHelp(MethodResponse):
    signatures: t.List[lsp.SignatureInformation]
    active_signature: t.Optional[int] = None
    active_parameter: t.Optional[int] = None

    def get_hint_str(self) -> t.Optional[str]:
        if len(self.signatures) == 0:
            return None
        active_sig = self.active_signature or 0
        sig = self.signatures[active_sig]
        return sig.label

    def get_signatures(self):
        if len(self.signatures) == 0:
            return None
        return self.signatures, self.active_signature, self.active_parameter


@attrs.define(kw_only=True)
class SemanticTokens(Event):
    message_id: t.Optional[Id] = None
    result_id: t.Optional[str] = None
    data: t.List[int]


@attrs.define(kw_only=True)
class Definition(MethodResponse):
    result: t.Optional[
        t.Union[lsp.Location, t.List[t.Union[lsp.Location, lsp.LocationLink]]]
    ] = None


@attrs.define(kw_only=True)
class WorkspaceEdit(MethodResponse):
    changes: t.Optional[t.Dict[str, t.List[lsp.TextEdit]]] = None
    document_changes: t.Optional[t.List[lsp.TextDocumentEdit]] = None


# result is a list, so putting in a custom class
@attrs.define(kw_only=True)
class References(MethodResponse):
    result: t.Optional[t.List[lsp.Location]]


@attrs.define(kw_only=True)
class MCallHierarchItems(Event):
    result: t.Optional[t.List[lsp.CallHierarchyItem]]


@attrs.define(kw_only=True)
class Implementation(MethodResponse):
    result: t.Optional[
        t.Union[lsp.Location, t.List[t.Union[lsp.Location, lsp.LocationLink]]]
    ] = None


@attrs.define(kw_only=True)
class MWorkspaceSymbols(MethodResponse):
    result: t.Optional[t.List[lsp.SymbolInformation]]


@attrs.define(kw_only=True)
class MFoldingRanges(MethodResponse):
    result: t.Optional[t.List[lsp.FoldingRange]] = None


@attrs.define(kw_only=True)
class MInlayHints(MethodResponse):
    result: t.Optional[t.List[lsp.InlayHint]] = None


@attrs.define(kw_only=True)
class MDocumentSymbols(MethodResponse):
    result: t.Optional[
        t.Union[t.List[lsp.SymbolInformation], t.List[lsp.DocumentSymbol]]
    ] = None


@attrs.define(kw_only=True)
class Declaration(MethodResponse):
    result: t.Optional[
        t.Union[lsp.Location, t.List[t.Union[lsp.Location, lsp.LocationLink]]]
    ] = None


@attrs.define(kw_only=True)
class TypeDefinition(MethodResponse):
    result: t.Optional[
        t.Union[lsp.Location, t.List[t.Union[lsp.Location, lsp.LocationLink]]]
    ] = None


@attrs.define(kw_only=True)
class RegisterCapabilityRequest(ServerRequest):
    registrations: t.List[lsp.Registration]

    def reply(self) -> None:
        self._client._send_response(id=self._id, result={})


@attrs.define(kw_only=True)
class DocumentFormatting(MethodResponse):
    result: t.Optional[t.List[lsp.TextEdit]] = None


@attrs.define(kw_only=True)
class WorkspaceFolders(ServerRequest):
    result: t.Optional[t.List[lsp.WorkspaceFolder]] = None

    def reply(self, folders: t.Optional[t.List[lsp.WorkspaceFolder]] = None) -> None:
        """
        Reply to the WorkspaceFolder with workspace folders.

        No bytes are actually returned from this method, the reply's bytes
        are added to the client's internal send buffer.
        """
        self._client._send_response(
            id=self._id,
            result=(
                [unstructure(f) for f in folders] if folders is not None else None
            ),
        )


@attrs.define(kw_only=True)
class ConfigurationRequest(ServerRequest):
    items: t.List[lsp.ConfigurationItem]

    def reply(self, result: t.List[t.Any]) -> None:
        self._client._send_response(id=self._id, result=result)


@attrs.define(kw_only=True)
class Metadata(Event):
    message_id: t.Optional[Id] = None
    result: t.Optional[JSONDict] = None
