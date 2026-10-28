import json
import re
from typing import Dict, Iterable, Iterator, List, Optional, Union

from .structs import JSONDict, JSONList, Request, Response, Id

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
    params: Optional[JSONDict] = None,
    id: Optional[Id] = None,
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
    id: Union[int, str],
    result: Optional[Union[JSONDict, JSONList]] = None,
    error: Optional[JSONDict] = None,
    *,
    encoding: str = "utf-8",
) -> bytes:
    request = bytearray()

    # Set up the actual JSONRPC content and encode it.
    content: JSONDict = {"jsonrpc": "2.0", "id": id}
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


def _parse_content_type(header: str) -> tuple:
    """Parse content type header."""
    content_type, _, param_string = header.partition(";")
    content_type = content_type.strip().lower()

    metadata = {
        m.group(1).lower(): (m.group(2) or m.group(3))
        for m in _CONTENT_TYPE_PARAM_RE.finditer(param_string)
    }

    return content_type, metadata


def _parse_request_or_response(data: JSONDict) -> Union[Request, Response]:
    """Parse dict into Request or Response based on presence of 'method' field."""
    del data["jsonrpc"]
    
    # If has 'method' field, it's a Request
    if 'method' in data:
        return Request(
            method=data['method'],
            id=data.get('id'),
            params=data.get('params')
        )
    # Otherwise it's a Response
    else:
        return Response(
            id=data.get('id'),
            result=data.get('result'),
            error=data.get('error')
        )


def _parse_one_message(
    response_buf: bytearray,
) -> Optional[Iterable[Union[Request, Response]]]:
    """Parse a single JSON-RPC message from a bytearray.

    Args:
        response_buf: A bytearray containing JSON-RPC messages.

    Returns:
        None if there's not enough data for a complete message,
        or an iterable of Request or Response objects if a message was parsed successfully.

    Note: This function modifies response_buf by removing parsed data."""
    if b"\r\n\r\n" not in response_buf:
        return None

    header_lines, raw_content = bytes(response_buf).split(b"\r\n\r\n", 1)

    # Many langservers don't set Content-Type header
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

    # Verify that raw_content is long enough
    if len(raw_content) < content_length:
        return None

    # Take only as many bytes as we need
    unused_bytes_count = len(raw_content) - content_length
    raw_content = raw_content[:content_length]

    # Delete unnecessary stuff from response_buf
    if unused_bytes_count == 0:
        response_buf.clear()
    else:
        del response_buf[:-unused_bytes_count]

    content = json.loads(raw_content.decode(encoding))

    if isinstance(content, list):
        # Batch operation
        return map(_parse_request_or_response, content)
    else:
        return [_parse_request_or_response(content)]


def _parse_messages(response_buf: bytearray) -> Iterator[Union[Response, Request]]:
    """Parse all complete JSON-RPC messages from a bytearray.

    Args:
        response_buf: A bytearray containing zero or more JSON-RPC messages.

    Returns:
        An iterator yielding Request or Response objects for each complete message.
        Partial messages at the end of the buffer are left for future parsing.

    Note: This function modifies response_buf by removing parsed data."""
    while True:
        parsed = _parse_one_message(response_buf)
        if parsed is None:
            break
        yield from parsed
