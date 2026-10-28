import enum
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple, Union

# Type aliases
JSONDict = Dict[str, Any]
JSONList = List[Any]
Id = Union[int, str]
ProgressToken = Union[int, str]


@dataclass
class Request:
    method: str
    id: Optional[Id] = None
    params: Optional[Union[List[Any], JSONDict]] = None


@dataclass
class Response:
    id: Optional[Id] = None
    result: Optional[Union[List[Any], JSONDict]] = None
    error: Optional[JSONDict] = None


class MessageType(enum.IntEnum):
    ERROR = 1
    WARNING = 2
    INFO = 3
    LOG = 4
    DEBUG = 5


@dataclass
class MessageActionItem:
    title: str


@dataclass
class TextDocumentItem:
    uri: str
    languageId: str
    version: int
    text: str
    
    def to_dict(self):
        return asdict(self)


@dataclass
class TextDocumentIdentifier:
    uri: str
    
    def to_dict(self):
        return asdict(self)


@dataclass
class OptionalVersionedTextDocumentIdentifier:
    uri: str
    version: Optional[int] = None


@dataclass
class VersionedTextDocumentIdentifier:
    uri: str
    version: Optional[int] = None
    
    def to_dict(self):
        return asdict(self)


@dataclass
class Position:
    line: int
    character: int

    def as_tuple(self) -> Tuple[int, int]:
        return (self.line, self.character)
    
    def __lt__(self, other):
        return (self.character < other.character) if self.line == other.line else (self.line < other.line)
    
    def to_dict(self):
        return {'line': self.line, 'character': self.character}


@dataclass
class Range:
    start: Position
    end: Position

    def calculate_length(self, text: str) -> int:
        text_lines = text.splitlines()
        if self.end.line == self.start.line:
            line = text_lines[self.start.line]
            return len(line[self.start.character : self.end.character])
        else:
            total = len(text_lines[self.start.line][self.start.character :])
            for line_number in range(self.start.line + 1, self.end.line):
                total += len(text_lines[line_number])
            total += len(text_lines[self.end.line][: self.end.character])
            return total
    
    def to_dict(self):
        return {
            'start': self.start.to_dict() if hasattr(self.start, 'to_dict') else asdict(self.start),
            'end': self.end.to_dict() if hasattr(self.end, 'to_dict') else asdict(self.end)
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            start=Position(**data['start']),
            end=Position(**data['end'])
        )


@dataclass
class TextDocumentContentChangeEvent:
    text: str
    range: Optional[Range] = None
    rangeLength: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {}
        d['text'] = self.text
        if self.range is not None:
            d['range'] = self.range.to_dict()
        if self.rangeLength is not None:
            d['rangeLength'] = self.rangeLength
        return d

    @classmethod
    def range_change(cls, change_start: Position, change_end: Position,
                     change_text: str, old_text: str):
        change_range = Range(start=change_start, end=change_end)
        return cls(
            range=change_range,
            rangeLength=change_range.calculate_length(old_text),
            text=change_text,
        )

    @classmethod
    def whole_document_change(cls, change_text: str):
        return cls(text=change_text, range=None, rangeLength=None)


@dataclass
class TextDocumentPosition:
    textDocument: TextDocumentIdentifier
    position: Position
    
    def to_dict(self):
        return {
            'textDocument': self.textDocument.to_dict(),
            'position': self.position.to_dict()
        }


class CompletionTriggerKind(enum.IntEnum):
    INVOKED = 1
    TRIGGER_CHARACTER = 2
    TRIGGER_FOR_INCOMPLETE_COMPLETIONS = 3


@dataclass
class CompletionContext:
    triggerKind: CompletionTriggerKind
    triggerCharacter: Optional[str] = None
    
    def to_dict(self, exclude_unset=False):
        d = {'triggerKind': int(self.triggerKind)}
        if not exclude_unset or self.triggerCharacter is not None:
            if self.triggerCharacter is not None:
                d['triggerCharacter'] = self.triggerCharacter
        return d


class MarkupKind(enum.Enum):
    PLAINTEXT = "plaintext"
    MARKDOWN = "markdown"


@dataclass
class MarkupContent:
    kind: MarkupKind
    value: str


@dataclass
class TextEdit:
    range: Range
    newText: str
    annotationId: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            range=Range.from_dict(data['range']),
            newText=data['newText'],
            annotationId=data.get('annotationId')
        )


@dataclass
class TextDocumentEdit:
    textDocument: OptionalVersionedTextDocumentIdentifier
    edits: List[TextEdit]
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            textDocument=OptionalVersionedTextDocumentIdentifier(**data['textDocument']),
            edits=[TextEdit.from_dict(e) for e in data['edits']]
        )


@dataclass
class Command:
    title: str
    command: str
    arguments: Optional[List[Any]] = None


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


@dataclass
class CompletionItem:
    label: str
    kind: Optional[CompletionItemKind] = None
    tags: Optional[List[CompletionItemTag]] = None
    detail: Optional[str] = None
    documentation: Union[str, MarkupContent, None] = None
    deprecated: Optional[bool] = None
    preselect: Optional[bool] = None
    sortText: Optional[str] = None
    filterText: Optional[str] = None
    insertText: Optional[str] = None
    insertTextFormat: Optional[InsertTextFormat] = None
    textEdit: Optional[TextEdit] = None
    additionalTextEdits: Optional[List[TextEdit]] = None
    commitCharacters: Optional[List[str]] = None
    command: Optional[Command] = None
    data: Optional[Any] = None


@dataclass
class CompletionList:
    isIncomplete: bool
    items: List[CompletionItem]


class TextDocumentSaveReason(enum.IntEnum):
    MANUAL = 1
    AFTER_DELAY = 2
    FOCUS_OUT = 3


@dataclass
class Location:
    uri: str
    range: Range


@dataclass
class LocationLink:
    targetUri: str
    targetRange: Range
    targetSelectionRange: Range
    originSelectionRange: Optional[Range] = None


@dataclass
class DiagnosticRelatedInformation:
    location: Location
    message: str


class DiagnosticSeverity(enum.IntEnum):
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4

    def short_name(self):
        return {self.ERROR:'Err', self.WARNING:'Wrn', self.INFORMATION:'Inf',
                self.HINT:'Hint'}[self]


@dataclass
class Diagnostic:
    range: Range
    message: str
    severity: Optional[DiagnosticSeverity] = None
    code: Optional[Union[int, str]] = None
    source: Optional[str] = None
    relatedInformation: Optional[List[DiagnosticRelatedInformation]] = None


@dataclass
class MarkedString:
    language: str
    value: str


@dataclass
class ParameterInformation:
    label: Union[str, Tuple[int, int]]
    documentation: Optional[Union[str, MarkupContent]] = None


@dataclass
class SignatureInformation:
    label: str
    documentation: Optional[Union[MarkupContent, str]] = None
    parameters: Optional[List[ParameterInformation]] = None
    activeParameter: Optional[int] = None


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


@dataclass
class CallHierarchyItem:
    name: str
    kind: SymbolKind
    uri: str
    range: Range
    selectionRange: Range
    tags: Optional[SymbolTag] = None
    detail: Optional[str] = None
    data: Optional[Any] = None


@dataclass
class CallHierarchyIncomingCall:
    from_: CallHierarchyItem
    fromRanges: List[Range]


@dataclass
class CallHierarchyOutgoingCall:
    to: CallHierarchyItem
    fromRanges: List[Range]


class TextDocumentSyncKind(enum.IntEnum):
    NONE = 0
    FULL = 1
    INCREMENTAL = 2


@dataclass
class SymbolInformation:
    name: str
    kind: SymbolKind
    location: Location
    tags: Optional[List[SymbolTag]] = None
    deprecated: Optional[bool] = None
    containerName: Optional[str] = None

    def mpos(self):
        return self.location.range.start.character, self.location.range.start.line


@dataclass
class InlayHintLabelPart:
    value: str
    tooltip: Optional[Union[str, MarkupContent]] = None
    location: Optional[Location] = None
    command: Optional[Command] = None


class InlayHintKind(enum.IntEnum):
    TYPE = 1
    PARAMETER = 2


@dataclass
class InlayHint:
    position: Position
    label: Union[str, List[InlayHintLabelPart]]
    kind: Optional[InlayHintKind] = None
    textEdits: Optional[List[TextEdit]] = None
    tooltip: Optional[Union[str, MarkupContent]] = None
    paddingLeft: Optional[bool] = None
    paddingRight: Optional[bool] = None
    data: Optional[Any] = None


@dataclass
class FoldingRange:
    startLine: int
    endLine: int
    startCharacter: Optional[int] = None
    endCharacter: Optional[int] = None
    kind: Optional[str] = None
    collapsedText: Optional[str] = None


@dataclass
class DocumentSymbol:
    name: str
    kind: SymbolKind
    range: Range
    selectionRange: Range
    detail: Optional[str] = None
    tags: Optional[List[SymbolTag]] = None
    deprecated: Optional[bool] = None
    children: Optional[List['DocumentSymbol']] = None

    def mpos(self):
        return self.selectionRange.start.character, self.selectionRange.start.line


@dataclass
class Registration:
    id: str
    method: str
    registerOptions: Optional[Any] = None


@dataclass
class DocumentFilter:
    language: Optional[str] = None
    scheme: Optional[str] = None
    pattern: Optional[str] = None


DocumentSelector = List[DocumentFilter]


@dataclass
class CompletionOptionsCompletionItem:
    labelDetailsSupport: Optional[bool] = None


@dataclass
class CompletionRegistrationOptions:
    documentSelector: Union[DocumentSelector, None] = None
    triggerCharacters: Optional[List[str]] = None
    allCommitCharacters: Optional[List[str]] = None
    resolveProvider: Optional[bool] = None
    completionItem: Optional[CompletionOptionsCompletionItem] = None


@dataclass
class FormattingOptions:
    tabSize: int
    insertSpaces: bool
    trimTrailingWhitespace: Optional[bool] = None
    insertFinalNewline: Optional[bool] = None
    trimFinalNewlines: Optional[bool] = None
    
    def to_dict(self):
        return asdict(self)


@dataclass
class WorkspaceFolder:
    uri: str
    name: str
    
    def to_dict(self):
        return asdict(self)


@dataclass
class ProgressValue:
    pass


@dataclass
class WorkDoneProgressValue:
    pass


class MWorkDoneProgressKind(enum.Enum):
    BEGIN = "begin"
    REPORT = "report"
    END = "end"


@dataclass
class WorkDoneProgressBeginValue:
    kind: str  # Literal["begin"]
    title: str
    cancellable: Optional[bool] = None
    message: Optional[str] = None
    percentage: Optional[int] = None


@dataclass
class WorkDoneProgressReportValue:
    kind: str  # Literal["report"]
    cancellable: Optional[bool] = None
    message: Optional[str] = None
    percentage: Optional[int] = None


@dataclass
class WorkDoneProgressEndValue:
    kind: str  # Literal["end"]
    message: Optional[str] = None


@dataclass
class ConfigurationItem:
    scopeUri: Optional[str] = None
    section: Optional[str] = None
