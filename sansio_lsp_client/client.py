"""Sans-I/O LSP client state machine.

Sends requests/notifications and turns incoming server messages into
`lsprotocol` message objects. There are **no hand-written LSP types here**:

* JSON-RPC envelopes and payloads come exclusively from
  ``lsprotocol.types`` (e.g. ``HoverResponse``, ``ShowMessageNotification``,
  ``RegistrationRequest``, ``ResponseErrorMessage``),
* method-to-type dispatch uses lsprotocol's own ``METHOD_TO_TYPES`` table,
* (de)serialization uses the cattrs converter from
  ``lsprotocol.converters``.

Messages for methods unknown to the LSP specification (e.g. Roslyn's
``workspace/projectInitializationComplete`` or OmniSharp's ``o#/metadata``)
are yielded as the raw parsed JSON dict, since lsprotocol has no types for
them.
"""

import enum
import typing as t

import attrs
from lsprotocol import types as lsp
from lsprotocol.types import METHOD_TO_TYPES

from .io_handler import (
    Id,
    JSONDict,
    JSONList,
    ProgressToken,
    _dump_content,
    _make_request_content,
    _make_response_content,
    _parse_messages,
    structure,
    unstructure,
)

__all__ = [
    "Client",
    "ClientState",
    "CAPABILITIES",
    "Id",
    "JSONDict",
    "JSONList",
    "ProgressToken",
]


class ClientState(enum.Enum):
    NOT_INITIALIZED = enum.auto()
    WAITING_FOR_INITIALIZED = enum.auto()
    NORMAL = enum.auto()
    WAITING_FOR_SHUTDOWN = enum.auto()
    SHUTDOWN = enum.auto()
    EXITED = enum.auto()


#NOTE: Server capabilities: resolveProvider - info about completion item -- can't use?
# Client capabilities, sent in the "initialize" request (raw JSON literal).
CAPABILITIES: JSONDict = {
    "textDocument": {
        "synchronization": {
            "didSave": True,
            #'willSaveWaitUntil': True,
            "dynamicRegistration": True,
            #'willSave': True
        },
        "publishDiagnostics": {
            "relatedInformation": True,
            "tagSupport": {"valueSet": [1, 2]}
        },
        "completion": {
            "dynamicRegistration": True,
            "completionItem": {"snippetSupport": True},
            "completionItemKind": {"valueSet": list(lsp.CompletionItemKind)},
            "contextSupport": True,
        },
        "hover": {
            "dynamicRegistration": True,
            "contentFormat": ["markdown", "plaintext"],
        },
        "foldingRange": {
            "dynamicRegistration": True,
        },
        "inlayHint": {
            "dynamicRegistration": True,
        },
        "definition": {"dynamicRegistration": True, "linkSupport": True},
        "signatureHelp": {
            "dynamicRegistration": True,
            "signatureInformation": {
                "parameterInformation": {
                    "labelOffsetSupport": True  # substring from label
                },
                "documentationFormat": ["markdown", "plaintext"],
                "activeParameterSupport": True
            },
        },
        "implementation": {"linkSupport": True, "dynamicRegistration": True},
        "references": {"dynamicRegistration": True},
        "callHierarchy": {"dynamicRegistration": True},
        "declaration": {"linkSupport": True, "dynamicRegistration": True},
        "typeDefinition": {"linkSupport": True, "dynamicRegistration": True},
        "formatting": {"dynamicRegistration": True},
        "rangeFormatting": {"dynamicRegistration": True},
        "rename": {"dynamicRegistration": True},
        "documentSymbol": {
            "hierarchicalDocumentSymbolSupport": True,
            "dynamicRegistration": True,
            "symbolKind": {"valueSet": list(lsp.SymbolKind)},
        },
    },
    "window": {
        "showMessage": {
            # TODO 'messageActionItem':...
            #"messageActionItem": {
                #"additionalPropertiesSupport": True
            #}
        },
        "workDoneProgress": True,
    },
    "workspace": {
        "symbol": {
            "dynamicRegistration": True,
            "symbolKind": {"valueSet": list(lsp.SymbolKind)},
        },
        "workspaceFolders": True,
        # TODO 'workspaceEdit':..., #'applyEdit':..., 'executeCommand':...,
        #"workspaceEdit": {
            #"failureHandling": "abort",
            #"documentChanges": True
        #},
        #"applyEdit": True,
        #"executeCommand": {},
        "configuration": True,
        "didChangeConfiguration": {"dynamicRegistration": True},
    },
}


def _to_raw(value: t.Any) -> t.Any:
    """Convert a value to JSON-serializable data.

    lsprotocol/attrs objects (and lists/tuples thereof) are unstructured
    with the shared converter; raw JSON data is passed through unchanged.
    """
    if isinstance(value, (list, tuple)):
        return [_to_raw(v) for v in value]
    if value is not None and attrs.has(type(value)):
        return unstructure(value)
    return value


# Methods whose result is `Location | Location[] | LocationLink[]`.
_GOTO_RESPONSE_METHODS = frozenset(
    (
        "textDocument/definition",
        "textDocument/implementation",
        "textDocument/declaration",
        "textDocument/typeDefinition",
    )
)


class Client:
    # TODO: Save the encoding given here.
    def __init__(
        self,
        process_id: t.Optional[int] = None,
        root_uri: t.Optional[str] = None,
        workspace_folders: t.Optional[t.List[lsp.WorkspaceFolder]] = None,
        trace: str = "off",
        settings: t.Optional[t.Any] = {},
        spy: t.Optional[t.Callable[[str, JSONDict, t.Optional[str]], None]] = None,
    ) -> None:
        self._state = ClientState.NOT_INITIALIZED

        # Optional message spy: called as spy(direction, content, method) for
        # every complete JSON-RPC message going in ('recv') or out ('send'),
        # with the *raw parsed content dict* and (when known) the method name
        # a response belongs to. Must never raise - failures are swallowed.
        # Set before the 'initialize' request is queued, so it is spied too.
        self._spy = spy

        # Methods of server->client requests, by request id: lets the spy
        # display which method our responses reply to.
        self._server_request_methods: t.Dict[Id, str] = {}

        # Used to save data as it comes in (from `recieve_bytes`) until we have
        # a full request.
        self._recv_buf = bytearray()

        # Things that we still need to send.
        self._send_buf = bytearray()

        # Keeps track of which IDs match to which unanswered requests.
        self._unanswered_requests: t.Dict[Id, str] = {}

        # Just a simple counter to make sure we have unique IDs. We could make
        # sure that this fits into a JSONRPC Number, seeing as Python supports
        # bignums, but I think that's an unlikely enough case that checking for
        # it would just litter the code unnecessarily.
        self._id_counter = 0

        # We'll just immediately send off an "initialize" request.
        self._send_request(
            method="initialize",
            params={
                "processId": process_id,
                "rootUri": root_uri,
                "workspaceFolders": (
                    None
                    if workspace_folders is None
                    else [unstructure(f) for f in workspace_folders]
                ),
                "trace": trace,
                "capabilities": CAPABILITIES,
                "initializationOptions": settings,
            },
        )
        self._state = ClientState.WAITING_FOR_INITIALIZED

        # prepare configuration for sending via "workspace/didChangeConfiguration"
        self.settings = settings

    @property
    def state(self) -> ClientState:
        return self._state

    def set_spy(
        self, spy: t.Optional[t.Callable[[str, JSONDict, t.Optional[str]], None]] = None
    ) -> None:
        """Register/replace/remove the message spy callback (see ``__init__``)."""
        self._spy = spy

    def _spy_message(self, direction: str, content: JSONDict) -> None:
        """Feed the registered spy (if any) with one complete raw message."""
        if self._spy is None:
            return
        try:
            method = None
            if isinstance(content, dict):
                method = content.get("method")
                if method is None and "id" in content:
                    # Response: correlate its id with a method name, so the spy
                    # can display e.g. 'textDocument/hover (id 3)'.
                    if direction == "recv":
                        method = self._unanswered_requests.get(content["id"])
                    else:
                        method = self._server_request_methods.get(content["id"])
            self._spy(direction, content, method)
        except Exception:
            # Spying must never break the protocol.
            pass

    @property
    def is_initialized(self) -> bool:
        return (
            self._state != ClientState.NOT_INITIALIZED
            and self._state != ClientState.WAITING_FOR_INITIALIZED
        )

    def _send_request(self, method: str, params: t.Optional[JSONDict] = None) -> Id:
        id: Id = self._id_counter
        self._id_counter += 1

        content = _make_request_content(method=method, params=params, id=id)
        self._spy_message("send", content)
        self._send_buf += _dump_content(content)
        self._unanswered_requests[id] = method
        return id

    def _send_notification(
        self, method: str, params: t.Optional[JSONDict] = None
    ) -> None:
        content = _make_request_content(method=method, params=params)
        self._spy_message("send", content)
        self._send_buf += _dump_content(content)

    def _send_response(
        self,
        id: Id,
        result: t.Optional[t.Union[JSONDict, JSONList]] = None,
        error: t.Optional[JSONDict] = None,
    ) -> None:
        content = _make_response_content(id=id, result=result, error=error)
        self._spy_message("send", content)
        self._server_request_methods.pop(id, None)
        self._send_buf += _dump_content(content)

    # ------------------------------------------------------------------
    # Incoming messages: raw JSON dict -> lsprotocol message objects
    # ------------------------------------------------------------------

    @staticmethod
    def _structure_progress_params(params: JSONDict) -> lsp.ProgressParams:
        """Structure ``$/progress`` params.

        ``ProgressParams.value`` is typed ``LSPAny`` in the spec (progress
        values are extensible), so the converter leaves it as a raw dict.
        The well-known ``window/workDoneProgress`` kinds are structured into
        their lsprotocol classes here; unknown kinds stay raw.
        """
        p = structure(params, lsp.ProgressParams)
        value = p.value
        if isinstance(value, dict):
            kind = value.get("kind")
            if kind == "begin":
                p.value = structure(value, lsp.WorkDoneProgressBegin)
            elif kind == "report":
                p.value = structure(value, lsp.WorkDoneProgressReport)
            elif kind == "end":
                p.value = structure(value, lsp.WorkDoneProgressEnd)
        return p

    def _handle_request(self, content: JSONDict) -> t.Any:
        """Handle a server->client request or notification."""
        method: str = content["method"]

        # Remember server request methods for spy display of our responses.
        request_id = content.get("id")
        if request_id is not None:
            self._server_request_methods[request_id] = method

        if method == "$/progress":
            # if "window/workDoneProgress/create" request from server was missing -
            # it's not an error: the notification is still parsed fine.
            # such server bugs must be silently ignored without crashing our plugin.
            return lsp.ProgressNotification(
                params=self._structure_progress_params(content.get("params") or {})
            )

        types = METHOD_TO_TYPES.get(method)
        if types is None:
            # Not part of the LSP spec (e.g. Roslyn's
            # 'workspace/projectInitializationComplete'): no lsprotocol type
            # exists, yield the raw parsed message.
            return content

        return structure(content, types[0])

    def _handle_response(self, content: JSONDict) -> t.Any:
        """Handle a response to one of our requests."""
        response_id = content.get("id")
        method = self._unanswered_requests.pop(response_id, None)
        if method is None:
            # Response to a request we never made (or already answered) -
            # a server bug; don't let it kill the message stream.
            return content

        # FIXME: The errors have meanings.
        if content.get("error") is not None:
            return structure(content, lsp.ResponseErrorMessage)

        if method == "initialize":
            assert self._state == ClientState.WAITING_FOR_INITIALIZED
            self._send_notification(
                "initialized", params={}
            )  # params=None doesn't work with gopls
            self._send_notification("workspace/didChangeConfiguration", params={
                "settings": self.settings
            })
            self._state = ClientState.NORMAL
            return structure(content, lsp.InitializeResponse)

        if method == "shutdown":
            assert self._state == ClientState.WAITING_FOR_SHUTDOWN
            self._state = ClientState.SHUTDOWN
            return structure(content, lsp.ShutdownResponse)

        if method == "textDocument/completion":
            # ! structuring the completion list is expensive and not really
            # needed: items are kept as raw dicts (perf optimization).
            result = content.get("result")
            if isinstance(result, list):
                # legacy: bare CompletionItem[] -> CompletionList shape
                result = {"isIncomplete": False, "items": result}
            return lsp.CompletionResponse(id=response_id, result=result)

        types = METHOD_TO_TYPES.get(method)
        if types is None or types[1] is None:
            # Custom method not in the LSP spec (e.g. OmniSharp 'o#/metadata'):
            # no lsprotocol response type exists, yield the raw parsed message.
            return content

        if method in _GOTO_RESPONSE_METHODS:
            result = content.get("result")
            if isinstance(result, dict) and "targetUri" in result:
                # Non-conformant server sent a single LocationLink *object*
                # (the spec only allows LocationLink[]). lsprotocol's
                # Location hook would misread it as a Location and fail;
                # structure it explicitly instead.
                return types[1](
                    id=response_id, result=structure(result, lsp.LocationLink)
                )

        return structure(content, types[1])

    def _handle_message(self, content: JSONDict) -> t.Any:
        if "method" in content:
            return self._handle_request(content)
        return self._handle_response(content)

    # ------------------------------------------------------------------
    # Public I/O
    # ------------------------------------------------------------------

    def recv(self, data: bytes) -> t.Iterator[t.Any]:
        self._recv_buf += data
        # Make sure to use lots of iterators, so that if one message fails to
        # parse, the messages before it are yielded successfully before the
        # error, and the messages after it are left in _recv_buf.
        for content in _parse_messages(self._recv_buf):
            # Spy on every *complete* incoming message - before/independently
            # of message parsing, so even malformed messages are visible.
            self._spy_message("recv", content)
            yield self._handle_message(content)

    def send(self) -> bytes:
        send_buf = self._send_buf[:]
        self._send_buf.clear()
        return send_buf

    def respond(
        self,
        id: Id,
        result: t.Any = None,
        error: t.Optional[lsp.ResponseError] = None,
    ) -> None:
        """Reply to a server->client request.

        ``result`` may be raw JSON data or lsprotocol objects (or lists
        thereof); lsprotocol objects are unstructured automatically.

        No bytes are actually returned from this method, the reply's bytes
        are added to the client's internal send buffer.
        """
        self._send_response(
            id=id,
            result=_to_raw(result),
            error=(unstructure(error) if error is not None else None),
        )

    def shutdown(self) -> None:
        assert self._state == ClientState.NORMAL
        self._send_request(method="shutdown")
        self._state = ClientState.WAITING_FOR_SHUTDOWN

    def exit(self) -> None:
        assert self._state == ClientState.SHUTDOWN
        # TODO: figure out why params={} is needed
        self._send_notification(method="exit", params={})
        self._state = ClientState.EXITED

    def cancel_last_request(self) -> None:
        params = unstructure(lsp.CancelParams(id=self._id_counter - 1))
        self._send_notification(method="$/cancelRequest", params=params)

    # ------------------------------------------------------------------
    # Client -> server notifications
    # ------------------------------------------------------------------

    def did_open(self, text_document: lsp.TextDocumentItem) -> None:
        assert self._state == ClientState.NORMAL
        params = lsp.DidOpenTextDocumentParams(text_document=text_document)
        self._send_notification(
            method="textDocument/didOpen", params=unstructure(params)
        )

    def did_change(
        self,
        text_document: lsp.VersionedTextDocumentIdentifier,
        content_changes: t.List[lsp.TextDocumentContentChangeEvent],
    ) -> None:
        assert self._state == ClientState.NORMAL
        params = lsp.DidChangeTextDocumentParams(
            text_document=text_document,
            content_changes=content_changes,
        )
        self._send_notification(
            method="textDocument/didChange", params=unstructure(params)
        )

    def did_change_configuration(self, settings: t.Any) -> None:
        assert self._state == ClientState.NORMAL
        params = lsp.DidChangeConfigurationParams(settings=settings)
        self._send_notification(
            method="workspace/didChangeConfiguration", params=unstructure(params)
        )

    def will_save(
        self, text_document: lsp.TextDocumentIdentifier, reason: lsp.TextDocumentSaveReason
    ) -> None:
        assert self._state == ClientState.NORMAL
        params = lsp.WillSaveTextDocumentParams(
            text_document=text_document, reason=reason
        )
        self._send_notification(
            method="textDocument/willSave", params=unstructure(params)
        )

    def will_save_wait_until(
        self, text_document: lsp.TextDocumentIdentifier, reason: lsp.TextDocumentSaveReason
    ) -> None:
        assert self._state == ClientState.NORMAL
        params = lsp.WillSaveTextDocumentParams(
            text_document=text_document, reason=reason
        )
        self._send_request(
            method="textDocument/willSaveWaitUntil", params=unstructure(params)
        )

    def did_save(
        self, text_document: lsp.TextDocumentIdentifier, text: t.Optional[str] = None
    ) -> None:
        assert self._state == ClientState.NORMAL
        params = lsp.DidSaveTextDocumentParams(
            text_document=text_document, text=text
        )
        self._send_notification(method="textDocument/didSave", params=unstructure(params))

    def did_close(self, text_document: lsp.TextDocumentIdentifier) -> None:
        assert self._state == ClientState.NORMAL
        params = lsp.DidCloseTextDocumentParams(text_document=text_document)
        self._send_notification(
            method="textDocument/didClose", params=unstructure(params)
        )

    def did_change_workspace_folders(
        self, added: t.List[lsp.WorkspaceFolder], removed: t.List[lsp.WorkspaceFolder]
    ) -> None:
        assert self._state == ClientState.NORMAL
        params = lsp.DidChangeWorkspaceFoldersParams(
            event=lsp.WorkspaceFoldersChangeEvent(added=added, removed=removed)
        )
        self._send_notification(
            method="workspace/didChangeWorkspaceFolders", params=unstructure(params)
        )

    # ------------------------------------------------------------------
    # Client -> server requests (return the request id)
    # ------------------------------------------------------------------

    def completion(
        self,
        text_document_position: lsp.TextDocumentPositionParams,
        context: t.Optional[lsp.CompletionContext] = None,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.CompletionParams(
            text_document=text_document_position.text_document,
            position=text_document_position.position,
            context=context,
        )
        return self._send_request(
            method="textDocument/completion", params=unstructure(params)
        )

    def semantic_tokens(
        self,
        text_document: lsp.TextDocumentIdentifier,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.SemanticTokensParams(text_document=text_document)
        return self._send_request(
            method="textDocument/semanticTokens/full", params=unstructure(params)
        )

    def rename(
        self,
        text_document_position: lsp.TextDocumentPositionParams,
        new_name: str,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.RenameParams(
            text_document=text_document_position.text_document,
            position=text_document_position.position,
            new_name=new_name,
        )
        return self._send_request(method="textDocument/rename", params=unstructure(params))

    def hover(self, text_document_position: lsp.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.HoverParams(
            text_document=text_document_position.text_document,
            position=text_document_position.position,
        )
        return self._send_request(method="textDocument/hover", params=unstructure(params))

    def folding_range(self, text_document: lsp.TextDocumentIdentifier) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.FoldingRangeParams(text_document=text_document)
        return self._send_request(
            method="textDocument/foldingRange", params=unstructure(params)
        )

    def signatureHelp(
        self, text_document_position: lsp.TextDocumentPositionParams
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.SignatureHelpParams(
            text_document=text_document_position.text_document,
            position=text_document_position.position,
        )
        return self._send_request(
            method="textDocument/signatureHelp", params=unstructure(params)
        )

    def definition(self, text_document_position: lsp.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.DefinitionParams(
            text_document=text_document_position.text_document,
            position=text_document_position.position,
        )
        return self._send_request(
            method="textDocument/definition", params=unstructure(params)
        )

    def declaration(self, text_document_position: lsp.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.DeclarationParams(
            text_document=text_document_position.text_document,
            position=text_document_position.position,
        )
        return self._send_request(
            method="textDocument/declaration", params=unstructure(params)
        )

    def inlay_hint(
        self, text_document: lsp.TextDocumentIdentifier, range: lsp.Range
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.InlayHintParams(text_document=text_document, range=range)
        return self._send_request(
            method="textDocument/inlayHint", params=unstructure(params)
        )

    def typeDefinition(
        self, text_document_position: lsp.TextDocumentPositionParams
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.TypeDefinitionParams(
            text_document=text_document_position.text_document,
            position=text_document_position.position,
        )
        return self._send_request(
            method="textDocument/typeDefinition", params=unstructure(params)
        )

    def references(self, text_document_position: lsp.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.ReferenceParams(
            text_document=text_document_position.text_document,
            position=text_document_position.position,
            context=lsp.ReferenceContext(include_declaration=True),
        )
        return self._send_request(
            method="textDocument/references", params=unstructure(params)
        )

    # TODO incomplete
    def prepareCallHierarchy(
        self, text_document_position: lsp.TextDocumentPositionParams
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.CallHierarchyPrepareParams(
            text_document=text_document_position.text_document,
            position=text_document_position.position,
        )
        return self._send_request(
            method="textDocument/prepareCallHierarchy", params=unstructure(params)
        )

    def implementation(
        self, text_document_position: lsp.TextDocumentPositionParams
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.ImplementationParams(
            text_document=text_document_position.text_document,
            position=text_document_position.position,
        )
        return self._send_request(
            method="textDocument/implementation", params=unstructure(params)
        )

    def workspace_symbol(self, query: str = "") -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.WorkspaceSymbolParams(query=query)
        return self._send_request(method="workspace/symbol", params=unstructure(params))

    def documentSymbol(self, text_document: lsp.TextDocumentIdentifier) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.DocumentSymbolParams(text_document=text_document)
        return self._send_request(
            method="textDocument/documentSymbol", params=unstructure(params)
        )

    def formatting(
        self, text_document: lsp.TextDocumentIdentifier, options: lsp.FormattingOptions
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.DocumentFormattingParams(
            text_document=text_document, options=options
        )
        return self._send_request(
            method="textDocument/formatting", params=unstructure(params)
        )

    def rangeFormatting(
        self,
        text_document: lsp.TextDocumentIdentifier,
        range: lsp.Range,
        options: lsp.FormattingOptions,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = lsp.DocumentRangeFormattingParams(
            text_document=text_document, range=range, options=options
        )
        return self._send_request(
            method="textDocument/rangeFormatting", params=unstructure(params)
        )

    def metadata(self, params):
        return self._send_request(method="o#/metadata", params=params)
