import enum
import json
import re
import typing as t
import attrs
from lsprotocol import converters, types as lsp_types

Converter = converters.get_converter()

# ============================================================================
# IO Handler (formerly io_handler.py)
# ============================================================================

_CONTENT_TYPE_PARAM_RE = re.compile(r'(\w+)\s*=\s*(?:(?:"([^"]*)")|([^;,\s]*))')

def _make_headers(content_length: int, encoding: str = "utf-8") -> bytes:
    headers_bytes = bytearray()
    headers = {
        "Content-Length": content_length,
        "Content-Type": f"application/vscode-jsonrpc; charset={encoding}",
    }
    for key, value in headers.items():
        headers_bytes += f"{key}: {value}\r\n".encode(encoding)
    headers_bytes += b"\r\n"
    return headers_bytes

def _make_request(
    method: str,
    params: t.Optional[t.Dict[str, t.Any]] = None,
    id: t.Optional[t.Union[int, str]] = None,
    *,
    encoding: str = "utf-8",
) -> bytes:
    request = bytearray()
    content: t.Dict[str, t.Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        content["params"] = params
    if id is not None:
        content["id"] = id
    encoded_content = json.dumps(content).encode(encoding)
    request += _make_headers(content_length=len(encoded_content), encoding=encoding)
    request += encoded_content
    return request

def _make_response(
    id: t.Union[int, str],
    result: t.Optional[t.Union[t.Dict[str, t.Any], t.List[t.Any]]] = None,
    error: t.Optional[t.Dict[str, t.Any]] = None,
    *,
    encoding: str = "utf-8",
) -> bytes:
    request = bytearray()
    content: t.Dict[str, t.Any] = {"jsonrpc": "2.0", "id": id}
    if result is not None:
        content["result"] = result
    if error is not None:
        content["error"] = error
    elif result is None:
        content["result"] = None
    encoded_content = json.dumps(content).encode(encoding)
    request += _make_headers(content_length=len(encoded_content), encoding=encoding)
    request += encoded_content
    return request

def _parse_content_type(header: str) -> t.Tuple[str, t.Dict[str, str]]:
    content_type, _, param_string = header.partition(";")
    content_type = content_type.strip().lower()
    metadata = {
        m.group(1).lower(): (m.group(2) or m.group(3))
        for m in _CONTENT_TYPE_PARAM_RE.finditer(param_string)
    }
    return content_type, metadata

def _parse_one_message(response_buf: bytearray) -> t.Optional[t.Iterable[dict]]:
    if b"\r\n\r\n" not in response_buf:
        return None
    header_lines, raw_content = bytes(response_buf).split(b"\r\n\r\n", 1)
    headers = {"content-type": "application/vscode-jsonrpc; charset=utf-8"}
    for header_line in header_lines.split(b"\r\n"):
        key, value = header_line.decode("ascii").split(": ", 1)
        headers[key.lower()] = value
    assert set(headers.keys()) == {"content-type", "content-length"}
    content_type, metadata = _parse_content_type(headers["content-type"])
    assert content_type == "application/vscode-jsonrpc"
    encoding = metadata["charset"]
    content_length = int(headers["content-length"])
    if len(raw_content) < content_length:
        return None
    unused_bytes_count = len(raw_content) - content_length
    raw_content = raw_content[:content_length]
    if unused_bytes_count == 0:
        response_buf.clear()
    else:
        del response_buf[:-unused_bytes_count]
    content = json.loads(raw_content.decode(encoding))
    if isinstance(content, list):
        return content
    else:
        return [content]

def _parse_messages(response_buf: bytearray) -> t.Optional[t.Iterable[dict]]:
    while True:
        parsed = _parse_one_message(response_buf)
        if parsed is None:
            break
        yield from parsed

# ============================================================================
# Events (formerly events.py) - Now using lsprotocol types
# ============================================================================

@attrs.define
class ResponseError:
    """Custom response error wrapper"""
    code: int = attrs.field()
    message: str = attrs.field()
    data: t.Optional[t.Any] = attrs.field(default=None)
    message_id: t.Optional[t.Union[int, str]] = attrs.field(default=None)

@attrs.define
class Metadata:
    """OmniSharp metadata response"""
    message_id: t.Optional[t.Union[int, str]] = attrs.field(default=None)
    result: t.Optional[t.Dict[str, t.Any]] = attrs.field(default=None)

# ============================================================================
# Client State
# ============================================================================

class ClientState(enum.Enum):
    NOT_INITIALIZED = enum.auto()
    WAITING_FOR_INITIALIZED = enum.auto()
    NORMAL = enum.auto()
    WAITING_FOR_SHUTDOWN = enum.auto()
    SHUTDOWN = enum.auto()
    EXITED = enum.auto()

# ============================================================================
# Client Capabilities
# ============================================================================

CAPABILITIES: t.Dict[str, t.Any] = {
    "textDocument": {
        "synchronization": {
            "didSave": True,
            "dynamicRegistration": True,
        },
        "publishDiagnostics": {
            "relatedInformation": True,
            "tagSupport": {"valueSet": [1, 2]}
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

# ============================================================================
# Main Client Class
# ============================================================================

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
        self._unanswered_requests: t.Dict[t.Union[int, str], t.Dict[str, t.Any]] = {}
        self._id_counter = 0
        self._progress_tokens_map: t.Dict[lsp_types.ProgressToken, type] = {}

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

    def _send_request(self, method: str, params: t.Optional[t.Dict[str, t.Any]] = None) -> t.Union[int, str]:
        id: t.Union[int, str] = self._id_counter
        self._id_counter += 1
        self._send_buf += _make_request(method=method, params=params, id=id)
        self._unanswered_requests[id] = {"id": id, "method": method, "params": params}
        return id

    def _send_notification(self, method: str, params: t.Optional[t.Dict[str, t.Any]] = None) -> None:
        self._send_buf += _make_request(method=method, params=params)

    def _send_response(
        self,
        id: t.Union[int, str],
        result: t.Optional[t.Union[t.Dict[str, t.Any], t.List[t.Any]]] = None,
        error: t.Optional[t.Dict[str, t.Any]] = None,
    ) -> None:
        self._send_buf += _make_response(id=id, result=result, error=error)

    def _handle_response(self, response: t.Any) -> t.Any:
        response_id = response.get('id')
        assert response_id is not None
        request = self._unanswered_requests.pop(response_id)
        error_payload = response.get('error')
        
        if error_payload is not None:
            err = ResponseError(
                code=error_payload.get("code"),
                message=error_payload.get("message", ""),
                data=error_payload.get("data"),
            )
            err.message_id = response_id
            return err

        method = request["method"]
        result = response.get('result')

        if method == "initialize":
            assert self._state == ClientState.WAITING_FOR_INITIALIZED
            self._send_notification("initialized", params={})
            self._send_notification(
                "workspace/didChangeConfiguration",
                params={"settings": self.settings},
            )
            event = Converter.structure(response, lsp_types.InitializeResponse)
            self._state = ClientState.NORMAL
            return event

        elif method == "shutdown":
            assert self._state == ClientState.WAITING_FOR_SHUTDOWN
            self._state = ClientState.SHUTDOWN
            return lsp_types.ShutdownResponse(id=response_id, result=None)

        elif method == "textDocument/completion":
            return Converter.structure(response, lsp_types.CompletionResponse)

        elif method == "textDocument/hover":
            return Converter.structure(response, lsp_types.HoverResponse)

        elif method == "textDocument/signatureHelp":
            return Converter.structure(response, lsp_types.SignatureHelpResponse)

        elif method == "textDocument/definition":
            return Converter.structure(response, lsp_types.DefinitionResponse)

        elif method == "textDocument/references":
            return Converter.structure(response, lsp_types.ReferencesResponse)

        elif method == "textDocument/implementation":
            return Converter.structure(response, lsp_types.ImplementationResponse)

        elif method == "textDocument/declaration":
            return Converter.structure(response, lsp_types.DeclarationResponse)

        elif method == "textDocument/typeDefinition":
            return Converter.structure(response, lsp_types.TypeDefinitionResponse)

        elif method == "textDocument/formatting":
            return Converter.structure(response, lsp_types.DocumentFormattingResponse)

        elif method == "textDocument/rangeFormatting":
            return Converter.structure(response, lsp_types.DocumentRangeFormattingResponse)

        elif method == "textDocument/semanticTokens/full":
            return Converter.structure(response, lsp_types.SemanticTokensResponse)

        elif method == "textDocument/documentSymbol":
            return Converter.structure(response, lsp_types.DocumentSymbolResponse)

        elif method == "o#/metadata":
            metadata_result = result if isinstance(result, dict) else None
            return Metadata(message_id=response_id, result=metadata_result)

        else:
            raise NotImplementedError((response, request))

    def _handle_request(self, request: t.Any) -> t.Any:
        method = request.get('method')
        params = request.get('params') or {}
        request_id = request.get('id')

        if method == "workspace/workspaceFolders":
            event = Converter.structure(request, lsp_types.WorkspaceFoldersRequest)
            event._client = self
            return event

        elif method == "workspace/configuration":
            event = Converter.structure(request, lsp_types.ConfigurationRequest)
            event._client = self
            return event

        elif method == "window/showMessage":
            return Converter.structure(request, lsp_types.ShowMessageNotification)

        elif method == "window/logMessage":
            return Converter.structure(request, lsp_types.LogMessageNotification)

        elif method == "textDocument/publishDiagnostics":
            return Converter.structure(request, lsp_types.PublishDiagnosticsNotification)

        elif method == "window/workDoneProgress/create":
            token = params.get('token')
            if token is not None:
                self._progress_tokens_map[token] = lsp_types.WorkDoneProgressBegin
            event = Converter.structure(request, lsp_types.WorkDoneProgressCreateRequest)
            event._client = self
            return event

        elif method == "client/registerCapability":
            event = Converter.structure(request, lsp_types.RegisterCapabilityRequest)
            event._client = self
            return event

        elif method == "$/progress":
            token = params.get('token')
            if token not in self._progress_tokens_map:
                self._progress_tokens_map[token] = lsp_types.WorkDoneProgressBegin
            
            value = params.get('value', {})
            kind = value.get('kind')
            
            if kind == "begin":
                return Converter.structure(request, lsp_types.ProgressNotification)
            elif kind == "report":
                return Converter.structure(request, lsp_types.ProgressNotification)
            elif kind == "end":
                if token in self._progress_tokens_map:
                    del self._progress_tokens_map[token]
                return Converter.structure(request, lsp_types.ProgressNotification)
            else:
                raise ValueError(f"Unknown progress kind: {kind}")

        else:
            raise NotImplementedError(request)

    def recv(self, data: bytes) -> t.Iterator[t.Tuple[t.Optional[t.Union[int, str]], t.Any]]:
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

    def did_open(self, text_document: lsp_types.TextDocumentItem) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="textDocument/didOpen",
            params={"textDocument": Converter.unstructure(text_document)},
        )

    def did_change(
        self,
        text_document: lsp_types.VersionedTextDocumentIdentifier,
        content_changes: t.List[lsp_types.TextDocumentContentChangeEvent],
    ) -> None:
        assert self._state == ClientState.NORMAL
        self._send_notification(
            method="textDocument/didChange",
            params={
                "textDocument": Converter.unstructure(text_document),
                "contentChanges": [Converter.unstructure(evt) for evt in content_changes],
            },
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
    ) -> t.Union[int, str]:
        assert self._state == ClientState.NORMAL
        params = Converter.unstructure(text_document_position)
        if context is not None:
            params['context'] = Converter.unstructure(context)
        return self._send_request(method="textDocument/completion", params=params)

    def hover(self, text_document_position: lsp_types.TextDocumentPositionParams) -> t.Union[int, str]:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/hover", params=Converter.unstructure(text_document_position)
        )

    def signatureHelp(self, text_document_position: lsp_types.TextDocumentPositionParams) -> t.Union[int, str]:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/signatureHelp",
            params=Converter.unstructure(text_document_position),
        )

    def definition(self, text_document_position: lsp_types.TextDocumentPositionParams) -> t.Union[int, str]:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/definition", params=Converter.unstructure(text_document_position)
        )

    def references(self, text_document_position: lsp_types.TextDocumentPositionParams) -> t.Union[int, str]:
        assert self._state == ClientState.NORMAL
        params = {
            "context": {"includeDeclaration": True},
            **Converter.unstructure(text_document_position),
        }
        return self._send_request(method="textDocument/references", params=params)

    def implementation(self, text_document_position: lsp_types.TextDocumentPositionParams) -> t.Union[int, str]:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/implementation",
            params=Converter.unstructure(text_document_position),
        )

    def declaration(self, text_document_position: lsp_types.TextDocumentPositionParams) -> t.Union[int, str]:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/declaration",
            params=Converter.unstructure(text_document_position),
        )

    def typeDefinition(self, text_document_position: lsp_types.TextDocumentPositionParams) -> t.Union[int, str]:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/typeDefinition",
            params=Converter.unstructure(text_document_position),
        )

    def formatting(
        self, text_document: lsp_types.TextDocumentIdentifier, options: lsp_types.FormattingOptions
    ) -> t.Union[int, str]:
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
    ) -> t.Union[int, str]:
        assert self._state == ClientState.NORMAL
        params = {
            "textDocument": Converter.unstructure(text_document),
            "range": Converter.unstructure(range),
            "options": Converter.unstructure(options),
        }
        return self._send_request(method="textDocument/rangeFormatting", params=params)

    def semantic_tokens(self, text_document: lsp_types.TextDocumentIdentifier) -> t.Union[int, str]:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/semanticTokens/full",
            params={"textDocument": Converter.unstructure(text_document)},
        )

    def documentSymbol(self, text_document: lsp_types.TextDocumentIdentifier) -> t.Union[int, str]:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/documentSymbol",
            params={"textDocument": Converter.unstructure(text_document)},
        )

    def metadata(self, params):
        return self._send_request(method="o#/metadata", params=params)
