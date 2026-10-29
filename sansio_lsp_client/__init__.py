"""Client library for managing language server requests & responses.

Sans-I/O LSP client built on:

- `lsprotocol <https://pypi.org/project/lsprotocol/>`_ - the canonical LSP
  type definitions (all wire types come from ``lsprotocol.types``),
- `attrs <https://pypi.org/project/attrs/>`_ - the JSON-RPC envelope and the
  event classes,
- `cattrs <https://pypi.org/project/cattrs/>`_ - (de)serialization between
  lsprotocol objects and raw JSON.

Replaces the former pydantic-based implementation; supports Python 3.8+.
"""

import attrs

from .client import *  # noqa: F401,F403
from .events import *  # noqa: F401,F403
from .io_handler import (  # noqa: F401
    Request,
    Response,
    structure,
    unstructure,
)


def event_asdict(event):
    """Debug helper: dump an event/attrs object into a plain dict.

    Private fields (like the internal client reference) are skipped;
    nested lsprotocol objects are recursed into.
    """
    return attrs.asdict(
        event, recurse=True, filter=lambda a, _v: not a.name.startswith('_')
    )


__version__ = "1.0.0"
