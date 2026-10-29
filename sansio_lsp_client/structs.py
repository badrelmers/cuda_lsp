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




TextDocumentContentChangeEvent = t.Union[
    lsp_types.TextDocumentContentChangePartial,
    lsp_types.TextDocumentContentChangeWholeDocument,
]
CallHierarchyIncomingCall = lsp_types.CallHierarchyIncomingCall
CallHierarchyItem = lsp_types.CallHierarchyItem
CallHierarchyOutgoingCall = lsp_types.CallHierarchyOutgoingCall
Command = lsp_types.Command
CompletionContext = lsp_types.CompletionContext
CompletionItem = lsp_types.CompletionItem
CompletionItemKind = lsp_types.CompletionItemKind
CompletionItemTag = lsp_types.CompletionItemTag
CompletionList = lsp_types.CompletionList
CompletionOptions = lsp_types.CompletionOptions
CompletionRegistrationOptions = lsp_types.CompletionRegistrationOptions
CompletionTriggerKind = lsp_types.CompletionTriggerKind
ConfigurationItem = lsp_types.ConfigurationItem
Diagnostic = lsp_types.Diagnostic
DiagnosticRelatedInformation = lsp_types.DiagnosticRelatedInformation
DiagnosticSeverity = lsp_types.DiagnosticSeverity
DocumentFilter = lsp_types.DocumentFilter
DocumentSymbol = lsp_types.DocumentSymbol
FoldingRange = lsp_types.FoldingRange
FormattingOptions = lsp_types.FormattingOptions
InlayHint = lsp_types.InlayHint
InlayHintKind = lsp_types.InlayHintKind
InlayHintLabelPart = lsp_types.InlayHintLabelPart
InsertTextFormat = lsp_types.InsertTextFormat
MarkedString = lsp_types.MarkedString
MarkupContent = lsp_types.MarkupContent
MarkupKind = lsp_types.MarkupKind
MessageActionItem = lsp_types.MessageActionItem
MessageType = lsp_types.MessageType
OptionalVersionedTextDocumentIdentifier = lsp_types.OptionalVersionedTextDocumentIdentifier
ParameterInformation = lsp_types.ParameterInformation
Position = lsp_types.Position
ProgressToken = lsp_types.ProgressToken
Range = lsp_types.Range
Registration = lsp_types.Registration
SignatureInformation = lsp_types.SignatureInformation
SymbolInformation = lsp_types.SymbolInformation
SymbolKind = lsp_types.SymbolKind
SymbolTag = lsp_types.SymbolTag
TextDocumentEdit = lsp_types.TextDocumentEdit
TextDocumentIdentifier = lsp_types.TextDocumentIdentifier
TextDocumentItem = lsp_types.TextDocumentItem
TextDocumentPosition = lsp_types.TextDocumentPositionParams
TextDocumentSaveReason = lsp_types.TextDocumentSaveReason
TextDocumentSyncKind = lsp_types.TextDocumentSyncKind
TextEdit = lsp_types.TextEdit
VersionedTextDocumentIdentifier = lsp_types.VersionedTextDocumentIdentifier
WorkDoneProgressBeginValue = lsp_types.WorkDoneProgressBegin
WorkDoneProgressEndValue = lsp_types.WorkDoneProgressEnd
WorkDoneProgressReportValue = lsp_types.WorkDoneProgressReport
WorkspaceFolder = lsp_types.WorkspaceFolder


class WorkDoneProgressKind(str, enum.Enum):
    BEGIN = "begin"
    REPORT = "report"
    END = "end"


MWorkDoneProgressKind = WorkDoneProgressKind


def _range_from_positions(change_start: Position, change_end: Position) -> Range:
    return Range(start=change_start, end=change_end)

#TODO dellllll
def make_text_document_content_change_event(
    change_start: Position,
    change_end: Position,
    change_text: str,
    old_text: str,
) -> lsp_types.TextDocumentContentChangePartial:
    change_range = Range(start=change_start, end=change_end)
    range_length = change_range.calculate_length(old_text)
    return lsp_types.TextDocumentContentChangePartial(
        range=change_range,
        text=change_text,
        range_length=range_length,
    )

#TODO dellllll
def make_whole_document_change_event(change_text: str) -> lsp_types.TextDocumentContentChangeWholeDocument:
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
