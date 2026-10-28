import enum
import typing as t

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
    ServerNotification,
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
from .io_handler import _make_request, _make_response, _parse_messages
from .structs import (
    CompletionContext,
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    FormattingOptions,
    Id,
    JSONDict,
    JSONList,
    MWorkDoneProgressKind,
    Range,
    Request,
    Response,
    SymbolKind,
    TextDocumentContentChangeEvent,
    TextDocumentEdit,
    TextDocumentIdentifier,
    TextDocumentItem,
    TextDocumentPosition,
    TextDocumentSaveReason,
    TextEdit,
    VersionedTextDocumentIdentifier,
    WorkspaceFolder,
    OptionalVersionedTextDocumentIdentifier,
)
from ._parse_helpers import (
    parse_signature_information,
    parse_text_edit,
    parse_text_edits_list,
    parse_location_or_link_list,
    parse_diagnostic,
    parse_markup_content,
    parse_range,
    parse_location,
)


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
            "completionItemKind": {"valueSet": list(CompletionItemKind)},
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
            "symbolKind": {"valueSet": list(SymbolKind)},
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
            "symbolKind": {"valueSet": list(SymbolKind)},
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
        workspace_folders: t.Optional[t.List[WorkspaceFolder]] = None,
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
                    else [f.to_dict() for f in workspace_folders]
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
        print(f"DEBUG: Sending {method}")

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

    # response from server
    def _handle_response(self, response: Response) -> Event:
        assert response.id is not None
        request = self._unanswered_requests.pop(response.id)

        # DEBUG: Print response
        print(f"DEBUG: method={request.method}, result type={type(response.result)}")
        if response.error:
            print(f"DEBUG: ERROR: {response.error}")
            
        # FIXME: The errors have meanings.
        if response.error is not None:
            err = ResponseError(
                code=response.error.get('code', 0),
                message=response.error.get('message', ''),
                data=response.error.get('data')
            )
            err.message_id = response.id
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
            event = Initialized.from_dict(response.result)
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

            event = Completion(
                message_id=response.id, completion_list=completion_list
            )

        elif method == "textDocument/willSaveWaitUntil":
            edits = parse_text_edits_list(response.result) if response.result else None
            event = WillSaveWaitUntilEdits(edits=edits)

        elif method == "textDocument/hover":
            if response.result is not None:
                # Parse contents - can be string, MarkupContent, MarkedString, or list
                raw_contents = response.result.get('contents', [])
                contents = self._parse_hover_contents(raw_contents)
                
                range_data = response.result.get('range')
                range_obj = parse_range(range_data) if range_data else None
                event = Hover(contents=contents, range=range_obj)
            else:
                event = Hover(contents=[])  # null response
            event.message_id = response.id

        elif method == "textDocument/foldingRange":
            event = MFoldingRanges(
                message_id=response.id,
                result=response.result if response.result is not None else [],
            )

        elif method == "textDocument/signatureHelp":
            if response.result is not None and isinstance(response.result, dict):
                try:
                    sigs = []
                    for s in response.result.get('signatures', []):
                        try:
                            sigs.append(parse_signature_information(s))
                        except Exception:
                            print(f"DEBUG: Failed to parse signature: {e}")
                            # Fallback: create minimal signature
                            from .structs import SignatureInformation
                            sigs.append(SignatureInformation(
                                label=s.get('label', 'unknown') if isinstance(s, dict) else str(s)
                            ))
                    
                    event = SignatureHelp(
                        signatures=sigs,
                        activeSignature=response.result.get('activeSignature'),
                        activeParameter=response.result.get('activeParameter')
                    )
                except Exception as e:
                    # Complete fallback
                    event = SignatureHelp(signatures=[])
            else:
                event = SignatureHelp(signatures=[])  # null response
            event.message_id = response.id

        elif method == "textDocument/documentSymbol":
            event = MDocumentSymbols(
                message_id=response.id,
                result=response.result if response.result is not None else [],
            )

        elif method == "textDocument/inlayHint":
            result_data = response.result if response.result is not None else []
            event = MInlayHints(result=result_data)
            event.message_id = response.id

        elif method == "textDocument/rename":
            if response.result is not None and isinstance(response.result, dict):
                if "documentChanges" in response.result:
                    document_changes = []
                    for change in response.result["documentChanges"]:
                        text_doc = OptionalVersionedTextDocumentIdentifier(
                            uri=change['textDocument']['uri'],
                            version=change['textDocument'].get('version')
                        )
                        edits = [parse_text_edit(e) for e in change['edits']]
                        document_changes.append(
                            TextDocumentEdit(textDocument=text_doc, edits=edits)
                        )
                    event = WorkspaceEdit(
                        message_id=response.id, documentChanges=document_changes
                    )
                elif "changes" in response.result:
                    event = WorkspaceEdit(
                        message_id=response.id, changes=response.result["changes"]
                    )
                else:
                    event = WorkspaceEdit(message_id=response.id)
            else:
                event = WorkspaceEdit(message_id=response.id)

        elif method == "textDocument/semanticTokens/full":
            if response.result is None:
                event = SemanticTokens(data=[])
            else:
                event = SemanticTokens(
                    data=response.result.get('data', []),
                    resultId=response.result.get('resultId')
                )
            event.message_id = response.id

        #GOTOs
        elif method == "textDocument/definition":
            try:
                result = parse_location_or_link_list(response.result)
            except Exception as e:
                print(f"DEBUG: Failed to parse definition: {e}")
                result = None
            event = Definition(result=result)
            event.message_id = response.id

        elif method == "textDocument/references":
            result = None
            try:
                if response.result is not None:
                    if isinstance(response.result, list):
                        result = [parse_location(loc) for loc in response.result]
            except Exception:
                result = None
            event = References(result=result)
            event.message_id = response.id

        elif method == "textDocument/implementation":
            try:
                result = parse_location_or_link_list(response.result)
            except Exception:
                result = None
            event = Implementation(result=result)
            event.message_id = response.id

        elif method == "textDocument/declaration":
            try:
                result = parse_location_or_link_list(response.result)
            except Exception:
                result = None
            event = Declaration(result=result)
            event.message_id = response.id

        elif method == "textDocument/typeDefinition":
            try:
                result = parse_location_or_link_list(response.result)
            except Exception:
                result = None
            event = TypeDefinition(result=result)
            event.message_id = response.id

        elif method == "textDocument/prepareCallHierarchy":
            result = None
            if response.result is not None:
                # Parse CallHierarchyItem list
                from .structs import CallHierarchyItem, SymbolKind
                result = []
                for item_dict in response.result:
                    item = CallHierarchyItem(
                        name=item_dict['name'],
                        kind=SymbolKind(item_dict['kind']),
                        uri=item_dict['uri'],
                        range=parse_range(item_dict['range']),
                        selectionRange=parse_range(item_dict['selectionRange']),
                        tags=item_dict.get('tags'),
                        detail=item_dict.get('detail'),
                        data=item_dict.get('data')
                    )
                    result.append(item)
            event = MCallHierarchItems(result=result)
            event.message_id = response.id

        elif method in ("textDocument/formatting", "textDocument/rangeFormatting"):
            result = parse_text_edits_list(response.result) if response.result else None
            event = DocumentFormatting(result=result)
            event.message_id = response.id

        # WORKSPACE
        elif method == "workspace/symbol":
            result = None
            if response.result is not None:
                # Parse SymbolInformation list
                from .structs import SymbolInformation, SymbolKind
                result = []
                for sym_dict in response.result:
                    sym = SymbolInformation(
                        name=sym_dict['name'],
                        kind=SymbolKind(sym_dict['kind']),
                        location=parse_location(sym_dict['location']),
                        tags=sym_dict.get('tags'),
                        deprecated=sym_dict.get('deprecated'),
                        containerName=sym_dict.get('containerName')
                    )
                    result.append(sym)
            event = MWorkspaceSymbols(result=result)
            event.message_id = response.id

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
        def parse_request(event_cls: t.Type[Event]) -> Event:
            if issubclass(event_cls, ServerRequest):
                params = request.params if isinstance(request.params, dict) else {}
                event = event_cls(**params) if params else event_cls()
                assert request.id is not None
                event._id = request.id
                event._client = self
                return event
            elif issubclass(event_cls, ServerNotification):
                params = request.params if isinstance(request.params, dict) else {}
                return event_cls(**params) if params else event_cls()
            else:
                raise TypeError(
                    "`event_cls` must be a subclass of ServerRequest"
                    " or ServerNotification"
                )

        if request.method == "workspace/workspaceFolders":
            event = WorkspaceFolders(result=None)
            event._id = request.id
            event._client = self
            return event
        elif request.method == "workspace/configuration":
            # Parse ConfigurationItem list
            from .structs import ConfigurationItem
            items = []
            for item_dict in request.params.get('items', []):
                items.append(ConfigurationItem(
                    scopeUri=item_dict.get('scopeUri'),
                    section=item_dict.get('section')
                ))
            event = ConfigurationRequest(items=items)
            event._id = request.id
            event._client = self
            return event
        elif request.method == "workspace/projectInitializationComplete":
            event = parse_request(WorkspaceProjectInitializationComplete)
            assert isinstance(event, WorkspaceProjectInitializationComplete)
            return event
        elif request.method == "window/showMessage":
            from .structs import MessageType
            event = ShowMessage(
                type=MessageType(request.params.get('type', 3)),
                message=request.params.get('message', '')
            )
            return event
        elif request.method == "window/showMessageRequest":
            from .structs import MessageType, MessageActionItem
            actions = None
            if 'actions' in request.params:
                actions = [MessageActionItem(title=a['title']) 
                          for a in request.params['actions']]
            event = ShowMessageRequest(
                type=MessageType(request.params.get('type', 3)),
                message=request.params.get('message', ''),
                actions=actions
            )
            event._id = request.id
            event._client = self
            return event
        elif request.method == "window/logMessage":
            from .structs import MessageType
            event = LogMessage(
                type=MessageType(request.params.get('type', 3)),
                message=request.params.get('message', '')
            )
            return event
        elif request.method == "textDocument/publishDiagnostics":
            try:
                diagnostics = [parse_diagnostic(d) 
                              for d in request.params.get('diagnostics', [])]
            except Exception as e:
                # Fallback: create minimal diagnostics
                diagnostics = []
                for d in request.params.get('diagnostics', []):
                    try:
                        diagnostics.append(parse_diagnostic(d))
                    except Exception:
                        # Skip malformed diagnostic
                        pass
            
            event = PublishDiagnostics(
                uri=request.params.get('uri', ''),
                diagnostics=diagnostics
            )
            return event
        elif request.method == "window/workDoneProgress/create":
            token = request.params.get('token', '')
            self._progress_tokens_map[token] = WorkDoneProgress
            event = WorkDoneProgressCreate(token=token)
            event._id = request.id
            event._client = self
            return event
        elif request.method == "client/registerCapability":
            from .structs import Registration
            registrations = []
            for reg_dict in request.params.get('registrations', []):
                reg = Registration(
                    id=reg_dict['id'],
                    method=reg_dict['method'],
                    registerOptions=reg_dict.get('registerOptions')
                )
                registrations.append(reg)
            event = RegisterCapabilityRequest(registrations=registrations)
            event._id = request.id
            event._client = self
            return event

        elif request.method == "$/progress":
            token = request.params.get('token', '')
            progress_type = self._progress_tokens_map.get(token)
            
            # if "window/workDoneProgress/create" request from server was missing -
            # pretend it actually was already recieved. i think there is no harm in that.
            # such server bugs must be silently ignored without crashing our plugin.
            if progress_type is None:
                # Gracefully handle servers that forget to send workDoneProgress/create
                self._progress_tokens_map[token] = WorkDoneProgress
                progress_type = WorkDoneProgress

            if progress_type == WorkDoneProgress:
                value = request.params.get('value', {})
                kind = value.get('kind', '')
                kind = MWorkDoneProgressKind(kind)

                if kind == MWorkDoneProgressKind.BEGIN:
                    from .structs import WorkDoneProgressBeginValue
                    val = WorkDoneProgressBeginValue(
                        kind=value.get('kind', 'begin'),
                        title=value.get('title', ''),
                        cancellable=value.get('cancellable'),
                        message=value.get('message'),
                        percentage=value.get('percentage')
                    )
                    return WorkDoneProgressBegin(token=token, value=val)
                elif kind == MWorkDoneProgressKind.REPORT:
                    from .structs import WorkDoneProgressReportValue
                    val = WorkDoneProgressReportValue(
                        kind=value.get('kind', 'report'),
                        cancellable=value.get('cancellable'),
                        message=value.get('message'),
                        percentage=value.get('percentage')
                    )
                    return WorkDoneProgressReport(token=token, value=val)
                elif kind == MWorkDoneProgressKind.END:
                    del self._progress_tokens_map[token] # prevent the dictionary from growing indefinitely.
                    from .structs import WorkDoneProgressEndValue
                    val = WorkDoneProgressEndValue(
                        kind=value.get('kind', 'end'),
                        message=value.get('message')
                    )
                    return WorkDoneProgressEnd(token=token, value=val)
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

    def _parse_hover_contents(self, raw_contents):
        """Parse hover contents which can be various formats."""
        from .structs import MarkupContent, MarkupKind, MarkedString
        
        # If it's a string, return as-is
        if isinstance(raw_contents, str):
            return raw_contents
        
        # If it's a dict (MarkupContent or MarkedString)
        if isinstance(raw_contents, dict):
            if 'kind' in raw_contents:
                # MarkupContent
                kind_str = raw_contents.get('kind', 'plaintext')
                kind = MarkupKind.MARKDOWN if kind_str == 'markdown' else MarkupKind.PLAINTEXT
                return MarkupContent(kind=kind, value=raw_contents.get('value', ''))
            elif 'language' in raw_contents:
                # MarkedString
                return MarkedString(
                    language=raw_contents.get('language', ''),
                    value=raw_contents.get('value', '')
                )
            else:
                # Unknown dict format, return as string representation
                return str(raw_contents)
        
        # If it's a list
        if isinstance(raw_contents, list):
            parsed = []
            for item in raw_contents:
                if isinstance(item, str):
                    parsed.append(item)
                elif isinstance(item, dict):
                    if 'kind' in item:
                        kind_str = item.get('kind', 'plaintext')
                        kind = MarkupKind.MARKDOWN if kind_str == 'markdown' else MarkupKind.PLAINTEXT
                        parsed.append(MarkupContent(kind=kind, value=item.get('value', '')))
                    elif 'language' in item:
                        parsed.append(MarkedString(
                            language=item.get('language', ''),
                            value=item.get('value', '')
                        ))
                    else:
                        parsed.append(str(item))
            return parsed
        
        # Fallback
        return []

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

    def did_open(self, text_document: TextDocumentItem) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="textDocument/didOpen",
            params={"textDocument": text_document.to_dict()},
        )

    def did_change(
        self,
        text_document: VersionedTextDocumentIdentifier,
        content_changes: t.List[TextDocumentContentChangeEvent],
    ) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="textDocument/didChange",
            params={
                "textDocument": text_document.to_dict(),
                "contentChanges": [evt.to_dict() for evt in content_changes],
            },
        )

    def did_change_configuration(self, settings: t.Any) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="workspace/didChangeConfiguration", params={"settings": settings}
        )

    def will_save(
        self, text_document: TextDocumentIdentifier, reason: TextDocumentSaveReason
    ) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="textDocument/willSave",
            params={"textDocument": text_document.to_dict(), "reason": reason.value},
        )

    def will_save_wait_until(
        self, text_document: TextDocumentIdentifier, reason: TextDocumentSaveReason
    ) -> None:
        assert self._state == ClientState.NORMAL
        self._send_request(
            method="textDocument/willSaveWaitUntil",
            params={"textDocument": text_document.to_dict(), "reason": reason.value},
        )

    def did_save(
        self, text_document: TextDocumentIdentifier, text: t.Optional[str] = None
    ) -> None:
        assert self._state == ClientState.NORMAL
        params: t.Dict[str, t.Any] = {"textDocument": text_document.to_dict()}
        if text is not None:
            params["text"] = text
        self._send_notification(method="textDocument/didSave", params=params)

    def did_close(self, text_document: TextDocumentIdentifier) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="textDocument/didClose",
            params={"textDocument": text_document.to_dict()},
        )

    def did_change_workspace_folders(
        self, added: t.List[WorkspaceFolder], removed: t.List[WorkspaceFolder]
    ) -> None:
        assert self._state == ClientState.NORMAL
        params = {
            "added": [f.to_dict() for f in added],
            "removed": [f.to_dict() for f in removed],
        }
        self._send_notification(
            method="workspace/didChangeWorkspaceFolders", params=params
        )

    def completion(
        self,
        text_document_position: TextDocumentPosition,
        context: t.Optional[CompletionContext] = None,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {}
        params.update(text_document_position.to_dict())
        if context is not None:
            params.update( {
                'context': context.to_dict(exclude_unset=True)
            } )
        return self._send_request(method="textDocument/completion", params=params)

    def semantic_tokens(
        self,
        text_document: TextDocumentIdentifier,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/semanticTokens/full",
            params={"textDocument": text_document.to_dict()},
        )

    def rename(
        self,
        text_document_position: TextDocumentPosition,
        new_name: str,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {}
        params.update(text_document_position.to_dict())
        params["newName"] = new_name
        return self._send_request(method="textDocument/rename", params=params)

    def hover(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/hover", params=text_document_position.to_dict()
        )

    def folding_range(self, text_document: TextDocumentIdentifier) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/foldingRange",
            params={"textDocument": text_document.to_dict()},
        )

    def signatureHelp(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/signatureHelp",
            params=text_document_position.to_dict(),
        )

    def definition(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/definition", params=text_document_position.to_dict()
        )

    def declaration(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/declaration",
            params=text_document_position.to_dict(),
        )

    def inlay_hint(self, text_document: TextDocumentIdentifier, range: Range) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/inlayHint",
            params={
                "textDocument": text_document.to_dict(),
                "range": range.to_dict(),
            },
        )

    def typeDefinition(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/typeDefinition",
            params=text_document_position.to_dict(),
        )

    def references(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            "context": {"includeDeclaration": True},
            **text_document_position.to_dict(),
        }
        return self._send_request(method="textDocument/references", params=params)

    # TODO incomplete
    def prepareCallHierarchy(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/prepareCallHierarchy",
            params=text_document_position.to_dict(),
        )

    def implementation(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/implementation",
            params=text_document_position.to_dict(),
        )

    def workspace_symbol(self, query: str = "") -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(method="workspace/symbol", params={"query": query})

    def documentSymbol(self, text_document: TextDocumentIdentifier) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/documentSymbol",
            params={"textDocument": text_document.to_dict()},
        )

    def formatting(
        self, text_document: TextDocumentIdentifier, options: FormattingOptions
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            "textDocument": text_document.to_dict(),
            "options": options.to_dict(),
        }
        return self._send_request(method="textDocument/formatting", params=params)

    def rangeFormatting(
        self,
        text_document: TextDocumentIdentifier,
        range: Range,
        options: FormattingOptions,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            "textDocument": text_document.to_dict(),
            "range": range.to_dict(),
            "options": options.to_dict(),
        }
        return self._send_request(method="textDocument/rangeFormatting", params=params)

    def metadata(self, params):
        return self._send_request(method="o#/metadata", params=params)

