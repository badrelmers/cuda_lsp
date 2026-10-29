"""Client library for managing language server requests & responses.

Sans-I/O LSP client built on:

- `lsprotocol <https://pypi.org/project/lsprotocol/>`_ - the canonical LSP
  type definitions. **All** LSP types (JSON-RPC message envelopes, params
  and results) come exclusively from ``lsprotocol.types``; the client
  dispatches on lsprotocol's own ``METHOD_TO_TYPES`` table,
- `attrs <https://pypi.org/project/attrs/>`_ - powers the lsprotocol types
  themselves,
- `cattrs <https://pypi.org/project/cattrs/>`_ - (de)serialization between
  lsprotocol message objects and raw JSON (converter from
  ``lsprotocol.converters``).

Replaces the former pydantic-based implementation; supports Python 3.8+.
"""

import attrs

from .client import *  # noqa: F401,F403
from .io_handler import structure, unstructure  # noqa: F401


def event_asdict(message):
    """Debug helper: dump an lsprotocol message (or raw dict) to a plain dict."""
    if attrs.has(type(message)):
        return attrs.asdict(message, recurse=True)
    return message


__version__ = "1.0.0"
