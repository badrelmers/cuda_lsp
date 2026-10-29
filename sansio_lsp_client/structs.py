from __future__ import annotations

import enum
import typing as t
from typing_extensions import Literal

import attrs

from .attr_model import AttrsModel

# XXX: Replace the non-commented-out code with what's commented out once nested
# types become a thing in mypy.
# JSONValue = t.Union[None, str, int,
#                     t.List['JSONValue'], t.Dict[str, 'JSONValue']]
# JSONDict = t.Dict[str, JSONValue]
JSONDict = t.Dict[str, t.Any]
JSONList = t.List[t.Any]

Id = t.Union[int, str]

ProgressToken = t.Union[int, str]


@attrs.define(slots=True)
class Request(AttrsModel):
    method: str
    id: t.Optional[Id] = None
    params: t.Optional[t.Any] = None


@attrs.define(slots=True)
class Response(AttrsModel):
    id: t.Optional[Id] = None
    result: t.Optional[t.Any] = None
    error: t.Optional[JSONDict] = None


class MessageType(enum.IntEnum):
    ERROR = 1
    WARNING = 2
    INFO = 3
    LOG = 4
    DEBUG = 5


@attrs.define(slots=True)
class MessageActionItem(AttrsModel):
    title: str


@attrs.define(slots=True)
class TextDocumentItem(AttrsModel):
    uri: str
    languageId: str
    version: int
    text: str


@attrs.define(slots=True)
class TextDocumentIdentifier(AttrsModel):
    uri: str


@attrs.define(slots=True)
class OptionalVersionedTextDocumentIdentifier(TextDocumentIdentifier):
    version: t.Optional[int] = None


@attrs.define(slots=True)
class VersionedTextDocumentIdentifier(TextDocumentIdentifier):
    version: t.Optional[int] = None


# Sorting tip:  sorted(positions, key=(lambda p: p.as_tuple()))
@attrs.define(slots=True)
class Position(AttrsModel):
    # NB: These are both zero-based.
    line: int
    character: int

    def as_tuple(self) -> t.Tuple[int, int]:
        return (self.line, self.character)
    
    # for sorting
    def __lt__(self, other):
        return (self.character < other.character) if self.line == other.line else (self.line < other.line)


@attrs.define(slots=True)
class Range(AttrsModel):
    start: Position
    end: Position

    def calculate_length(self, text: str) -> int:
        text_lines = text.splitlines()

        if self.end.line == self.start.line:
            line = text_lines[self.start.line]
            return len(line[self.start.character : self.end.character])
        else:
            total = 0

            total += len(text_lines[self.start.line][self.start.character :])

            for line_number in range(self.start.line + 1, self.end.line):
                total += len(text_lines[line_number])

            total += len(text_lines[self.end.line][: self.end.character])

            return total


@attrs.define(slots=True)
class TextDocumentContentChangeEvent(AttrsModel):
    text: str
    rangeLength: t.Optional[int] = None  # deprecated, use .range
    range: t.Optional[Range] = None

    def model_dump(self, **kwargs: t.Any) -> t.Dict[str, t.Any]:
        d = super().model_dump(**kwargs)

        # vscode-css server requires un-filled values to be absent
        # TODO: add vscode-css to tests
        if self.rangeLength is None:
            del d["rangeLength"]
        if self.range is None:
            del d["range"]
        return d

    @classmethod
    def range_change(
        cls,
        change_start: Position,
        change_end: Position,
        change_text: str,
        old_text: str,
    ) -> "TextDocumentContentChangeEvent":
        """
        Create a TextDocumentContentChangeEvent reflecting the given changes.

        Nota bene: If you're creating a list of
        TextDocumentContentChangeEvent based on many changes, `old_text` must
        reflect the state of the text after all previous change events
        happened.
        """
        change_range = Range(start=change_start, end=change_end)
        return cls(
            range=change_range,
            rangeLength=change_range.calculate_length(old_text),
            text=change_text,
        )

    @classmethod
    def whole_document_change(
        cls, change_text: str
    ) -> "TextDocumentContentChangeEvent":
        return cls(text=change_text, range=None, rangeLength=None)


@attrs.define(slots=True)
class TextDocumentPosition(AttrsModel):
    textDocument: TextDocumentIdentifier
    position: Position


class CompletionTriggerKind(enum.IntEnum):
    INVOKED = 1
    TRIGGER_CHARACTER = 2
    TRIGGER_FOR_INCOMPLETE_COMPLETIONS = 3


@attrs.define(slots=True)
class CompletionContext(AttrsModel):
    triggerKind: CompletionTriggerKind
    triggerCharacter: t.Optional[str] = None


class MarkupKind(enum.Enum):
    PLAINTEXT = "plaintext"
    MARKDOWN = "markdown"


@attrs.define(slots=True)
class MarkupContent(AttrsModel):
    kind: MarkupKind
    value: str


@attrs.define(slots=True)
class TextEdit(AttrsModel):
    range: Range
    newText: str
    annotationId: t.Optional[str] = None


@attrs.define(slots=True)
class TextDocumentEdit(AttrsModel):
    textDocument: OptionalVersionedTextDocumentIdentifier
    edits: t.List[TextEdit]


@attrs.define(slots=True)
class Command(AttrsModel):
    title: str
    command: str
    arguments: t.Optional[t.List[t.Any]] = None


class InsertTextFormat(enum.IntEnum):
    PLAIN_TEXT = 1
    SNIPPET = 2


class CompletionItemKind(enum.IntEnum):
    TEXT = 1
    METHOD = 2
    FUNCTION = 3
    CONSTRUCTOR = 4
    FIELD = 5
    VARIABLE = 6
    CLASS = 7
    INTERFACE = 8
    MODULE = 9
    PROPERTY = 10
    UNIT = 11
    VALUE = 12
    ENUM = 13
    KEYWORD = 14
    SNIPPET = 15
    COLOR = 16
    FILE = 17
    REFERENCE = 18
    FOLDER = 19
    ENUMMEMBER = 20
    CONSTANT = 21
    STRUCT = 22
    EVENT = 23
    OPERATOR = 24
    TYPEPARAMETER = 25


class CompletionItemTag(enum.IntEnum):
    DEPRECATED = 1


@attrs.define(slots=True)
class CompletionItem(AttrsModel):
    label: str
    documentation: t.Union[str, MarkupContent, None] = None
    detail: t.Optional[str] = None
    kind: t.Optional[CompletionItemKind] = None
    insertText: t.Optional[str] = None
    insertTextFormat: t.Optional[InsertTextFormat] = None
    textEdit: t.Optional[TextEdit] = None
    additionalTextEdits: t.Optional[t.List[TextEdit]] = None
    commitCharacters: t.Optional[t.List[str]] = None
    command: t.Optional[Command] = None
    data: t.Optional[t.Any] = None
    deprecated: t.Optional[bool] = None
    filterText: t.Optional[str] = None
    preselect: t.Optional[bool] = None
    sortText: t.Optional[str] = None
    tags: t.Optional[t.List[CompletionItemTag]] = None


@attrs.define(slots=True)
class CompletionList(AttrsModel):
    isIncomplete: bool
    items: t.List[CompletionItem]


class TextDocumentSaveReason(enum.IntEnum):
    MANUAL = 1
    AFTER_DELAY = 2
    FOCUS_OUT = 3


@attrs.define(slots=True)
class Location(AttrsModel):
    uri: str
    range: Range


@attrs.define(slots=True)
class LocationLink(AttrsModel):
    targetUri: str
    targetRange: Range
    targetSelectionRange: Range
    originSelectionRange: t.Optional[Range] = None


class DiagnosticSeverity(enum.IntEnum):
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4

    def short_name(self):
        return {self.ERROR:'Err', self.WARNING:'Wrn', self.INFORMATION:'Inf',
                    self.HINT:'Hint'}[self]


class DiagnosticTag(enum.IntEnum):
    UNNECESSARY = 1
    DEPRECATED = 2


@attrs.define(slots=True)
class DiagnosticRelatedInformation(AttrsModel):
    location: Location
    message: str


@attrs.define(slots=True)
class Diagnostic(AttrsModel):
    range: Range
    message: str
    severity: t.Optional[DiagnosticSeverity] = None
    code: t.Optional[t.Union[int, str]] = None
    codeDescription: t.Optional[JSONDict] = None
    source: t.Optional[str] = None
    relatedInformation: t.Optional[t.List[DiagnosticRelatedInformation]] = None
    tags: t.Optional[t.List[DiagnosticTag]] = None
    data: t.Optional[t.Any] = None


""" HOVER #################
Hover:
    * contents: MarkedString | MarkedString[] | MarkupContent;
    * range?: Range;
"""
#deprecated, use MarkupContent
@attrs.define(slots=True)
class MarkedString(AttrsModel):
    language: str
    value: str


""" SignatureHelp
    * signatures: SignatureInformation[];
        # SignatureInformation
        * label: string;
        * documentation?: string | MarkupContent;
        * parameters?: ParameterInformation[];
            # ParameterInformation
            * label: string | [uinteger, uinteger];
            * documentation?: string | MarkupContent;
        * activeParameter?: uinteger;
    * activeSignature?: uinteger;
    * activeParameter?: uinteger;
"""
@attrs.define(slots=True)
class ParameterInformation(AttrsModel):
    label: t.Union[str, t.Tuple[int, int]]
    documentation: t.Optional[t.Union[str, MarkupContent]] = None


@attrs.define(slots=True)
class SignatureInformation(AttrsModel):
    label: str
    documentation: t.Optional[t.Union[MarkupContent, str]] = None
    parameters: t.Optional[t.List[ParameterInformation]] = None
    activeParameter: t.Optional[int] = None


class SymbolKind(enum.IntEnum):
    FILE = 1
    MODULE = 2
    NAMESPACE = 3
    PACKAGE = 4
    CLASS = 5
    METHOD = 6
    PROPERTY = 7
    FIELD = 8
    CONSTRUCTOR = 9
    ENUM = 10
    INTERFACE = 11
    FUNCTION = 12
    VARIABLE = 13
    CONSTANT = 14
    STRING = 15
    NUMBER = 16
    BOOLEAN = 17
    ARRAY = 18
    OBJECT = 19
    KEY = 20
    NULL = 21
    ENUMMEMBER = 22
    STRUCT = 23
    EVENT = 24
    OPERATOR = 25
    TYPEPARAMETER = 26


class SymbolTag(enum.IntEnum):
    DEPRECATED = 1


@attrs.define(slots=True)
class CallHierarchyItem(AttrsModel):
    name: str
    kind: SymbolKind
    uri: str
    range: Range
    selectionRange: Range
    data: t.Optional[t.Any] = None
    detail: t.Optional[str] = None
    tags: t.Optional[SymbolTag] = None


@attrs.define(slots=True)
class CallHierarchyIncomingCall(AttrsModel):
    from_: CallHierarchyItem = attrs.field(metadata={"alias": "from"})
    fromRanges: t.List[Range]


@attrs.define(slots=True)
class CallHierarchyOutgoingCall(AttrsModel):
    to: CallHierarchyItem
    fromRanges: t.List[Range]


class TextDocumentSyncKind(enum.IntEnum):
    NONE = 0
    FULL = 1
    INCREMENTAL = 2


# Usually in a flat list
@attrs.define(slots=True)
class SymbolInformation(AttrsModel):
    name: str
    kind: SymbolKind
    location: Location
    tags: t.Optional[t.List[SymbolTag]] = None
    deprecated: t.Optional[bool] = None
    containerName: t.Optional[str] = None

    def mpos(self):
        return self.location.range.start.character, self.location.range.start.line


@attrs.define(slots=True)
class InlayHintLabelPart(AttrsModel):
    value: str
    tooltip: t.Optional[t.Union[str, MarkupContent]] = None
    location: t.Optional[Location] = None
    command: t.Optional[Command] = None


class InlayHintKind(enum.IntEnum):
    TYPE = 1
    PARAMETER = 2


@attrs.define(slots=True)
class InlayHint(AttrsModel):
    position: Position
    label: t.Union[str, t.List[InlayHintLabelPart]]
    kind: t.Optional[InlayHintKind] = None
    data: t.Optional[t.Any] = None
    paddingLeft: t.Optional[bool] = None
    paddingRight: t.Optional[bool] = None
    textEdits: t.Optional[t.List[TextEdit]] = None
    tooltip: t.Optional[t.Union[str, MarkupContent]] = None


@attrs.define(slots=True)
class FoldingRange(AttrsModel):
    startLine: int
    endLine: int
    startCharacter: t.Optional[int] = None
    endCharacter: t.Optional[int] = None
    kind: t.Optional[str] = None
    collapsedText: t.Optional[str] = None


# Usually a hierarchy, e.g. a symbol with kind=SymbolKind.CLASS contains
# several SymbolKind.METHOD symbols
@attrs.define(slots=True)
class DocumentSymbol(AttrsModel):
    name: str
    kind: SymbolKind
    range: Range
    selectionRange: Range
    detail: t.Optional[str] = None
    tags: t.Optional[t.List[SymbolTag]] = None
    deprecated: t.Optional[bool] = None
    children: t.Optional[t.List["DocumentSymbol"]] = None

    def mpos(self):
        return self.selectionRange.start.character, self.selectionRange.start.line

# for `.children` treeness
@attrs.define(slots=True)
class Registration(AttrsModel):
    id: str
    method: str
    registerOptions: t.Optional[t.Any] = None
    
@attrs.define(slots=True)
class DocumentFilter(AttrsModel):
    language: t.Optional[str] = None
    scheme: t.Optional[str] = None
    pattern: t.Optional[str] = None

DocumentSelector = t.List[DocumentFilter]

@attrs.define(slots=True)
class CompletionOptionsCompletionItem(AttrsModel):
    labelDetailsSupport: t.Optional[bool] = None

@attrs.define(slots=True)
class CompletionRegistrationOptions(AttrsModel):
    documentSelector: t.Union[DocumentSelector, None]
    triggerCharacters: t.Optional[t.List[str]] = None
    allCommitCharacters: t.Optional[t.List[str]] = None
    resolveProvider: t.Optional[bool] = None
    completionItem: t.Optional[CompletionOptionsCompletionItem] = None


@attrs.define(slots=True)
class FormattingOptions(AttrsModel):
    tabSize: int
    insertSpaces: bool
    trimTrailingWhitespace: t.Optional[bool] = None
    insertFinalNewline: t.Optional[bool] = None
    trimFinalNewlines: t.Optional[bool] = None


@attrs.define(slots=True)
class WorkspaceFolder(AttrsModel):
    uri: str
    name: str


@attrs.define(slots=True)
class ProgressValue(AttrsModel):
    pass


@attrs.define(slots=True)
class WorkDoneProgressValue(ProgressValue):
    pass


class MWorkDoneProgressKind(enum.Enum):
    BEGIN = "begin"
    REPORT = "report"
    END = "end"


@attrs.define(slots=True)
class WorkDoneProgressBeginValue(WorkDoneProgressValue):
    kind: Literal["begin"]
    title: str
    cancellable: t.Optional[bool] = None
    message: t.Optional[str] = None
    percentage: t.Optional[int] = None


@attrs.define(slots=True)
class WorkDoneProgressReportValue(WorkDoneProgressValue):
    kind: Literal["report"]
    cancellable: t.Optional[bool] = None
    message: t.Optional[str] = None
    percentage: t.Optional[int] = None


@attrs.define(slots=True)
class WorkDoneProgressEndValue(WorkDoneProgressValue):
    kind: Literal["end"]
    message: t.Optional[str] = None


@attrs.define(slots=True)
class ConfigurationItem(AttrsModel):
    scopeUri: t.Optional[str] = None
    section: t.Optional[str] = None
