"""Sans-I/O LSP client state machine.

Sends requests/notifications and turns incoming server messages into
`events` objects. All LSP payloads are typed with `lsprotocol.types` and
(de)serialized with the cattrs converter from `lsprotocol.converters`.
"""

import enum
import typing as t

from lsprotocol import types as lsp

from .events import (
    Completion,
    ConfigurationRequest,
    Declaration,
    Definition,
    DocumentFormatting,
    Event,
    Hover,
    Implementation,
    Initialized,
    LogMessage,
    MCallHierarchItems,
    MDocumentSymbols,
    MFoldingRanges,
    MInlayHints,
    Metadata,
    MWorkspaceSymbols,
    MethodResponse,
    Progress,
    PublishDiagnostics,
    References,
    RegisterCapabilityRequest,
    ResponseError,
    SemanticTokens,
    ServerRequest,
    ShowMessage,
    ShowMessageRequest,
    Shutdown,
    SignatureHelp,
    TypeDefinition,
    WillSaveWaitUntilEdits,
    WorkDoneProgress,
    WorkDoneProgressBegin,
    WorkDoneProgressCreate,
    WorkDoneProgressEnd,
    WorkDoneProgressReport,
    WorkspaceEdit,
    WorkspaceFolders,
    WorkspaceProjectInitializationComplete,
)
from .io_handler import (
    Id,
    JSONDict,
    JSONList,
    ProgressToken,
    Request,
    Response,
    _make_request,
    _make_response,
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
    "Request",
    "Response",
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


class Client:
    # TODO: Save the encoding given here.
    def __init__(
        self,
        process_id: t.Optional[int] = None,
        root_uri: t.Optional[str] = None,
        workspace_folders: t.Optional[t.List[lsp.WorkspaceFolder]] = None,
        trace: str = "off",
        settings: t.Optional[t.Any] = {},
    ) -> None:
        self._state = ClientState.NOT_INITIALIZED

        # Used to save data as it comes in (from `recieve_bytes`) until we have
        # a full request.
        self._recv_buf = bytearray()

        # Things that we still need to send.
        self._send_buf = bytearray()

        # Keeps track of which IDs match to which unanswered requests.
        self._unanswered_requests: t.Dict[Id, Request] = {}

        # Just a simple counter to make sure we have unique IDs. We could make
        # sure that this fits into a JSONRPC Number, seeing as Python supports
        # bignums, but I think that's an unlikely enough case that checking for
        # it would just litter the code unnecessarily.
        self._id_counter = 0

        # Store type of '$/progress' for parsing
        self._progress_tokens_map: t.Dict[ProgressToken, t.Type[Progress]] = {}

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

    @property
    def is_initialized(self) -> bool:
        return (
            self._state != ClientState.NOT_INITIALIZED
            and self._state != ClientState.WAITING_FOR_INITIALIZED
        )

    def _send_request(self, method: str, params: t.Optional[JSONDict] = None) -> Id:
        id: Id = self._id_counter
        self._id_counter += 1

        self._send_buf += _make_request(method=method, params=params, id=id)
        self._unanswered_requests[id] = Request(id=id, method=method, params=params)
        return id

    def _send_notification(
        self, method: str, params: t.Optional[JSONDict] = None
    ) -> None:
        self._send_buf += _make_request(method=method, params=params)

    def _send_response(
        self,
        id: Id,
        result: t.Optional[t.Union[JSONDict, JSONList]] = None,
        error: t.Optional[JSONDict] = None,
    ) -> None:
        self._send_buf += _make_response(id=id, result=result, error=error)

    # helpers for structuring common response payload shapes ---------------

    @staticmethod
    def _structure_or_none(
        result: t.Any, cls: t.Any
    ) -> t.Optional[t.Any]:
        """Structure `result` with cattrs; None stays None."""
        if result is None:
            return None
        return structure(result, cls)

    @staticmethod
    def _structure_goto_result(
        result: t.Any,
    ) -> t.Optional[t.Union[lsp.Location, t.List[t.Union[lsp.Location, lsp.LocationLink]]]]:
        """Structure Definition/Declaration/Implementation/TypeDefinition result.

        Per spec it is `Location | Location[] | LocationLink[] | null`;
        disambiguation is done on the 'targetUri' key of LocationLink.
        """
        if result is None:
            return None
        if isinstance(result, list):
            structured = []
            for item in result:
                if isinstance(item, dict) and "targetUri" in item:
                    structured.append(structure(item, lsp.LocationLink))
                else:
                    structured.append(structure(item, lsp.Location))
            return structured
        if isinstance(result, dict) and "targetUri" in result:
            return structure(result, lsp.LocationLink)
        return structure(result, lsp.Location)

    @staticmethod
    def _structure_symbols(result: t.Any) -> t.Optional[
        t.Union[t.List[lsp.SymbolInformation], t.List[lsp.DocumentSymbol]]
    ]:
        """Structure documentSymbol result: DocumentSymbol[] or SymbolInformation[].

        Disambiguation is done on the 'location' key of SymbolInformation.
        """
        if result is None:
            return None
        if not isinstance(result, list):
            raise ValueError(f"bad documentSymbol result: {result!r}")
        if not result:
            return []
        if isinstance(result[0], dict) and "location" in result[0]:
            return structure(result, t.List[lsp.SymbolInformation])
        return structure(result, t.List[lsp.DocumentSymbol])

    # response from server
    def _handle_response(self, response: Response) -> Event:
        assert response.id is not None
        request = self._unanswered_requests.pop(response.id)

        # FIXME: The errors have meanings.
        if response.error is not None:
            # raise RuntimeError("Response error!\n\n" + pprint.pformat(response.error))
            err = ResponseError(
                message_id=response.id,
                code=response.error.get("code", 0),
                message=response.error.get("message", ""),
                data=response.error.get("data"),
            )
            return err

        event: Event

        method = request.method

        if method == "initialize":
            assert self._state == ClientState.WAITING_FOR_INITIALIZED
            self._send_notification(
                "initialized", params={}
            )  # params=None doesn't work with gopls
            self._send_notification("workspace/didChangeConfiguration", params={
                "settings": self.settings
            })
            init_result = structure(response.result, lsp.InitializeResult)
            event = Initialized(capabilities=init_result.capabilities)
            self._state = ClientState.NORMAL

        elif method == "shutdown":
            assert self._state == ClientState.WAITING_FOR_SHUTDOWN
            event = Shutdown()
            self._state = ClientState.SHUTDOWN

        elif method == "textDocument/completion":
            completion_list = None

            if isinstance(response.result, dict):
                completion_list = response.result
            elif isinstance(response.result, list):
                completion_list = {
                    'isIncomplete': 'false',
                    'items': response.result,
                }

            ## ! structuring the completion list is expensive and not really
            ## needed: items are kept as raw dicts (perf optimization).
            event = Completion(
                message_id=response.id, completion_list=completion_list
            )

        elif method == "textDocument/willSaveWaitUntil":
            event = WillSaveWaitUntilEdits(
                edits=self._structure_or_none(response.result, t.List[lsp.TextEdit])
            )

        elif method == "textDocument/hover":
            if response.result is not None:
                hover = structure(response.result, lsp.Hover)
                event = Hover(contents=hover.contents, range=hover.range)
            else:
                event = Hover(contents=[])  # null response
            event.message_id = response.id

        elif method == "textDocument/foldingRange":
            raw = response.result if response.result is not None else []
            event = MFoldingRanges(
                message_id=response.id,
                result=structure(raw, t.List[lsp.FoldingRange]),
            )

        elif method == "textDocument/signatureHelp":
            if response.result is not None:
                sighelp = structure(response.result, lsp.SignatureHelp)
                event = SignatureHelp(
                    signatures=list(sighelp.signatures),
                    active_signature=sighelp.active_signature,
                    active_parameter=sighelp.active_parameter,
                )
            else:
                event = SignatureHelp(signatures=[])  # null response
            event.message_id = response.id

        elif method == "textDocument/documentSymbol":
            raw = response.result if response.result is not None else []
            event = MDocumentSymbols(
                message_id=response.id,
                result=self._structure_symbols(raw),
            )

        elif method == "textDocument/inlayHint":
            event = MInlayHints(
                message_id=response.id,
                result=self._structure_or_none(response.result, t.List[lsp.InlayHint]),
            )

        elif method == "textDocument/rename":
            if response.result is not None and isinstance(response.result, dict):
                if "documentChanges" in response.result:
                    document_changes = [
                        structure(change, lsp.TextDocumentEdit)
                        for change in response.result["documentChanges"]
                    ]
                    event = WorkspaceEdit(
                        message_id=response.id, document_changes=document_changes
                    )
                elif "changes" in response.result:
                    changes = structure(
                        response.result["changes"],
                        t.Dict[str, t.List[lsp.TextEdit]],
                    )
                    event = WorkspaceEdit(
                        message_id=response.id, changes=changes
                    )
                else:
                    event = WorkspaceEdit(message_id=response.id)
            else:
                event = WorkspaceEdit(message_id=response.id)

        elif method == "textDocument/semanticTokens/full":
            if response.result is None:
                event = SemanticTokens(data=[])
            else:
                tokens = structure(response.result, lsp.SemanticTokens)
                event = SemanticTokens(result_id=tokens.result_id, data=list(tokens.data))
            event.message_id = response.id

        #GOTOs
        elif method == "textDocument/definition":
            event = Definition(result=self._structure_goto_result(response.result))
            event.message_id = response.id

        elif method == "textDocument/references":
            event = References(
                result=self._structure_or_none(response.result, t.List[lsp.Location])
            )

        elif method == "textDocument/implementation":
            event = Implementation(result=self._structure_goto_result(response.result))

        elif method == "textDocument/declaration":
            event = Declaration(result=self._structure_goto_result(response.result))

        elif method == "textDocument/typeDefinition":
            event = TypeDefinition(result=self._structure_goto_result(response.result))

        elif method == "textDocument/prepareCallHierarchy":
            event = MCallHierarchItems(
                result=self._structure_or_none(
                    response.result, t.List[lsp.CallHierarchyItem]
                )
            )

        elif method in ("textDocument/formatting", "textDocument/rangeFormatting"):
            event = DocumentFormatting(
                result=self._structure_or_none(response.result, t.List[lsp.TextEdit])
            )

        # WORKSPACE
        elif method == "workspace/symbol":
            event = MWorkspaceSymbols(
                result=self._structure_or_none(
                    response.result, t.List[lsp.SymbolInformation]
                )
            )

        elif method == "o#/metadata":
            metadata_result = response.result if isinstance(response.result, dict) else None
            event = Metadata(message_id=response.id, result=metadata_result)

        else:
            raise NotImplementedError((response, request))

        if isinstance(event, MethodResponse):
            event.message_id = response.id

        return event

    # request from server
    def _handle_request(self, request: Request) -> Event:
        params = request.params if isinstance(request.params, dict) else {}

        def bind_server_request(event: ServerRequest) -> Event:
            assert request.id is not None
            event._id = request.id
            event._client = self
            return event

        if request.method == "workspace/workspaceFolders":
            # We don't need to parse WorkspaceFolders server's request!
            # because according to LSP specs "params: none"
            # Just create empty event and return it
            return bind_server_request(WorkspaceFolders(result=None))

        elif request.method == "workspace/configuration":
            p = structure(params, lsp.ConfigurationParams)
            return bind_server_request(ConfigurationRequest(items=list(p.items)))

        elif request.method == "workspace/projectInitializationComplete":
            return WorkspaceProjectInitializationComplete()

        elif request.method == "window/showMessage":
            p = structure(params, lsp.ShowMessageParams)
            return ShowMessage(type=p.type, message=p.message)

        elif request.method == "window/showMessageRequest":
            p = structure(params, lsp.ShowMessageRequestParams)
            event = ShowMessageRequest(
                type=p.type,
                message=p.message,
                actions=list(p.actions) if p.actions is not None else None,
            )
            return bind_server_request(event)

        elif request.method == "window/logMessage":
            p = structure(params, lsp.LogMessageParams)
            return LogMessage(type=p.type, message=p.message)

        elif request.method == "textDocument/publishDiagnostics":
            p = structure(params, lsp.PublishDiagnosticsParams)
            return PublishDiagnostics(uri=p.uri, diagnostics=list(p.diagnostics))

        elif request.method == "window/workDoneProgress/create":
            token = params.get("token")
            self._progress_tokens_map[token] = WorkDoneProgress
            return bind_server_request(WorkDoneProgressCreate(token=token))

        elif request.method == "client/registerCapability":
            p = structure(params, lsp.RegistrationParams)
            return bind_server_request(
                RegisterCapabilityRequest(registrations=list(p.registrations))
            )

        elif request.method == "$/progress":
            token = params.get("token")
            self._progress_tokens_map.setdefault(token, WorkDoneProgress)

            # if "window/workDoneProgress/create" request from server was missing -
            # pretend it actually was already recieved. i think there is no harm in that.
            # such server bugs must be silently ignored without crashing our plugin.
            value = params.get("value") or {}
            kind = value.get("kind")

            if kind == "begin":
                return WorkDoneProgressBegin(
                    token=token, value=structure(value, lsp.WorkDoneProgressBegin)
                )
            elif kind == "report":
                return WorkDoneProgressReport(
                    token=token, value=structure(value, lsp.WorkDoneProgressReport)
                )
            elif kind == "end":
                self._progress_tokens_map.pop(token, None)  # prevent the dictionary from growing indefinitely.
                return WorkDoneProgressEnd(
                    token=token, value=structure(value, lsp.WorkDoneProgressEnd)
                )
            else:
                raise ValueError(f"Unknown progress kind: {kind}")

        else:
            raise NotImplementedError(request)

    def recv(self, data: bytes) -> t.Iterator[Event]:
        self._recv_buf += data
        # Make sure to use lots of iterators, so that if one message fails to
        # parse, the messages before it are yielded successfully before the
        # error, and the messages after it are left in _recv_buf.
        for message in _parse_messages(self._recv_buf):
            if isinstance(message, Response):
                yield self._handle_response(message)
            else:
                yield self._handle_request(message)

    def send(self) -> bytes:
        send_buf = self._send_buf[:]
        self._send_buf.clear()
        return send_buf

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
