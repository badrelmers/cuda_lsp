import enum
#import pprint
import typing as t
import attrs
from .events import (
    Completion,
    ConfigurationRequest,
    Event,
    Initialized,
    LogMessage,
    MCallHierarchItems,
    MDocumentSymbols,
    MFoldingRanges,
    MInlayHints,
    Metadata,
    MWorkspaceSymbols,
    Progress,
    PublishDiagnostics,
    RegisterCapabilityRequest,
    ResponseError,
    SemanticTokens,
    ServerNotification,
    ServerRequest,
    ShowMessage,
    ShowMessageRequest,
    Shutdown,
    SignatureHelp,
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
from .io_handler import _make_request, _make_response, _parse_messages
from .structs import (
    Id,
    JSONDict,
    JSONList,
    Request,
)
from lsprotocol import converters, types as lsp_types
Converter = converters.get_converter()


# This manually links all strings to their classes within the library itself
# so you never have to think about it again. this is not needed anymore because now we use directly response calsses from lsprotocol like DefinitionResponse which automatically resolve the quoted types. it may be needed only by things like DefinitionResult...etc
# for name, obj in lsp_types.__dict__.items():
    # if isinstance(obj, type) and attrs.has(obj):
        # attrs.resolve_types(obj, globalns=lsp_types.__dict__)
        
    
class ClientState(enum.Enum):
    NOT_INITIALIZED = enum.auto()
    WAITING_FOR_INITIALIZED = enum.auto()
    NORMAL = enum.auto()
    WAITING_FOR_SHUTDOWN = enum.auto()
    SHUTDOWN = enum.auto()
    EXITED = enum.auto()

#NOTE: Server capabilitie: resolveProvider - info about completion item -- can't use?
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
            "tagSupport": {"valueSet": [1,2]}
        },
        "completion": {
            "dynamicRegistration": True,
            "completionItem": {"snippetSupport": True},
            "completionItemKind": {"valueSet": list(lsp_types.CompletionItemKind)},
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
            "symbolKind": {"valueSet": list(lsp_types.SymbolKind)},
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
            "symbolKind": {"valueSet": list(lsp_types.SymbolKind)},
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
        workspace_folders: t.Optional[t.List[lsp_types.WorkspaceFolder]] = None,
        trace: str = "off",
        settings = {},
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
                    else [Converter.unstructure(f) for f in workspace_folders]
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
        print(f"DEBUG _send_notification: method={method}")
        if method == "initialized":
            print(f"DEBUG: Sending initialized notification")
        if method == "textDocument/didOpen":
            print(f"DEBUG: Sending didOpen for uri: {params.get('textDocument', {}).get('uri') if params else 'unknown'}")
        self._send_buf += _make_request(method=method, params=params)

    def _send_response(
        self,
        id: Id,
        result: t.Optional[t.Union[JSONDict, JSONList]] = None,
        error: t.Optional[JSONDict] = None,
    ) -> None:
        self._send_buf += _make_response(id=id, result=result, error=error)

    # response from server
    def _handle_response(self, response: t.Any) -> Event:
        # Use .get() to avoid KeyError
        response_id = response.get('id')
        assert response_id is not None
        
        # Pop the matching request using the ID
        request = self._unanswered_requests.pop(response_id)

        # Safely check for error existence
        # FIXME: The errors have meanings.
        error_payload = response.get('error')
        if error_payload is not None:
            err = ResponseError(
                code=error_payload.get("code"),
                message=error_payload.get("message", ""),
                data=error_payload.get("data"),
            )
            err.message_id = response_id
            return err

        event: Event
        method = request.method
        result = response.get('result') # result can be None, list, or dict

        if method == "initialize":
            assert self._state == ClientState.WAITING_FOR_INITIALIZED
            self._send_notification(
              "initialized", params={}
            )  # params=None doesn't work with gopls
            self._send_notification(
                "workspace/didChangeConfiguration",
                params={"settings": self.settings},
            )
            event = Initialized(capabilities=result or {})
            self._state = ClientState.NORMAL

        elif method == "shutdown":
            assert self._state == ClientState.WAITING_FOR_SHUTDOWN
            event = Shutdown()
            self._state = ClientState.SHUTDOWN

        elif method == "textDocument/completion":
            completion_list = None
            if isinstance(result, dict):
                completion_list = result
            elif isinstance(result, list):
                completion_list = {
                    "isIncomplete": False,
                    "items": result,
                }
            event = Completion(message_id=response_id, completion_list=completion_list)

        elif method == "textDocument/willSaveWaitUntil":
            edits = None
            if isinstance(result, list):
                edits = [
                    Converter.structure(entry, lsp_types.TextEdit) for entry in result
                ]
            event = WillSaveWaitUntilEdits(edits=edits)

        elif method == "textDocument/hover":
            # if result is not None:
                # event = Converter.structure(result, Hover)
            # else:
                # event = Hover(contents=[])  # null response
            # event.message_id = response_id
            
            event = Converter.structure(result, lsp_types.Hover)

        elif method == "textDocument/foldingRange":
            event = MFoldingRanges(
                message_id=response_id,
                result=result if result is not None else [],
            )

        elif method == "textDocument/signatureHelp":
            if result is not None:
                event = Converter.structure(result, SignatureHelp)
            else:
                event = SignatureHelp(signatures=[])  # null response
            event.message_id = response_id

        elif method == "textDocument/documentSymbol":
            event = MDocumentSymbols(
                message_id=response_id,
                result=result if result is not None else [],
            )

        elif method == "textDocument/inlayHint":
            event = Converter.structure(result or [], MInlayHints)
            event.message_id = response_id

        elif method == "textDocument/rename":
            if result is not None and isinstance(result, dict):
                if "documentChanges" in result:
                    document_changes = [
                        Converter.structure(change, lsp_types.TextDocumentEdit)
                        for change in result["documentChanges"]
                    ]
                    event = WorkspaceEdit(
                        message_id=response_id, documentChanges=document_changes
                    )
                elif "changes" in result:
                    event = WorkspaceEdit(
                        message_id=response_id, changes=result["changes"]
                    )
                else:
                    event = WorkspaceEdit(message_id=response_id)
            else:
                event = WorkspaceEdit(message_id=response_id)

        elif method == "textDocument/semanticTokens/full":
            if result is None:
                event = SemanticTokens(data=[])
            else:
                event = Converter.structure(result, SemanticTokens)
            event.message_id = response_id

        elif method == "textDocument/definition":
            event = Converter.structure(response, lsp_types.DefinitionResponse)

        elif method == "textDocument/references":
            event = Converter.structure(response, lsp_types.ReferencesResponse)

        elif method == "textDocument/implementation":
            event = Converter.structure(response, lsp_types.ImplementationResponse)

        elif method == "textDocument/declaration":
            event = Converter.structure(response, lsp_types.DeclarationResponse)

        elif method == "textDocument/typeDefinition":
            event = Converter.structure(response, lsp_types.TypeDefinitionResponse)

        elif method == "textDocument/prepareCallHierarchy":
            event = MCallHierarchItems(result=result)

        elif method == "textDocument/formatting":
            event = Converter.structure(response, lsp_types.DocumentFormattingResponse)

        elif method == "textDocument/rangeFormatting":
            event = Converter.structure(response, lsp_types.DocumentRangeFormattingResponse)
        
        # TODO: how this is supposed to work? format multiple selections? add it to cuda lsp
        # elif method == "textDocument/rangesFormatting":
            # event = Converter.structure(response, lsp_types.DocumentRangesFormattingResponse)

        # TODO: add this to cuda lsp
        # elif method == "textDocument/onTypeFormatting":
            # event = Converter.structure(response, lsp_types.DocumentOnTypeFormattingResponse)

        elif method == "workspace/symbol":
            event = MWorkspaceSymbols(result=result)

        elif method == "o#/metadata":
            metadata_result = result if isinstance(result, dict) else None
            event = Metadata(message_id=response_id, result=metadata_result)

        else:
            raise NotImplementedError((response, request))

        return event

    # request from server
    def _handle_request(self, request: t.Any) -> Event:
        # Use .get() for top-level keys
        method = request.get('method')
        params = request.get('params') or {}
        request_id = request.get('id')

        def parse_request(event_cls: t.Type[Event]) -> Event:
            if issubclass(event_cls, ServerRequest):
                # params is already a dict, so Converter works directly
                event = Converter.structure(params, event_cls)
                assert request_id is not None
                event._id = request_id
                event._client = self
                return event
            if issubclass(event_cls, ServerNotification):
                return Converter.structure(params, event_cls)
            raise TypeError(
                "`event_cls` must be a subclass of ServerRequest or ServerNotification"
            )

        if method == "workspace/workspaceFolders":
            # return parse_request(WorkspaceFolders)
            # ... We don't need to parse WorkspaceFolders server's request!
            # because according to LSP specs "params: none"
            # Just create empty event and return it
            event = WorkspaceFolders(result=None)
            event._id = request_id
            event._client = self
            return event
        elif method == "workspace/configuration":
            return parse_request(ConfigurationRequest)
        elif method == "workspace/projectInitializationComplete":
            return parse_request(WorkspaceProjectInitializationComplete)
        elif method == "window/showMessage":
            return parse_request(ShowMessage)
        elif method == "window/showMessageRequest":
            return parse_request(ShowMessageRequest)
        elif method == "window/logMessage":
            return parse_request(LogMessage)
        elif method == "textDocument/publishDiagnostics":
            return parse_request(PublishDiagnostics)
        elif method == "window/workDoneProgress/create":
            
            token = params.get('token') # Safely access nested 'token'
            if token is not None:
                self._progress_tokens_map[token] = WorkDoneProgress
            return parse_request(WorkDoneProgressCreate)
        elif method == "client/registerCapability":
            return parse_request(RegisterCapabilityRequest)

        elif method == "$/progress":
            token = params.get('token')
            progress_type = self._progress_tokens_map.get(token)
            
            # if "window/workDoneProgress/create" request from server was missing -
            # pretend it actually was already recieved. i think there is no harm in that.
            # such server bugs must be silently ignored without crashing our plugin.
            if progress_type is None:
                self._progress_tokens_map[token] = WorkDoneProgress
                # Gracefully handle servers that forget to send workDoneProgress/create
                progress_type = WorkDoneProgress

            if progress_type == WorkDoneProgress:
                # Safely drill into nested kind
                value = params.get('value', {})
                kind = value.get('kind')

                if kind == "begin":
                    return parse_request(WorkDoneProgressBegin)
                elif kind == "report":
                    return parse_request(WorkDoneProgressReport)
                elif kind == "end":
                    if token in self._progress_tokens_map:
                        del self._progress_tokens_map[token] # prevent the dictionary from growing indefinitely.
                    return parse_request(WorkDoneProgressEnd)
                else:
                    raise ValueError(f"Unknown progress kind: {kind}")



        else:
            raise NotImplementedError(request)

    def recv(self, data: bytes) -> t.Iterator[t.Tuple[t.Optional[Id], Event]]:
        """Parse received data and yield (message_id, event) tuples.
        
        Returns:
            Iterator of (message_id, event) tuples where:
            - message_id: The ID from our original request (for responses), or None (for server requests/notifications)
            - event: The parsed Event object
        """
        # Make sure to use lots of iterators, so that if one message fails to
        # parse, the messages before it are yielded successfully before the
        # error, and the messages after it are left in _recv_buf.
        self._recv_buf += data
        for message in _parse_messages(self._recv_buf):
            # Distinguish between Response and Request/Notification
            # In JSON-RPC, if it has 'method', it's NOT a response.
            if "method" not in message:
                # It's a Response.
                event = self._handle_response(message)
                yield (message['id'], event)
            else:
                # It's a Request or Notification.
                event = self._handle_request(message)
                yield (None, event)  # Server requests/notifications don't have our message_id
            
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
        self._send_notification(
            method="$/cancelRequest", params={"id": self._id_counter - 1}
        )

    def did_open(self, text_document: lsp_types.TextDocumentItem) -> None:
        assert self._state == ClientState.NORMAL
        td_dict = Converter.unstructure(text_document)
        print(f"DEBUG did_open: uri={td_dict.get('uri')}, languageId={td_dict.get('languageId')}")
        print(f"DEBUG did_open: unstructured type = {type(td_dict)}")
        print(f"DEBUG did_open: text length = {len(td_dict.get('text', ''))}")
        self._send_notification(
            method="textDocument/didOpen",
            params={"textDocument": td_dict},
        )


    def did_change(
        self,
        text_document: lsp_types.VersionedTextDocumentIdentifier,
        content_changes: t.List[lsp_types.TextDocumentContentChangeEvent],
    ) -> None:
        assert self._state == ClientState.NORMAL
        content_changes_payload = [Converter.unstructure(evt) for evt in content_changes]
        self._send_notification(
            method="textDocument/didChange",
            params={
                "textDocument": Converter.unstructure(text_document),
                "contentChanges": content_changes_payload,
            },
        )

    def did_change_configuration(self, settings: t.Any) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="workspace/didChangeConfiguration", params={"settings": settings}
        )

    def will_save(
        self, text_document: lsp_types.TextDocumentIdentifier, reason: lsp_types.TextDocumentSaveReason
    ) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="textDocument/willSave",
            params={"textDocument": Converter.unstructure(text_document), "reason": reason.value},
        )

    def will_save_wait_until(
        self, text_document: lsp_types.TextDocumentIdentifier, reason: lsp_types.TextDocumentSaveReason
    ) -> None:
        assert self._state == ClientState.NORMAL
        self._send_request(
            method="textDocument/willSaveWaitUntil",
            params={"textDocument": Converter.unstructure(text_document), "reason": reason.value},
        )

    def did_save(
        self, text_document: lsp_types.TextDocumentIdentifier, text: t.Optional[str] = None
    ) -> None:
        assert self._state == ClientState.NORMAL
        params: t.Dict[str, t.Any] = {"textDocument": Converter.unstructure(text_document)}
        if text is not None:
            params["text"] = text
        self._send_notification(method="textDocument/didSave", params=params)

    def did_close(self, text_document: lsp_types.TextDocumentIdentifier) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="textDocument/didClose",
            params={"textDocument": Converter.unstructure(text_document)},
        )

    def did_change_workspace_folders(
        self, added: t.List[lsp_types.WorkspaceFolder], removed: t.List[lsp_types.WorkspaceFolder]
    ) -> None:
        assert self._state == ClientState.NORMAL
        params = {
            "added": [Converter.unstructure(f) for f in added],
            "removed": [Converter.unstructure(f) for f in removed],
        }
        self._send_notification(
            method="workspace/didChangeWorkspaceFolders", params=params
        )

    def completion(
        self,
        text_document_position: lsp_types.TextDocumentPositionParams,
        context: t.Optional[lsp_types.CompletionContext] = None,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {}
        params.update(Converter.unstructure(text_document_position))
        if context is not None:
            params.update( {
                'context': Converter.unstructure(context)
            } )
        return self._send_request(method="textDocument/completion", params=params)

    def semantic_tokens(
        self,
        text_document: lsp_types.TextDocumentIdentifier,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/semanticTokens/full",
            params={"textDocument": Converter.unstructure(text_document)},
        )

    def rename(
        self,
        text_document_position: lsp_types.TextDocumentPositionParams,
        new_name: str,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            **Converter.unstructure(text_document_position),
            "newName": new_name,
        }
        return self._send_request(method="textDocument/rename", params=params)

    def hover(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/hover", params=Converter.unstructure(text_document_position)
        )

    def folding_range(self, text_document: lsp_types.TextDocumentIdentifier) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/foldingRange",
            params={"textDocument": Converter.unstructure(text_document)},
        )

    def signatureHelp(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/signatureHelp",
            params=Converter.unstructure(text_document_position),
        )

    def definition(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/definition", params=Converter.unstructure(text_document_position)
        )

    def declaration(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/declaration",
            params=Converter.unstructure(text_document_position),
        )

    def inlay_hint(self, text_document: lsp_types.TextDocumentIdentifier, range: lsp_types.Range) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/inlayHint",
            params={
                "textDocument": Converter.unstructure(text_document),
                "range": Converter.unstructure(range),
            },
        )

    def typeDefinition(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/typeDefinition",
            params=Converter.unstructure(text_document_position),
        )

    def references(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            "context": {"includeDeclaration": True},
            **Converter.unstructure(text_document_position),
        }
        return self._send_request(method="textDocument/references", params=params)

    # TODO incomplete
    def prepareCallHierarchy(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/prepareCallHierarchy",
            params=Converter.unstructure(text_document_position),
        )

    def implementation(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/implementation",
            params=Converter.unstructure(text_document_position),
        )

    def workspace_symbol(self, query: str = "") -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(method="workspace/symbol", params={"query": query})

    def documentSymbol(self, text_document: lsp_types.TextDocumentIdentifier) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/documentSymbol",
            params={"textDocument": Converter.unstructure(text_document)},
        )

    def formatting(
        self, text_document: lsp_types.TextDocumentIdentifier, options: lsp_types.FormattingOptions
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            "textDocument": Converter.unstructure(text_document),
            "options": Converter.unstructure(options),
        }
        return self._send_request(method="textDocument/formatting", params=params)

    def rangeFormatting(
        self,
        text_document: lsp_types.TextDocumentIdentifier,
        range: lsp_types.Range,
        options: lsp_types.FormattingOptions,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            "textDocument": Converter.unstructure(text_document),
            "range": Converter.unstructure(range),
            "options": Converter.unstructure(options),
        }
        return self._send_request(method="textDocument/rangeFormatting", params=params)

    def metadata(self, params):
        return self._send_request(method="o#/metadata", params=params)

