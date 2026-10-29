import enum
import typing as t

import attrs
from lsprotocol import converters, types as lsp_types

JSONDict = t.Dict[str, t.Any]
JSONList = t.List[t.Any]

Id = t.Union[int, str]


Converter = converters.get_converter()


@attrs.define
class Request:
    jsonrpc: str = attrs.field(default="2.0", init=False)
    method: str
    params: t.Optional[t.Union[JSONDict, JSONList]] = None
    id: t.Optional[Id] = None


@attrs.define
class Response:
    jsonrpc: str = attrs.field(default="2.0", init=False)
    id: t.Optional[Id]
    result: t.Optional[t.Union[JSONDict, JSONList]] = None
    error: t.Optional[JSONDict] = None


MessageType = lsp_types.MessageType
MessageActionItem = lsp_types.MessageActionItem
WorkspaceFolder = lsp_types.WorkspaceFolder
TextDocumentItem = lsp_types.TextDocumentItem
TextDocumentIdentifier = lsp_types.TextDocumentIdentifier
OptionalVersionedTextDocumentIdentifier = lsp_types.OptionalVersionedTextDocumentIdentifier
VersionedTextDocumentIdentifier = lsp_types.VersionedTextDocumentIdentifier
CompletionContext = lsp_types.CompletionContext
CompletionTriggerKind = lsp_types.CompletionTriggerKind
CompletionItem = lsp_types.CompletionItem
CompletionItemKind = lsp_types.CompletionItemKind
CompletionItemTag = lsp_types.CompletionItemTag
CompletionList = lsp_types.CompletionList
FormattingOptions = lsp_types.FormattingOptions
MarkupContent = lsp_types.MarkupContent
MarkupKind = lsp_types.MarkupKind
Command = lsp_types.Command
InsertTextFormat = lsp_types.InsertTextFormat
TextEdit = lsp_types.TextEdit
TextDocumentEdit = lsp_types.TextDocumentEdit
Location = lsp_types.Location
LocationLink = lsp_types.LocationLink
Diagnostic = lsp_types.Diagnostic
DiagnosticSeverity = lsp_types.DiagnosticSeverity
DiagnosticRelatedInformation = lsp_types.DiagnosticRelatedInformation
MarkedString = lsp_types.MarkedString
ParameterInformation = lsp_types.ParameterInformation
SignatureInformation = lsp_types.SignatureInformation
SymbolKind = lsp_types.SymbolKind
SymbolTag = lsp_types.SymbolTag
CallHierarchyItem = lsp_types.CallHierarchyItem
CallHierarchyIncomingCall = lsp_types.CallHierarchyIncomingCall
CallHierarchyOutgoingCall = lsp_types.CallHierarchyOutgoingCall
TextDocumentSyncKind = lsp_types.TextDocumentSyncKind
SymbolInformation = lsp_types.SymbolInformation
InlayHint = lsp_types.InlayHint
InlayHintKind = lsp_types.InlayHintKind
InlayHintLabelPart = lsp_types.InlayHintLabelPart
FoldingRange = lsp_types.FoldingRange
Registration = lsp_types.Registration
DocumentFilter = lsp_types.DocumentFilter
CompletionOptions = lsp_types.CompletionOptions
CompletionRegistrationOptions = lsp_types.CompletionRegistrationOptions
ConfigurationItem = lsp_types.ConfigurationItem
ProgressToken = lsp_types.ProgressToken
WorkDoneProgressBeginValue = lsp_types.WorkDoneProgressBegin
WorkDoneProgressReportValue = lsp_types.WorkDoneProgressReport
WorkDoneProgressEndValue = lsp_types.WorkDoneProgressEnd


Range = lsp_types.Range
Position = lsp_types.Position
TextDocumentPosition = lsp_types.TextDocumentPositionParams
TextDocumentSaveReason = lsp_types.TextDocumentSaveReason


class WorkDoneProgressKind(str, enum.Enum):
    BEGIN = "begin"
    REPORT = "report"
    END = "end"


def _range_from_positions(change_start: Position, change_end: Position) -> Range:
    return Range(start=change_start, end=change_end)


def make_text_document_content_change_event(
    change_start: Position,
    change_end: Position,
    change_text: str,
    old_text: str,
) -> lsp_types.TextDocumentContentChangeEvent:
    change_range = Range(start=change_start, end=change_end)
    range_length = change_range.calculate_length(old_text)
    return lsp_types.TextDocumentContentChangePartial(
        range=change_range,
        text=change_text,
        range_length=range_length,
    )


def make_whole_document_change_event(change_text: str) -> lsp_types.TextDocumentContentChangeEvent:
    return lsp_types.TextDocumentContentChangeWholeDocument(text=change_text)


def unstructure(obj: t.Any) -> t.Any:
    return Converter.unstructure(obj)


def structure(data: t.Any, typ: t.Type[t.Any]) -> t.Any:
    return Converter.structure(data, typ)


def _range_calculate_length(self: Range, text: str) -> int:
    text_lines = text.splitlines()

    if self.end.line == self.start.line:
        line = text_lines[self.start.line]
        return len(line[self.start.character : self.end.character])

    total = 0
    total += len(text_lines[self.start.line][self.start.character :])

    for line_number in range(self.start.line + 1, self.end.line):
        total += len(text_lines[line_number])

    total += len(text_lines[self.end.line][: self.end.character])

    return total


Range.calculate_length = _range_calculate_length  # type: ignore[attr-defined]
