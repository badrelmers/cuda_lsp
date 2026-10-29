import enum
import typing as t

import lsprotocol.types as lsp_types
from lsprotocol import converters

from .events import (
    Metadata,
    ResponseError,
    ServerNotification,
    ServerRequest,
)
from .io_handler import _make_request, _make_response, _parse_messages
from .structs import (
    Id,
    JSONDict,
    JSONList,
    Request,
    unstructure,
)

lsp_converter = converters.get_converter()

class ClientState(enum.Enum):
    NOT_INITIALIZED = enum.auto()
    WAITING_FOR_INITIALIZED = enum.auto()
    NORMAL = enum.auto()
    WAITING_FOR_SHUTDOWN = enum.auto()
    SHUTDOWN = enum.auto()
    EXITED = enum.auto()

CAPABILITIES: JSONDict = {
    "textDocument": {
        "synchronization": {
            "didSave": True,
            "dynamicRegistration": True,
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
                    "labelOffsetSupport": True
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
        "showMessage": {},
        "workDoneProgress": True,
    },
    "workspace": {
        "symbol": {
            "dynamicRegistration": True,
            "symbolKind": {"valueSet": list(lsp_types.SymbolKind)},
        },
        "workspaceFolders": True,
        "configuration": True,
        "didChangeConfiguration": {"dynamicRegistration": True},
    },
}


class Client:
    def __init__(
        self,
        process_id: t.Optional[int] = None,
        root_uri: t.Optional[str] = None,
        workspace_folders: t.Optional[t.List[lsp_types.WorkspaceFolder]] = None,
        trace: str = "off",
        settings = {},
    ) -> None:
        self._state = ClientState.NOT_INITIALIZED
        self._recv_buf = bytearray()
        self._send_buf = bytearray()
        self._unanswered_requests: t.Dict[Id, Request] = {}
        self._id_counter = 0
        self._progress_tokens_map: t.Dict[lsp_types.ProgressToken, t.Type] = {}

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

    def _handle_response(self, response: t.Any) -> t.Any:
        response_id = response.get('id')
        assert response_id is not None
        
        request = self._unanswered_requests.pop(response_id)
        method = request.method
        
        # 1. Standard Error Handling
        error_payload = response.get('error')
        if error_payload is not None:
            err = ResponseError(
                code=error_payload.get("code"),
                message=error_payload.get("message", ""),
                data=error_payload.get("data"),
            )
            err.message_id = response_id
            return err
        
        # 2. Initialization & State Logic
        if method == "initialize":
            assert self._state == ClientState.WAITING_FOR_INITIALIZED
            self._send_notification("initialized", params={})
            self._send_notification(
                "workspace/didChangeConfiguration",
                params={"settings": self.settings},
            )
            self._state = ClientState.NORMAL
            event = lsp_converter.structure(response, lsp_types.InitializeResponse)
            
        elif method == "shutdown":
            assert self._state == ClientState.WAITING_FOR_SHUTDOWN
            self._state = ClientState.SHUTDOWN
            event = lsp_converter.structure(response, lsp_types.ShutdownResponse)
            
        elif method == "textDocument/completion":
            event = lsp_converter.structure(response, lsp_types.CompletionResponse)
            # Custom override for list wrapping
            if isinstance(response.get('result'), list):
                if hasattr(event, 'result'):
                    event.result = lsp_types.CompletionList(
                        is_incomplete=False,
                        items=response.get('result')
                    )
                    
        elif method == "o#/metadata":
            # Purely custom non-LSP method
            event = Metadata(message_id=response_id, result=response.get('result'))
            
        # 3. Use METHOD_TO_TYPES for all other standard LSP methods
        elif method in lsp_types.METHOD_TO_TYPES:
            response_cls = lsp_types.METHOD_TO_TYPES[method]
            event = lsp_converter.structure(response, response_cls)
            
        # 4. If it's not a special case AND not in the LSP registry, CRASH
        else:
            raise NotImplementedError(f"Unhandled method: {method}. Response: {response}")
        
        # Ensure message_id is attached if the event supports it
        if hasattr(event, 'message_id'):
            event.message_id = response_id
        
        return event

    def _handle_request(self, request: t.Any) -> t.Any:
        method = request.get('method')
        params = request.get('params') or {}
        request_id = request.get('id')

        # Server requests using lsprotocol types directly
        if method == "workspace/workspaceFolders":
            event = lsp_converter.structure(request, lsp_types.WorkspaceFoldersRequest)
            event._client = self
            return event
            
        elif method == "workspace/configuration":
            event = lsp_converter.structure(request, lsp_types.ConfigurationRequest)
            event._client = self
            return event
            
        elif method == "window/showMessage":
            event = lsp_converter.structure(request, lsp_types.ShowMessageRequest)
            event._client = self
            return event
            
        elif method == "window/showMessageRequest":
            event = lsp_converter.structure(request, lsp_types.ShowMessageRequest)
            event._client = self
            return event
            
        elif method == "window/logMessage":
            event = lsp_converter.structure(request, lsp_types.LogMessageNotification)
            return event
            
        elif method == "textDocument/publishDiagnostics":
            event = lsp_converter.structure(request, lsp_types.PublishDiagnosticsNotification)
            return event
            
        elif method == "window/workDoneProgress/create":
            token = params.get('token')
            if token is not None:
                self._progress_tokens_map[token] = lsp_types.WorkDoneProgress
            event = lsp_converter.structure(request, lsp_types.WorkDoneProgressCreateRequest)
            event._client = self
            return event
            
        elif method == "client/registerCapability":
            event = lsp_converter.structure(request, lsp_types.RegisterCapabilityRequest)
            event._client = self
            return event
            
        elif method == "$/progress":
            token = params.get('token')
            value = params.get('value', {})
            kind_str = value.get('kind')
            
            if kind_str == 'begin':
                event = lsp_converter.structure(request, lsp_types.ProgressNotification)
            elif kind_str == 'report':
                event = lsp_converter.structure(request, lsp_types.ProgressNotification)
            elif kind_str == 'end':
                if token in self._progress_tokens_map:
                    del self._progress_tokens_map[token]
                event = lsp_converter.structure(request, lsp_types.ProgressNotification)
            else:
                raise ValueError(f"Unknown progress kind: {kind_str}")
            return event
            
        else:
            raise NotImplementedError(f"Unhandled server request: {method}")

    def recv(self, data: bytes) -> t.Iterator[t.Tuple[t.Optional[Id], t.Any]]:
        self._recv_buf += data
        for message in _parse_messages(self._recv_buf):
            if "method" not in message:
                event = self._handle_response(message)
                yield (message['id'], event)
            else:
                event = self._handle_request(message)
                yield (None, event)
            
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
        self._send_notification(method="exit", params={})
        self._state = ClientState.EXITED

    def cancel_last_request(self) -> None:
        self._send_notification(
            method="$/cancelRequest", params={"id": self._id_counter - 1}
        )

    def did_open(self, text_document: lsp_types.TextDocumentItem) -> None:
        assert self._state == ClientState.NORMAL
        td_dict = unstructure(text_document)
        self._send_notification(
            method="textDocument/didOpen",
            params={"textDocument": td_dict},
        )

    def did_change(
        self,
        text_document: lsp_types.VersionedTextDocumentIdentifier,
        content_changes: t.List[t.Union[
            lsp_types.TextDocumentContentChangePartial,
            lsp_types.TextDocumentContentChangeWholeDocument
        ]],
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
        self, text_document: lsp_types.TextDocumentIdentifier, reason: lsp_types.TextDocumentSaveReason
    ) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="textDocument/willSave",
            params={"textDocument": unstructure(text_document), "reason": reason.value},
        )

    def will_save_wait_until(
        self, text_document: lsp_types.TextDocumentIdentifier, reason: lsp_types.TextDocumentSaveReason
    ) -> None:
        assert self._state == ClientState.NORMAL
        self._send_request(
            method="textDocument/willSaveWaitUntil",
            params={"textDocument": unstructure(text_document), "reason": reason.value},
        )

    def did_save(
        self, text_document: lsp_types.TextDocumentIdentifier, text: t.Optional[str] = None
    ) -> None:
        assert self._state == ClientState.NORMAL
        params: t.Dict[str, t.Any] = {"textDocument": unstructure(text_document)}
        if text is not None:
            params["text"] = text
        self._send_notification(method="textDocument/didSave", params=params)

    def did_close(self, text_document: lsp_types.TextDocumentIdentifier) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="textDocument/didClose",
            params={"textDocument": unstructure(text_document)},
        )

    def did_change_workspace_folders(
        self, added: t.List[lsp_types.WorkspaceFolder], removed: t.List[lsp_types.WorkspaceFolder]
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
        text_document_position: lsp_types.TextDocumentPositionParams,
        context: t.Optional[lsp_types.CompletionContext] = None,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {}
        params.update(unstructure(text_document_position))
        if context is not None:
            params.update({'context': unstructure(context)})
        return self._send_request(method="textDocument/completion", params=params)

    def semantic_tokens(
        self,
        text_document: lsp_types.TextDocumentIdentifier,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/semanticTokens/full",
            params={"textDocument": unstructure(text_document)},
        )

    def rename(
        self,
        text_document_position: lsp_types.TextDocumentPositionParams,
        new_name: str,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            **unstructure(text_document_position),
            "newName": new_name,
        }
        return self._send_request(method="textDocument/rename", params=params)

    def hover(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/hover", params=unstructure(text_document_position)
        )

    def folding_range(self, text_document: lsp_types.TextDocumentIdentifier) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/foldingRange",
            params={"textDocument": unstructure(text_document)},
        )

    def signatureHelp(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/signatureHelp",
            params=unstructure(text_document_position),
        )

    def definition(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/definition", params=unstructure(text_document_position)
        )

    def declaration(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/declaration",
            params=unstructure(text_document_position),
        )

    def inlay_hint(self, text_document: lsp_types.TextDocumentIdentifier, range: lsp_types.Range) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/inlayHint",
            params={
                "textDocument": unstructure(text_document),
                "range": unstructure(range),
            },
        )

    def typeDefinition(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/typeDefinition",
            params=unstructure(text_document_position),
        )

    def references(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            "context": {"includeDeclaration": True},
            **unstructure(text_document_position),
        }
        return self._send_request(method="textDocument/references", params=params)

    def prepareCallHierarchy(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/prepareCallHierarchy",
            params=unstructure(text_document_position),
        )

    def implementation(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/implementation",
            params=unstructure(text_document_position),
        )

    def workspace_symbol(self, query: str = "") -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(method="workspace/symbol", params={"query": query})

    def documentSymbol(self, text_document: lsp_types.TextDocumentIdentifier) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/documentSymbol",
            params={"textDocument": unstructure(text_document)},
        )

    def formatting(
        self, text_document: lsp_types.TextDocumentIdentifier, options: lsp_types.FormattingOptions
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {
            "textDocument": unstructure(text_document),
            "options": unstructure(options),
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
            "textDocument": unstructure(text_document),
            "range": unstructure(range),
            "options": unstructure(options),
        }
        return self._send_request(method="textDocument/rangeFormatting", params=params)

    def metadata(self, params):
        return self._send_request(method="o#/metadata", params=params)
