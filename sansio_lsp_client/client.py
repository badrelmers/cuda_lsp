import enum
#import pprint
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
    TextDocumentContentChangeEvent,
    CompletionList,
    Converter,
    FormattingOptions,
    Id,
    JSONDict,
    JSONList,
    MWorkDoneProgressKind,
    Range,
    Request,
    Response,
    SymbolKind,
    TextDocumentEdit,
    TextDocumentIdentifier,
    TextDocumentItem,
    TextDocumentPosition,
    TextDocumentSaveReason,
    TextEdit,
    VersionedTextDocumentIdentifier,
    WorkspaceFolder,
    unstructure,
)
from attrs import define
@define
class DefinitionEvent:
    result: Definition


def _structure_location_result(result):
    """Convert raw dict result to Location/LocationLink objects."""
    from .structs import Location, LocationLink
    
    if result is None:
        return None
    elif isinstance(result, list):
        structured = []
        for item in result:
            if 'targetUri' in item:  # LocationLink
                structured.append(Converter.structure(item, LocationLink))
            else:  # Location
                structured.append(Converter.structure(item, Location))
        return structured
    else:
        # Single Location
        return Converter.structure(result, Location)


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
    def _handle_response(self, response: Response) -> Event:
        assert response.id is not None
        request = self._unanswered_requests.pop(response.id)

        # FIXME: The errors have meanings.
        if response.error is not None:
            err = ResponseError(
                code=response.error.get("code"),
                message=response.error.get("message", ""),
                data=response.error.get("data"),
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
            self._send_notification(
                "workspace/didChangeConfiguration",
                params={"settings": self.settings},
            )
            event = Initialized(capabilities=response.result or {})
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
                    "isIncomplete": False,
                    "items": response.result,
                }

            event = Completion(message_id=response.id, completion_list=completion_list)

        elif method == "textDocument/willSaveWaitUntil":
            edits = None
            if isinstance(response.result, list):
                edits = [
                    Converter.structure(entry, TextEdit) for entry in response.result
                ]
            event = WillSaveWaitUntilEdits(edits=edits)

        elif method == "textDocument/hover":
            if response.result is not None:
                event = Converter.structure(response.result, Hover)
            else:
                event = Hover(contents=[])  # null response
            # event.message_id = response.id

        elif method == "textDocument/foldingRange":
            event = MFoldingRanges(
                message_id=response.id,
                result=response.result if response.result is not None else [],
            )

        elif method == "textDocument/signatureHelp":
            if response.result is not None:
                event = Converter.structure(response.result, SignatureHelp)
            else:
                event = SignatureHelp(signatures=[])  # null response
            event.message_id = response.id

        elif method == "textDocument/documentSymbol":
            event = MDocumentSymbols(
                message_id=response.id,
                result=response.result if response.result is not None else [],
            )

        elif method == "textDocument/inlayHint":
            event = Converter.structure(response.result or [], MInlayHints)
            event.message_id = response.id

        elif method == "textDocument/rename":
            if response.result is not None and isinstance(response.result, dict):
                if "documentChanges" in response.result:
                    document_changes = [
                        Converter.structure(change, TextDocumentEdit)
                        for change in response.result["documentChanges"]
                    ]
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
                event = Converter.structure(response.result, SemanticTokens)
            event.message_id = response.id

        #GOTOs
        elif method == "textDocument/definition":
            # event = Definition(result=response.result)
            # event.message_id = response.id
            print("=================definition response.result",response.result)
            print("=================definition response",response)
            
            from lsprotocol.types import Definition
            from lsprotocol.converters import get_converter
            converter = get_converter()
            #event = Converter.structure(response.result, Definition)
            #lsp_converter = get_converter()
            #event = lsp_converter.structure(response.result, Definition)


            #event = Converter.structure({"result": response.result}, DefinitionEvent)
            
                        
            import attrs
            import lsprotocol.types as lsp_types
            from lsprotocol.types import DefinitionResponse,DefinitionResult
            
            

            
            
            
            #error
            #event = converter.structure(response, DefinitionResponse)
            
            
            #no error but doble json!!
            #event = DefinitionResponse(response)
            #print("event",event)
            
            
            #no error but gave a diferent result than what we need because we still pass nested dict 
            #event = DefinitionResponse(id=response.id, result=response.result, jsonrpc=response.jsonrpc)
            #print("event",event)
            
            #error
            #event = DefinitionResponse(
                #id=response.id, 
                #result=converter.structure(response.result, DefinitionResult)
            #)
            
            
            #error
            #event=converter.structure(response.result, DefinitionResult)




            #attr.exceptions.NotAnAttrsClassError: <class 'list'> is not an attrs-decorated class.
            #vvv = attrs.asdict(response.result)
            #event=converter.structure(vvv, DefinitionResult)
            #print("event55555",event)




            #AttributeError: 'list' object has no attribute 'dict'
            #vvv = response.result.dict()
            #event=converter.structure(vvv, DefinitionResult)
            #print("event6666666",event)
            
            
            #_________________________________________________
            
            #all this do not work because attrs.resolve_types() is designed to work on classes (decorated with @attrs.define). It fails on things like DefinitionResult because those are Type Aliases (Unions), not classes. we cannot "resolve" a Union directly; you can only resolve the classes that the Union points to.
            
            # cattrs.errors.StructureHandlerNotFoundError: Unsupported type: typing.Union[ForwardRef('Location'), typing.Sequence[ForwardRef('Location')], typing.Sequence[ForwardRef('LocationLink')], NoneType]. Register a structure hook for it.
            import lsprotocol.types as lsp_types
            import attrs
            '''
            # Force lsprotocol to resolve its internal string refs
            attrs.resolve_types(lsp_types.Location)
            attrs.resolve_types(lsp_types.LocationLink)
            # Now try structuring
            event = converter.structure(response.result, lsp_types.DefinitionResult)
            print("event888888",event)
            '''
                        


            #TypeError: typing.Union[ForwardRef('Location'), typing.Sequence[ForwardRef('Location')]] is not a module, class, method, or function.
            '''
            attrs.resolve_types(lsp_types.Definition)
            attrs.resolve_types(lsp_types.DefinitionLink)
            # Now try structuring
            event = converter.structure(response.result, lsp_types.DefinitionResult)
            print("event888888",event)
            '''
            
                        
            
            # TypeError: typing.Union[ForwardRef('Location'), typing.Sequence[ForwardRef('Location')], typing.Sequence[ForwardRef('LocationLink')], NoneType] is not a module, class, method, or function.
            '''
            attrs.resolve_types(lsp_types.DefinitionResult)
            # Now try structuring
            event = converter.structure(response.result, lsp_types.DefinitionResult)
            print("event888888",event)
            '''
            
            
            
            #cattrs.errors.StructureHandlerNotFoundError: Unsupported type: typing.Union[ForwardRef('Location'), typing.Sequence[ForwardRef('Location')], typing.Sequence[ForwardRef('LocationLink')], NoneType]. Register a structure hook for it.  
            '''      
            from lsprotocol.types import Location, LocationLink
            
            # Manually tell the converter: "When you see the string 'Location', use this class"
            # This bypasses the need for resolve_types entirely.
            converter.register_structure_hook("Location", lambda d, _: converter.structure(d, Location))
            converter.register_structure_hook("LocationLink", lambda d, _: converter.structure(d, LocationLink))
            
            # Now this should work
            event = converter.structure(response.result, lsp_types.DefinitionResult)
            '''
            
            
            
            #work but return direcly the link , we will have to change langua&ge.py
            # it returns [file:///f:/_bin/_binz/_ide/_CudaText/_tools/_LSP/_python/python-lsp-server/PY38embed_x64_NoTclTk/_/lib/site-packages/attrs/__init__.py:14:4-14:9]
            #event = converter.structure(response.result, t.List[lsp_types.Location])
            #print("event",event)
            
            

            #cattrs.errors.StructureHandlerNotFoundError: Unsupported type: typing.Union[ForwardRef('Location'), typing.Sequence[ForwardRef('Location')], typing.Sequence[ForwardRef('LocationLink')], NoneType]. Register a structure hook for it.
            '''
            from typing import  Sequence, Union
            DefinitionResult = Union[lsp_types.Definition, Sequence[lsp_types.DefinitionLink], None]
            event = converter.structure(response.result, DefinitionResult)
            print("event",event)
            '''
            

            # cattrs.errors.StructureHandlerNotFoundError: Unsupported type: typing.Union[ForwardRef('Location'), typing.Sequence[ForwardRef('Location')], typing.Sequence[ForwardRef('LocationLink')], NoneType]. Register a structure hook for it.
            '''
            from typing import  Sequence, Union
            attrs.resolve_types(lsp_types.Location)
            attrs.resolve_types(lsp_types.LocationLink)
            DefinitionResult = Union[lsp_types.Definition, Sequence[lsp_types.DefinitionLink], None]
            event = converter.structure(response.result, DefinitionResult)
            print("event",event)
            '''

            
                        
            # cattrs.errors.StructureHandlerNotFoundError: Unsupported type: typing.Union[ForwardRef('Location'), typing.Sequence[ForwardRef('Location')], typing.Sequence[ForwardRef('LocationLink')], NoneType]. Register a structure hook for it.
            '''
            # You have to resolve the CLASS that uses the types, not the Union itself
            attrs.resolve_types(lsp_types.DefinitionResponse, globalns=lsp_types.__dict__) 
            # Now the converter might (maybe, on 3.8) see through the Union
            event = converter.structure(response.result, lsp_types.DefinitionResult)
            '''
            
            
            
            #gooooooooooooooooooood
            '''
            #attrs.resolve_types(DefinitionResponse, globalns=lsp_types.__dict__)
            #or simply 
            attrs.resolve_types(DefinitionResponse)

            raw_data = {
                "id": response.id,
                "result": response.result,
                "jsonrpc": getattr(response, 'jsonrpc', '2.0')
            }
            event = converter.structure(raw_data, DefinitionResponse)
            print("===event",event)
            '''
            
            
            # TypeError: argument of type 'Response' is not iterable
            '''
            attrs.resolve_types(DefinitionResponse)
            event = converter.structure(response, DefinitionResponse)
            print("===event",event)
            '''
            
            
            
            raw_data = {
                "id": response.id,
                "result": response.result,
                "jsonrpc": getattr(response, 'jsonrpc', '2.0')
            }
            print("111111",type(raw_data),raw_data)
            print("222222",type(response),response)
          
            
            #________________________________________________________
            
            #gooooooooooooood
            '''
            # 1. Convert your 'Response' object to a plain Python dictionary      
            raw_data = attrs.asdict(response)
            # 2. Structure that dictionary into the lsprotocol class
            event = converter.structure(raw_data, DefinitionResponse) 
            #print("event77777",event)
            '''


            #error:
            '''
            ccc = _structure_location_result(response.result)
            print("____ccc",ccc)

            event = Definition(result=ccc)
            print("____event",event)
            '''



        elif method == "textDocument/references":
            event = References(result=response.result)

        elif method == "textDocument/implementation":
            event = Implementation(result=response.result)

        elif method == "textDocument/declaration":
            event = Declaration(result=response.result)

        elif method == "textDocument/typeDefinition":
            event = TypeDefinition(result=response.result)

        elif method == "textDocument/prepareCallHierarchy":
            event = MCallHierarchItems(result=response.result)

        elif method in ("textDocument/formatting", "textDocument/rangeFormatting"):
            event = DocumentFormatting(result=response.result)

        # WORKSPACE
        elif method == "workspace/symbol":
            event = MWorkspaceSymbols(result=response.result)

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
                params = request.params or {}
                event = Converter.structure(params, event_cls)
                assert request.id is not None
                event._id = request.id
                event._client = self
                return event
            if issubclass(event_cls, ServerNotification):
                params = request.params or {}
                return Converter.structure(params, event_cls)
            raise TypeError(
                "`event_cls` must be a subclass of ServerRequest or ServerNotification"
            )

        if request.method == "workspace/workspaceFolders":
            # return parse_request(WorkspaceFolders)
            # ... We don't need to parse WorkspaceFolders server's request!
            # because according to LSP specs "params: none"
            # Just create empty event and return it
            event = WorkspaceFolders(result=None)
            event._id = request.id
            event._client = self
            return event
        elif request.method == "workspace/configuration":
            event = parse_request(ConfigurationRequest)
            assert isinstance(event, ConfigurationRequest)
            return event
        elif request.method == "workspace/projectInitializationComplete":
            event = parse_request(WorkspaceProjectInitializationComplete)
            assert isinstance(event, WorkspaceProjectInitializationComplete)
            return event
        elif request.method == "window/showMessage":
            event = parse_request(ShowMessage)
            assert isinstance(event, ShowMessage)
            return event
        elif request.method == "window/showMessageRequest":
            event = parse_request(ShowMessageRequest)
            assert isinstance(event, ShowMessageRequest)
            return event
        elif request.method == "window/logMessage":
            event = parse_request(LogMessage)
            assert isinstance(event, LogMessage)
            return event
        elif request.method == "textDocument/publishDiagnostics":
            event = parse_request(PublishDiagnostics)
            assert isinstance(event, PublishDiagnostics)
            return event
        elif request.method == "window/workDoneProgress/create":
            ev = parse_request(WorkDoneProgressCreate)
            self._progress_tokens_map[request.params['token']] = WorkDoneProgress
            return parse_request(WorkDoneProgressCreate)
        elif request.method == "client/registerCapability":
            event = parse_request(RegisterCapabilityRequest)
            assert isinstance(event, RegisterCapabilityRequest)
            return event

        elif request.method == "$/progress":
            progress_type = self._progress_tokens_map.get(request.params['token'])
            
            # if "window/workDoneProgress/create" request from server was missing -
            # pretend it actually was already recieved. i think there is no harm in that.
            # such server bugs must be silently ignored without crashing our plugin.
            if progress_type is None:
                # Gracefully handle servers that forget to send workDoneProgress/create
                self._progress_tokens_map[request.params['token']] = WorkDoneProgress
                progress_type = WorkDoneProgress

            if progress_type == WorkDoneProgress:
                kind = request.params['value']['kind']
                kind = MWorkDoneProgressKind(kind)

                if kind == MWorkDoneProgressKind.BEGIN:
                    return parse_request(WorkDoneProgressBegin)
                elif kind == MWorkDoneProgressKind.REPORT:
                    return parse_request(WorkDoneProgressReport)
                elif kind == MWorkDoneProgressKind.END:
                    del self._progress_tokens_map[request.params["token"]] # prevent the dictionary from growing indefinitely.
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
        print("NOTE: client recv",data)
        for message in _parse_messages(self._recv_buf):
            print("NOTE: client parsed",message)
            if isinstance(message, Response):
                event = self._handle_response(message)
                yield (message.id, event)
            else:
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

    def did_open(self, text_document: TextDocumentItem) -> None:
        assert self._state == ClientState.NORMAL
        td_dict = unstructure(text_document)
        print(f"DEBUG did_open: uri={td_dict.get('uri')}, languageId={td_dict.get('languageId')}")
        print(f"DEBUG did_open: unstructured type = {type(td_dict)}")
        print(f"DEBUG did_open: text length = {len(td_dict.get('text', ''))}")
        self._send_notification(
            method="textDocument/didOpen",
            params={"textDocument": td_dict},
        )


    def did_change(
        self,
        text_document: VersionedTextDocumentIdentifier,
        content_changes: t.List[TextDocumentContentChangeEvent],
    ) -> None:
        assert self._state == ClientState.NORMAL
        content_changes_payload = [unstructure(evt) for evt in content_changes]
        self._send_notification(
            method="textDocument/didChange",
            params={
                "textDocument": unstructure(text_document),
                "contentChanges": content_changes_payload,
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
            params={"textDocument": unstructure(text_document), "reason": reason.value},
        )

    def will_save_wait_until(
        self, text_document: TextDocumentIdentifier, reason: TextDocumentSaveReason
    ) -> None:
        assert self._state == ClientState.NORMAL
        self._send_request(
            method="textDocument/willSaveWaitUntil",
            params={"textDocument": unstructure(text_document), "reason": reason.value},
        )

    def did_save(
        self, text_document: TextDocumentIdentifier, text: t.Optional[str] = None
    ) -> None:
        assert self._state == ClientState.NORMAL
        params: t.Dict[str, t.Any] = {"textDocument": unstructure(text_document)}
        if text is not None:
            params["text"] = text
        self._send_notification(method="textDocument/didSave", params=params)

    def did_close(self, text_document: TextDocumentIdentifier) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="textDocument/didClose",
            params={"textDocument": unstructure(text_document)},
        )

    def did_change_workspace_folders(
        self, added: t.List[WorkspaceFolder], removed: t.List[WorkspaceFolder]
    ) -> None:
        assert self._state == ClientState.NORMAL
        params = {
            "added": [unstructure(f) for f in added],
            "removed": [unstructure(f) for f in removed],
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
        params.update(unstructure(text_document_position))
        if context is not None:
            params.update( {
                'context': unstructure(context)
            } )
        return self._send_request(method="textDocument/completion", params=params)

    def semantic_tokens(
        self,
        text_document: TextDocumentIdentifier,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/semanticTokens/full",
            params={"textDocument": unstructure(text_document)},
        )

    def rename(
        self,
        text_document_position: TextDocumentPosition,
        new_name: str,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            **unstructure(text_document_position),
            "newName": new_name,
        }
        return self._send_request(method="textDocument/rename", params=params)

    def hover(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/hover", params=unstructure(text_document_position)
        )

    def folding_range(self, text_document: TextDocumentIdentifier) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/foldingRange",
            params={"textDocument": text_document.model_dump()},
        )

    def signatureHelp(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/signatureHelp",
            params=unstructure(text_document_position),
        )

    def definition(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/definition", params=unstructure(text_document_position)
        )

    def declaration(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/declaration",
            params=text_document_position.model_dump(),
        )

    def inlay_hint(self, text_document: TextDocumentIdentifier, range: Range) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/inlayHint",
            params={
                "textDocument": unstructure(text_document),
                "range": unstructure(range),
            },
        )

    def typeDefinition(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/typeDefinition",
            params=unstructure(text_document_position),
        )

    def references(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            "context": {"includeDeclaration": True},
            **unstructure(text_document_position),
        }
        return self._send_request(method="textDocument/references", params=params)

    # TODO incomplete
    def prepareCallHierarchy(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/prepareCallHierarchy",
            params=unstructure(text_document_position),
        )

    def implementation(self, text_document_position: TextDocumentPosition) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/implementation",
            params=unstructure(text_document_position),
        )

    def workspace_symbol(self, query: str = "") -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(method="workspace/symbol", params={"query": query})

    def documentSymbol(self, text_document: TextDocumentIdentifier) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/documentSymbol",
            params={"textDocument": unstructure(text_document)},
        )

    def formatting(
        self, text_document: TextDocumentIdentifier, options: FormattingOptions
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            "textDocument": unstructure(text_document),
            "options": unstructure(options),
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
            "textDocument": unstructure(text_document),
            "range": unstructure(range),
            "options": unstructure(options),
        }
        return self._send_request(method="textDocument/rangeFormatting", params=params)

    def metadata(self, params):
        return self._send_request(method="o#/metadata", params=params)

