"""
Helper functions for parsing LSP protocol dicts into dataclass objects.
Replaces Pydantic's model_validate() and TypeAdapter functionality.
"""

from typing import Any, Dict, List, Optional, Union
from .structs import (
    Position, Range, Location, LocationLink,
    MarkedString, MarkupContent, MarkupKind,
    TextEdit, TextDocumentEdit,
    SignatureInformation, ParameterInformation,
    Diagnostic, DiagnosticSeverity, DiagnosticRelatedInformation,
    CallHierarchyItem, SymbolKind,
)


def parse_position(data: dict) -> Position:
    """Parse Position from dict."""
    return Position(line=data['line'], character=data['character'])


def parse_range(data: dict) -> Range:
    """Parse Range from dict."""
    return Range(
        start=parse_position(data['start']),
        end=parse_position(data['end'])
    )


def parse_location(data: dict) -> Location:
    """Parse Location from dict."""
    return Location(
        uri=data['uri'],
        range=parse_range(data['range'])
    )


def parse_location_link(data: dict) -> LocationLink:
    """Parse LocationLink from dict."""
    origin_range = parse_range(data['originSelectionRange']) if data.get('originSelectionRange') else None
    return LocationLink(
        targetUri=data['targetUri'],
        targetRange=parse_range(data['targetRange']),
        targetSelectionRange=parse_range(data['targetSelectionRange']),
        originSelectionRange=origin_range
    )


def parse_text_edit(data: dict) -> TextEdit:
    """Parse TextEdit from dict."""
    return TextEdit(
        range=parse_range(data['range']),
        newText=data['newText'],
        annotationId=data.get('annotationId')
    )


def parse_text_edits_list(data: Optional[list]) -> Optional[List[TextEdit]]:
    """Parse list of TextEdit from list of dicts."""
    if data is None:
        return None
    return [parse_text_edit(item) for item in data]


def parse_marked_string(data: Union[str, dict]) -> Union[MarkedString, str]:
    """Parse MarkedString from dict or string."""
    if isinstance(data, str):
        return data
    return MarkedString(language=data['language'], value=data['value'])


def parse_markup_content(data: Union[str, dict]) -> Union[MarkupContent, str]:
    """Parse MarkupContent from dict or string."""
    if isinstance(data, str):
        return data
    kind_str = data.get('kind', 'plaintext')
    kind = MarkupKind.MARKDOWN if kind_str == 'markdown' else MarkupKind.PLAINTEXT
    return MarkupContent(kind=kind, value=data['value'])


def parse_parameter_information(data: dict) -> ParameterInformation:
    """Parse ParameterInformation from dict."""
    label = data['label']
    # Label can be string or [start, end] tuple
    if isinstance(label, list):
        label = tuple(label)
    
    doc = data.get('documentation')
    if doc and isinstance(doc, dict):
        doc = parse_markup_content(doc)
    
    return ParameterInformation(label=label, documentation=doc)


def parse_signature_information(data: dict) -> SignatureInformation:
    """Parse SignatureInformation from dict."""
    doc = data.get('documentation')
    if doc and isinstance(doc, dict):
        doc = parse_markup_content(doc)
    
    params = data.get('parameters')
    if params:
        params = [parse_parameter_information(p) for p in params]
    
    return SignatureInformation(
        label=data['label'],
        documentation=doc,
        parameters=params,
        activeParameter=data.get('activeParameter')
    )


def parse_diagnostic_related_info(data: dict) -> DiagnosticRelatedInformation:
    """Parse DiagnosticRelatedInformation from dict."""
    return DiagnosticRelatedInformation(
        location=parse_location(data['location']),
        message=data['message']
    )


def parse_diagnostic(data: dict) -> Diagnostic:
    """Parse Diagnostic from dict."""
    severity = data.get('severity')
    if severity is not None:
        severity = DiagnosticSeverity(severity)
    
    related_info = data.get('relatedInformation')
    if related_info:
        related_info = [parse_diagnostic_related_info(ri) for ri in related_info]
    
    return Diagnostic(
        range=parse_range(data['range']),
        message=data['message'],
        severity=severity,
        code=data.get('code'),
        source=data.get('source'),
        relatedInformation=related_info
    )


def parse_call_hierarchy_item(data: dict) -> CallHierarchyItem:
    """Parse CallHierarchyItem from dict."""
    return CallHierarchyItem(
        name=data['name'],
        kind=SymbolKind(data['kind']),
        uri=data['uri'],
        range=parse_range(data['range']),
        selectionRange=parse_range(data['selectionRange']),
        tags=data.get('tags'),
        detail=data.get('detail'),
        data=data.get('data')
    )


def parse_location_or_link_list(data: Optional[Union[dict, list]]) -> Optional[Union[Location, List[Union[Location, LocationLink]]]]:
    """Parse result that can be Location, LocationLink, or list of either."""
    if data is None:
        return None
    
    if isinstance(data, dict):
        # Single Location or LocationLink
        if 'targetUri' in data:
            return parse_location_link(data)
        else:
            return parse_location(data)
    
    if isinstance(data, list):
        if not data:
            return []
        
        # List of Location or LocationLink
        result = []
        for item in data:
            if 'targetUri' in item:
                result.append(parse_location_link(item))
            else:
                result.append(parse_location(item))
        return result
    
    return None
