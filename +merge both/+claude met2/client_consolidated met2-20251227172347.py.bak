"""Client library for managing language server requests & responses."""

import enum
import json
import re
import typing as t
from lsprotocol import converters, types as lsp_types

Converter = converters.get_converter()

# Type aliases for readability
JSONDict = t.Dict[str, t.Any]
JSONList = t.List[t.Any]
Id = t.Union[int, str]

# ============================================================================
# IO Handler Functions (formerly io_handler.py)
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
    params: t.Optional[JSONDict] = None,
    id: t.Optional[Id] = None,
    *,
    encoding: str = "utf-8",
) -> bytes:
    request = bytearray()

    # Set up the actual JSONRPC content and encode it.
    content: JSONDict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        content["params"] = params
    if id is not None:
        content["id"] = id
    encoded_content = json.dumps(content).encode(encoding)

    # Write the headers to the request body
    request += _make_headers(content_length=len(encoded_content), encoding=encoding)

    # Append the content to the request
    request += encoded_content

    return request


def _make_response(
    id: t.Union[int, str],
    result: t.Optional[t.Union[JSONDict, JSONList]] = None,
    error: t.Optional[JSONDict] = None,
    *,
    encoding: str = "utf-8",
) -> bytes:
    request = bytearray()

    # Set up the actual JSONRPC content and encode it.
    content: JSONDict = {"jsonrpc": "2.0", "id": id}
    # content["result"]: The result of a request. This member is REQUIRED on success.
    # This member MUST NOT exist if there was an error invoking the method.
    if result is not None:
        content["result"] = result
    if error is not None:
        content["error"] = error
    elif result is None:
        content["result"] = None  # "result": null

    encoded_content = json.dumps(content).encode(encoding)

    # Write the headers to the request body
    request += _make_headers(content_length=len(encoded_content), encoding=encoding)

    # Append the content to the request
    request += encoded_content

    return request


def _parse_content_type(header: str) -> t.Tuple[str, t.Dict[str, str]]:
    """Example: "application/vscode-jsonrpc; charset=utf-8" --> 
    ("application/vscode-jsonrpc", {"charset": "utf-8"})"""
    content_type, _, param_string = header.partition(";")
    content_type = content_type.strip().lower()

    metadata = {
        m.group(1).lower(): (m.group(2) or m.group(3))
        for m in _CONTENT_TYPE_PARAM_RE.finditer(param_string)
    }

    return content_type, metadata


def _parse_one_message(response_buf: bytearray) -> t.Optional[t.Iterable[dict]]:
    """Parse a single JSON-RPC message from a bytearray.

    Args:
        response_buf: A bytearray containing JSON-RPC messages.

    Returns:
        None if there's not enough data for a complete message,
        or the raw dicts if a message was parsed successfully.

    Note: This function modifies response_buf by removing parsed data."""
    if b"\r\n\r\n" not in response_buf:
        return None

    header_lines, raw_content = bytes(response_buf).split(b"\r\n\r\n", 1)

    # Many langservers don't set Content-Type header for whatever reason.
    # We use a sane default for that.
    # Langserver spec links to RFC 7230 which says that header names should be
    # case-insensitive.
    headers = {"content-type": "application/vscode-jsonrpc; charset=utf-8"}
    for header_line in header_lines.split(b"\r\n"):
        key, value = header_line.decode("ascii").split(": ", 1)
        headers[key.lower()] = value

    # Parse Content-Type and Content-Length headers
    assert set(headers.keys()) == {"content-type", "content-length"}

    # Content-Type and encoding
    content_type, metadata = _parse_content_type(headers["content-type"])
    assert content_type == "application/vscode-jsonrpc"
    encoding = metadata["charset"]

    # Content-Length
    content_length = int(headers["content-length"])

    # Verify that the raw_content is long enough
    if len(raw_content) < content_length:
        # incomplete request
        return None

    # Take only as many bytes as we need
    unused_bytes_count = len(raw_content) - content_length
    raw_content = raw_content[:content_length]

    # Delete unnecessary stuff from response_buf
    if unused_bytes_count == 0:  # 'del response_buf[:-0]' does wrong thing
        response_buf.clear()
    else:
        del response_buf[:-unused_bytes_count]

    content = json.loads(raw_content.decode(encoding))

    # LSP can send a single dict or a list (batch).
    # We ensure we return an iterable of dicts.
    if isinstance(content, list):
        return content
    else:
        return [content]


def _parse_messages(response_buf: bytearray) -> t.Optional[t.Iterable[dict]]:
    """Parse all complete JSON-RPC messages from a bytearray.

    Args:
        response_buf: A bytearray containing zero or more JSON-RPC messages.

    Returns:
        An iterator yielding the raw dicts for each complete message.
        Partial messages at the end of the buffer are left for future parsing.

    Note: This function modifies response_buf by removing parsed data."""
    while True:
        parsed = _parse_one_message(response_buf)
        if parsed is None:
            break
        yield from parsed


# ============================================================================
# Client State and Capabilities
# ============================================================================

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
# Request Tracking
# ============================================================================

class Request:
    """Tracks an outgoing request"""
    def __init__(self, id: Id, method: str, params: t.Optional[t.Union[JSONDict, JSONList]] = None):
        self.id = id
        self.method = method
        self.params = params


# ============================================================================
# Client Class
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

        # Used to save data as it comes in until we have a full request
        self._recv_buf = bytearray()

        # Things that we still need to send
        self._send_buf = bytearray()

        # Keeps track of which IDs match to which unanswered requests
        self._unanswered_requests: t.Dict[Id, Request] = {}

        # Simple counter to make sure we have unique IDs
        self._id_counter = 0

        # Store type of '$/progress' for parsing
        self._progress_tokens_map: t.Dict[t.Union[int, str], t.Any] = {}

        # Send off an "initialize" request immediately
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

        # Prepare configuration for "workspace/didChangeConfiguration"
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
        """Handle response from server"""
        response_id = response.get('id')
        assert response_id is not None
        
        request = self._unanswered_requests.pop(response_id)

        # Check for error
        error_payload = response.get('error')
        if error_payload is not None:
            err = lsp_types.ResponseError(
                code=error_payload.get("code"),
                message=error_payload.get("message", ""),
                data=error_payload.get("data"),
            )
            # Attach message_id for tracking
            err.message_id = response_id
            return err

        method = request.method
        result = response.get('result')

        # Handle initialize response specially
        if method == "initialize":
            assert self._state == ClientState.WAITING_FOR_INITIALIZED
            self._send_notification("initialized", params={})
            self._send_notification(
                "workspace/didChangeConfiguration",
                params={"settings": self.settings},
            )
            # Return capabilities dict directly
            self._state = ClientState.NORMAL
            return {"_initialized": True, "capabilities": result or {}}

        elif method == "shutdown":
            assert self._state == ClientState.WAITING_FOR_SHUTDOWN
            self._state = ClientState.SHUTDOWN
            return {"_shutdown": True}

        elif method == "textDocument/completion":
            completion_list = None
            if isinstance(result, dict):
                completion_list = result
            elif isinstance(result, list):
                completion_list = {
                    "isIncomplete": False,
                    "items": result,
                }
            return {"_completion": True, "message_id": response_id, "completion_list": completion_list}

        elif method == "textDocument/hover":
            event = Converter.structure(result, lsp_types.Hover)
            event.message_id = response_id
            return event

        elif method == "textDocument/signatureHelp":
            if result is not None:
                event = Converter.structure(result, lsp_types.SignatureHelp)
            else:
                event = lsp_types.SignatureHelp(signatures=[])
            event.message_id = response_id
            return event

        elif method == "textDocument/semanticTokens/full":
            if result is None:
                event = lsp_types.SemanticTokens(data=[])
            else:
                event = Converter.structure(result, lsp_types.SemanticTokens)
            event.message_id = response_id
            event.resultId = result.get('resultId') if result else None
            return event

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

        elif method == "textDocument/documentSymbol":
            return {"_document_symbols": True, "message_id": response_id, "result": result or []}

        elif method == "o#/metadata":
            metadata_result = result if isinstance(result, dict) else None
            return {"_metadata": True, "message_id": response_id, "result": metadata_result}

        else:
            raise NotImplementedError((response, request))

    def _handle_request(self, request: t.Any) -> t.Any:
        """Handle request from server"""
        method = request.get('method')
        params = request.get('params') or {}
        request_id = request.get('id')

        if method == "workspace/workspaceFolders":
            return {"_workspace_folders": True, "_id": request_id}
        
        elif method == "workspace/configuration":
            items = params.get('items', [])
            parsed_items = [Converter.structure(item, lsp_types.ConfigurationItem) for item in items]
            return {"_configuration_request": True, "_id": request_id, "items": parsed_items}
        
        elif method == "window/showMessage":
            return Converter.structure(params, lsp_types.ShowMessageParams)
        
        elif method == "window/logMessage":
            return Converter.structure(params, lsp_types.LogMessageParams)
        
        elif method == "textDocument/publishDiagnostics":
            return Converter.structure(params, lsp_types.PublishDiagnosticsParams)
        
        elif method == "window/workDoneProgress/create":
            token = params.get('token')
            if token is not None:
                self._progress_tokens_map[token] = True
            return {"_progress_create": True, "_id": request_id, "token": token}
        
        elif method == "client/registerCapability":
            registrations = params.get('registrations', [])
            parsed_regs = [Converter.structure(reg, lsp_types.Registration) for reg in registrations]
            return {"_register_capability": True, "_id": request_id, "registrations": parsed_regs}
        
        elif method == "$/progress":
            token = params.get('token')
            value = params.get('value', {})
            kind = value.get('kind')
            
            # Handle missing workDoneProgress/create gracefully
            if token not in self._progress_tokens_map:
                self._progress_tokens_map[token] = True
            
            if kind == "begin":
                parsed_value = Converter.structure(value, lsp_types.WorkDoneProgressBegin)
                return {"_progress_begin": True, "token": token, "value": parsed_value}
            elif kind == "report":
                parsed_value = Converter.structure(value, lsp_types.WorkDoneProgressReport)
                return {"_progress_report": True, "token": token, "value": parsed_value}
            elif kind == "end":
                if token in self._progress_tokens_map:
                    del self._progress_tokens_map[token]
                parsed_value = Converter.structure(value, lsp_types.WorkDoneProgressEnd)
                return {"_progress_end": True, "token": token, "value": parsed_value}
            else:
                raise ValueError(f"Unknown progress kind: {kind}")
        
        else:
            raise NotImplementedError(request)

    def recv(self, data: bytes) -> t.Iterator[t.Tuple[t.Optional[Id], t.Any]]:
        """Parse received data and yield (message_id, event) tuples.
        
        Returns:
            Iterator of (message_id, event) tuples where:
            - message_id: The ID from our original request (for responses), or None (for server requests/notifications)
            - event: The parsed Event object
        """
        self._recv_buf += data
        for message in _parse_messages(self._recv_buf):
            # Distinguish between Response and Request/Notification
            if "method" not in message:
                # It's a Response
                event = self._handle_response(message)
                yield (message['id'], event)
            else:
                # It's a Request or Notification
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

    # Document synchronization methods
    def did_open(self, text_document: lsp_types.TextDocumentItem) -> None:
        assert self._state == ClientState.NORMAL
        td_dict = Converter.unstructure(text_document)
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

    def did_save(
        self, text_document: lsp_types.TextDocumentIdentifier, text: t.Optional[str] = None
    ) -> None:
        assert self._state == ClientState.NORMAL
        params: JSONDict = {"textDocument": Converter.unstructure(text_document)}
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

    # Language feature methods
    def completion(
        self,
        text_document_position: lsp_types.TextDocumentPositionParams,
        context: t.Optional[lsp_types.CompletionContext] = None,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params = {}
        params.update(Converter.unstructure(text_document_position))
        if context is not None:
            params.update({'context': Converter.unstructure(context)})
        return self._send_request(method="textDocument/completion", params=params)

    def semantic_tokens(self, text_document: lsp_types.TextDocumentIdentifier) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/semanticTokens/full",
            params={"textDocument": Converter.unstructure(text_document)},
        )

    def hover(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/hover", params=Converter.unstructure(text_document_position)
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

    def implementation(self, text_document_position: lsp_types.TextDocumentPositionParams) -> Id:
        assert self._state == ClientState.NORMAL
        return self._send_request(
            method="textDocument/implementation",
            params=Converter.unstructure(text_document_position),
        )

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
        """OmniSharp metadata request"""
        return self._send_request(method="o#/metadata", params=params)
