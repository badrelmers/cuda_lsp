import enum
from dataclasses import dataclass, field, asdict
import typing as t

# Type aliases
JSONDict = t.Dict[str, t.Any]
JSONList = t.List[t.Any]
Id = t.Union[int, str]
ProgressToken = t.Union[int, str]


@dataclass
class Request:
    method: str
    id: t.Optional[Id] = None
    params: t.Optional[t.Union[t.List[t.Any], JSONDict]] = None


@dataclass
class Response:
    id: t.Optional[Id] = None
    result: t.Optional[t.Union[t.List[t.Any], JSONDict]] = None
    error: t.Optional[JSONDict] = None


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
    version: t.Optional[int] = None


@dataclass
class VersionedTextDocumentIdentifier:
    uri: str
    version: t.Optional[int] = None
    
    def to_dict(self):
        return asdict(self)


@dataclass
class Position:
    line: int
    character: int

    def as_tuple(self) -> t.Tuple[int, int]:
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
    range: t.Optional[Range] = None
    rangeLength: t.Optional[int] = None

    def to_dict(self) -> t.Dict[str, t.Any]:
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
    triggerCharacter: t.Optional[str] = None
    
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
    annotationId: t.Optional[str] = None
    
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
    edits: t.List[TextEdit]
    
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


@dataclass
class CompletionItem:
    label: str
    kind: t.Optional[CompletionItemKind] = None
    tags: t.Optional[t.List[CompletionItemTag]] = None
    detail: t.Optional[str] = None
    documentation: t.Union[str, MarkupContent, None] = None
    deprecated: t.Optional[bool] = None
    preselect: t.Optional[bool] = None
    sortText: t.Optional[str] = None
    filterText: t.Optional[str] = None
    insertText: t.Optional[str] = None
    insertTextFormat: t.Optional[InsertTextFormat] = None
    textEdit: t.Optional[TextEdit] = None
    additionalTextEdits: t.Optional[t.List[TextEdit]] = None
    commitCharacters: t.Optional[t.List[str]] = None
    command: t.Optional[Command] = None
    data: t.Optional[t.Any] = None


@dataclass
class CompletionList:
    isIncomplete: bool
    items: t.List[CompletionItem]


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
    originSelectionRange: t.Optional[Range] = None


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
    severity: t.Optional[DiagnosticSeverity] = None
    code: t.Optional[t.Union[int, str]] = None
    source: t.Optional[str] = None
    relatedInformation: t.Optional[t.List[DiagnosticRelatedInformation]] = None


@dataclass
class MarkedString:
    language: str
    value: str


@dataclass
class ParameterInformation:
    label: t.Union[str, t.Tuple[int, int]]
    documentation: t.Optional[t.Union[str, MarkupContent]] = None


@dataclass
class SignatureInformation:
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


@dataclass
class CallHierarchyItem:
    name: str
    kind: SymbolKind
    uri: str
    range: Range
    selectionRange: Range
    tags: t.Optional[SymbolTag] = None
    detail: t.Optional[str] = None
    data: t.Optional[t.Any] = None


@dataclass
class CallHierarchyIncomingCall:
    from_: CallHierarchyItem
    fromRanges: t.List[Range]


@dataclass
class CallHierarchyOutgoingCall:
    to: CallHierarchyItem
    fromRanges: t.List[Range]


class TextDocumentSyncKind(enum.IntEnum):
    NONE = 0
    FULL = 1
    INCREMENTAL = 2


@dataclass
class SymbolInformation:
    name: str
    kind: SymbolKind
    location: Location
    tags: t.Optional[t.List[SymbolTag]] = None
    deprecated: t.Optional[bool] = None
    containerName: t.Optional[str] = None

    def mpos(self):
        return self.location.range.start.character, self.location.range.start.line


@dataclass
class InlayHintLabelPart:
    value: str
    tooltip: t.Optional[t.Union[str, MarkupContent]] = None
    location: t.Optional[Location] = None
    command: t.Optional[Command] = None


class InlayHintKind(enum.IntEnum):
    TYPE = 1
    PARAMETER = 2


@dataclass
class InlayHint:
    position: Position
    label: t.Union[str, t.List[InlayHintLabelPart]]
    kind: t.Optional[InlayHintKind] = None
    textEdits: t.Optional[t.List[TextEdit]] = None
    tooltip: t.Optional[t.Union[str, MarkupContent]] = None
    paddingLeft: t.Optional[bool] = None
    paddingRight: t.Optional[bool] = None
    data: t.Optional[t.Any] = None


@dataclass
class FoldingRange:
    startLine: int
    endLine: int
    startCharacter: t.Optional[int] = None
    endCharacter: t.Optional[int] = None
    kind: t.Optional[str] = None
    collapsedText: t.Optional[str] = None


@dataclass
class DocumentSymbol:
    name: str
    kind: SymbolKind
    range: Range
    selectionRange: Range
    detail: t.Optional[str] = None
    tags: t.Optional[t.List[SymbolTag]] = None
    deprecated: t.Optional[bool] = None
    children: t.Optional[t.List['DocumentSymbol']] = None

    def mpos(self):
        return self.selectionRange.start.character, self.selectionRange.start.line


@dataclass
class Registration:
    id: str
    method: str
    registerOptions: t.Optional[t.Any] = None


@dataclass
class DocumentFilter:
    language: t.Optional[str] = None
    scheme: t.Optional[str] = None
    pattern: t.Optional[str] = None


DocumentSelector = t.List[DocumentFilter]


@dataclass
class CompletionOptionsCompletionItem:
    labelDetailsSupport: t.Optional[bool] = None


@dataclass
class CompletionRegistrationOptions:
    documentSelector: t.Union[DocumentSelector, None] = None
    triggerCharacters: t.Optional[t.List[str]] = None
    allCommitCharacters: t.Optional[t.List[str]] = None
    resolveProvider: t.Optional[bool] = None
    completionItem: t.Optional[CompletionOptionsCompletionItem] = None


@dataclass
class FormattingOptions:
    tabSize: int
    insertSpaces: bool
    trimTrailingWhitespace: t.Optional[bool] = None
    insertFinalNewline: t.Optional[bool] = None
    trimFinalNewlines: t.Optional[bool] = None
    
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
    cancellable: t.Optional[bool] = None
    message: t.Optional[str] = None
    percentage: t.Optional[int] = None


@dataclass
class WorkDoneProgressReportValue:
    kind: str  # Literal["report"]
    cancellable: t.Optional[bool] = None
    message: t.Optional[str] = None
    percentage: t.Optional[int] = None


@dataclass
class WorkDoneProgressEndValue:
    kind: str  # Literal["end"]
    message: t.Optional[str] = None


@dataclass
class ConfigurationItem:
    scopeUri: t.Optional[str] = None
    section: t.Optional[str] = None
