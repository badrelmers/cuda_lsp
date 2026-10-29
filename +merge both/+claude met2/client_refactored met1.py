"""Client library for managing language server requests & responses."""

import enum
import json
import re
import typing as t
import attrs
from lsprotocol import converters, types as lsp_types

Converter = converters.get_converter()

# ============================================================================
# Type Aliases (formerly structs.py)
# ============================================================================

JSONDict = t.Dict[str, t.Any]
JSONList = t.List[t.Any]
Id = t.Union[int, str]

# ============================================================================
# Custom Events (not in lsprotocol)
# ============================================================================

@attrs.define
class ResponseError:
    """Custom response error wrapper"""
    code: int = attrs.field()
    message: str = attrs.field()
    data: t.Optional[t.Any] = attrs.field(default=None)
    message_id: t.Optional[Id] = attrs.field(default=None)

@attrs.define
class Metadata:
    """OmniSharp metadata response"""
    message_id: t.Optional[Id] = attrs.field(default=None)
    result: t.Optional[JSONDict] = attrs.field(default=None)

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
    id: Id,
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

# Example: "application/vscode-jsonrpc; charset=utf-8" --> ("application/vscode-jsonrpc", {"charset": "utf-8"})
def _parse_content_type(header: str) -> t.Tuple[str, t.Dict[str, str]]:
    content_type, _, param_string = header.partition(";")
    content_type = content_type.strip().lower()

    metadata = {
        m.group(1).lower(): (m.group(2) or m.group(3))
        for m in _CONTENT_TYPE_PARAM_RE.finditer(param_string)
    }

    return content_type, metadata

# _parse_messages is kind of tricky.
#
# It used to work like this:
#   - Take in bytes argument
#   - Yield parsed things (Responses and Requests)
#   - Raise IncompleteResponseError if parsing fails by running out of bytes
#
# Then, if the bytes contained two valid things (Responses or Requests) and
# then only a part of another thing, this function would first parse and yield
# the valid things and then raise IncompleteResponseError, outputting no
# information about which bytes hadn't been parsed yet. The code calling this
# function would see only the IncompleteResponseError and discard the parsed
# things. Even with that bugginess, this actually worked because every once in
# a while there would be no bytes left from parsing things, and this function
# would output parsed things with no error.
#
# The least error-prone fix I could think of is to pass the bytes to parse
# as a mutable bytearray object, and just delete the used bytes from there.
# This means that we no longer have any need for IncompleteResponseError, and
# this function will return an empty list instead in that case.
#
# _parse_one_message returns None when there are no more messages, and an empty
# iterator when a message was parsed but no things were created.
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

    # Many langservers don't set Content-Type header for whatever reason. We use a sane default for that.
    # Langserver spec links to RFC 7230 which says that header names should be
    # case-insensitive.
    headers = {"content-type": "application/vscode-jsonrpc; charset=utf-8"}
    for header_line in header_lines.split(b"\r\n"):
        key, value = header_line.decode("ascii").split(": ", 1)
        headers[key.lower()] = value

    # We will now parse the Content-Type and Content-Length headers. Since for
    # version 3.0 of the Language Server Protocol they're the only ones, we can
    # just verify they're there and not keep them around in the Response
    # object.
    assert set(headers.keys()) == {"content-type", "content-length"}

    # Content-Type and encoding.
    content_type, metadata = _parse_content_type(headers["content-type"])
    assert content_type == "application/vscode-jsonrpc"
    encoding = metadata["charset"]

    # Content-Length
    content_length = int(headers["content-length"])

    # We need to verify that the raw_content is long enough.
    if len(raw_content) < content_length:
        # incomplete request
        return None

    # Take only as many bytes as we need. If there's any remaining, they're
    # the next response's.
    unused_bytes_count = len(raw_content) - content_length
    raw_content = raw_content[:content_length]

    # This is a good place for deleting unnecessary stuff from response_buf
    # because if the code below fails, then leaving the cause of failure to
    # response_buf would cause this function to fail every time in the future
    # when called with the same response_buf. I think I've had this issue a
    # long time ago, and it was annoying how one response parsing error would
    # also block the parsing of any future responses.
    if unused_bytes_count == 0:  # 'del response_buf[:-0]' does wrong thing
        response_buf.clear()
    else:
        del response_buf[:-unused_bytes_count]

    content = json.loads(raw_content.decode(encoding))

    # LSP can send a single dict or a list (batch).
    # We ensure we return an iterable of dicts.
    if isinstance(content, list):
        # This is in response to a batch operation.
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

#NOTE: Server capability: resolveProvider - info about completion item -- can't use?
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
# Main Client Class
# ============================================================================

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

        # Used to save data as it comes in (from `receive_bytes`) until we have a full request.
        self._recv_buf = bytearray()

        # Things that we still need to send.
        self._send_buf = bytearray()

        # Keeps track of which IDs match to which unanswered requests
        self._unanswered_requests: t.Dict[Id, Request] = {}

        # Just a simple counter to make sure we have unique IDs. We could make
        # sure that this fits into a JSONRPC Number, seeing as Python supports
        # bignums, but I think that's an unlikely enough case that checking for
        # it would just litter the code unnecessarily.
        self._id_counter = 0

        # Store type of '$/progress' for parsing
        self._progress_tokens_map: t.Dict[lsp_types.ProgressToken, t.Any] = {}

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

    def _send_notification(self, method: str, params: t.Optional[JSONDict] = None) -> None:
        self._send_buf += _make_request(method=method, params=params)

    def _send_response(
        self,
        id: Id,
        result: t.Optional[t.Union[JSONDict, JSONList]] = None,
        error: t.Optional[JSONDict] = None,
    ) -> None:
        self._send_buf += _make_response(id=id, result=result, error=error)

    # response from server
    def _handle_response(self, response: t.Any) -> t.Any:
        """Handle response from server"""
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

        method = request["method"]
        result = response.get('result')  # result can be None, list, or dict

        if method == "initialize":
            assert self._state == ClientState.WAITING_FOR_INITIALIZED
            self._send_notification(
                "initialized", params={}
            )  # params=None doesn't work with gopls
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

        elif method == "textDocument/willSaveWaitUntil":
            # TODO: check if this is correct
            return Converter.structure(response, lsp_types.WillSaveTextDocumentWaitUntilResponse)

        elif method == "textDocument/hover":
            return Converter.structure(response, lsp_types.HoverResponse)

        elif method == "textDocument/foldingRange":
            return Converter.structure(response, lsp_types.FoldingRangeResponse)

        elif method == "textDocument/signatureHelp":
            return Converter.structure(response, lsp_types.SignatureHelpResponse)

        elif method == "textDocument/documentSymbol":
            return Converter.structure(response, lsp_types.DocumentSymbolResponse)

        elif method == "textDocument/inlayHint":
            return Converter.structure(response, lsp_types.InlayHintResponse)

        elif method == "textDocument/rename":
            return Converter.structure(response, lsp_types.RenameResponse)

        elif method == "textDocument/semanticTokens/full":
            return Converter.structure(response, lsp_types.SemanticTokensResponse)

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

        elif method == "textDocument/prepareCallHierarchy":
            return Converter.structure(response, lsp_types.PrepareCallHierarchyResponse)

        elif method == "textDocument/formatting":
            return Converter.structure(response, lsp_types.DocumentFormattingResponse)

        elif method == "textDocument/rangeFormatting":
            return Converter.structure(response, lsp_types.DocumentRangeFormattingResponse)
        
        # TODO: how this is supposed to work? format multiple selections? add it to cuda lsp
        # elif method == "textDocument/rangesFormatting":
            # return Converter.structure(response, lsp_types.DocumentRangesFormattingResponse)

        # TODO: add this to cuda lsp
        # elif method == "textDocument/onTypeFormatting":
            # return Converter.structure(response, lsp_types.DocumentOnTypeFormattingResponse)

        elif method == "workspace/symbol":
            return Converter.structure(response, lsp_types.WorkspaceSymbolResponse)

        elif method == "o#/metadata":
            metadata_result = result if isinstance(result, dict) else None
            return Metadata(message_id=response_id, result=metadata_result)

        else:
            raise NotImplementedError((response, request))

    # request from server
    def _handle_request(self, request: t.Any) -> t.Any:
        # Use .get() for top-level keys
        method = request.get('method')
        params = request.get('params') or {}
        request_id = request.get('id')

        if method == "workspace/workspaceFolders":
            # We don't need to parse WorkspaceFolders server's request!
            # because according to LSP specs "params: none"
            # Just create empty event and return it
            return Converter.structure(request, lsp_types.WorkspaceFoldersRequest)

        elif method == "workspace/configuration":
            return Converter.structure(request, lsp_types.ConfigurationRequest)

        elif method == "workspace/projectInitializationComplete":
            # TODO: check if this notification exists in lsprotocol
            return Converter.structure(request, lsp_types.Notification)

        elif method == "window/showMessage":
            return Converter.structure(request, lsp_types.ShowMessageNotification)

        elif method == "window/showMessageRequest":
            return Converter.structure(request, lsp_types.ShowMessageRequest)

        elif method == "window/logMessage":
            return Converter.structure(request, lsp_types.LogMessageNotification)

        elif method == "textDocument/publishDiagnostics":
            return Converter.structure(request, lsp_types.PublishDiagnosticsNotification)

        elif method == "window/workDoneProgress/create":
            token = params.get('token')  # Safely access nested 'token'
            if token is not None:
                self._progress_tokens_map[token] = lsp_types.WorkDoneProgressBegin
            return Converter.structure(request, lsp_types.WorkDoneProgressCreateRequest)

        elif method == "client/registerCapability":
            return Converter.structure(request, lsp_types.RegisterCapabilityRequest)

        elif method == "$/progress":
            token = params.get('token')
            
            # if "window/workDoneProgress/create" request from server was missing -
            # pretend it actually was already received. i think there is no harm in that.
            # such server bugs must be silently ignored without crashing our plugin.
            if token not in self._progress_tokens_map:
                self._progress_tokens_map[token] = lsp_types.WorkDoneProgressBegin

            # Safely drill into nested kind
            value = params.get('value', {})
            kind = value.get('kind')

            if kind == "begin":
                return Converter.structure(request, lsp_types.ProgressNotification)
            elif kind == "report":
                return Converter.structure(request, lsp_types.ProgressNotification)
            elif kind == "end":
                if token in self._progress_tokens_map:
                    del self._progress_tokens_map[token]  # prevent the dictionary from growing indefinitely.
                return Converter.structure(request, lsp_types.ProgressNotification)
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

    def completion(
        self,
        text_document_position: lsp_types.TextDocumentPositionParams,
        context: t.Optional[lsp_types.CompletionContext] = None,
    ) -> Id:
        assert self._state == ClientState.NORMAL
        params: JSONDict = {}
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