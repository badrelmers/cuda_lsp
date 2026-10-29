import sys
import os
import socket
import time
import json
import queue
import subprocess
import re
from threading import Thread
from collections import namedtuple, defaultdict
from cattrs.errors import BaseValidationError
from cattrs.v import transform_error
import exceptiongroup
from lsprotocol import types as lsp_types

import email.parser
import email.message

from wcmatch.glob import globmatch, GLOBSTAR, BRACE

from cudatext import *
import cudax_lib as appx
import cudatext_cmd as cmds

from cudax_lib import get_translation, html_color_to_int
_ = get_translation(__file__)

from .util import (
        get_first,
        ed_uri,
        get_visible_eds,
        get_word,
        get_nonwords_chars,
        replace_on_right,
        split_text_by_length,
        uri_to_path,
        path_to_uri,
        langid2lex,
        collapse_path,
        normalize_drive_letter,
        replace_unbracketed,
        TimerScheduler,

        ValidationError,
    )
from .dlg import Hint, PanelLog, SignaturesDialog, TYPE_DIAG, SEVERITY_ERR, SEVERITY_LOG, SEVERITY_MAP
from .book import EditorDoc

import urllib.parse

from .sansio_lsp_client import client as lsp
from .snippet_engine import Snippet, VS_SNIPPET

import traceback
import datetime

# stderr errors are always printed to the bottom LSP panel
LOG = True
LOG_CACHE = False
DEBUG_COMPLETION = False
DEBUG_MESSAGES = True
DBG = LOG
LOG_NAME = 'LSP'

DEBUG_DEV = True  # enable spying request/response messages panel
SPY_MSG_LIMIT = 3000

api_ver = app_api_version()

IS_WIN = os.name=='nt'
IS_MAC = sys.platform=='darwin'
CMD_OS_KEY = 'cmd_windows' if IS_WIN else ('cmd_macos' if IS_MAC else 'cmd_unix')

SNIP_ID = 'cuda_lsp__snip'

TCP_CONNECT_TIMEOUT = 5     # sec
MAX_FORMAT_ON_SAVE_WAIT = 1  # sec
MIN_TIMER_TIME = 10     # ms
MAX_TIMER_TIME = 10     # ms

GOTO_EVENT_TYPES = {
    lsp_types.DefinitionResponse,
    lsp_types.ReferencesResponse,
    lsp_types.ImplementationResponse,
    lsp_types.TypeDefinitionResponse,
    lsp_types.DeclarationResponse,
}
CALLABLE_COMPLETIONS = {
    lsp_types.CompletionItemKind.Method,
    lsp_types.CompletionItemKind.Function,
    lsp_types.CompletionItemKind.Constructor,
}

RequestPos = namedtuple('RequestPos', 'h_ed carets target_pos_caret cursor_ed')
CachedCompletion = namedtuple('CachedCompletion', 'obj message_id items filtered_items carets h_ed line_str is_incomplete')
CompletionEdit = namedtuple('CompletionEdit', 'replace_range replace_text x y word1 word2 is_callable is_snippet cached_x')
Test = namedtuple('Test', 'lexer initial_text replace_range replace_text result_text is_callable is_snippet')

GOTO_TITLES = {
    lsp_types.DefinitionResponse:      _('Go to: definition'),
    lsp_types.ReferencesResponse:      _('Go to: references'),
    lsp_types.ImplementationResponse:  _('Go to: implementation'),
    lsp_types.TypeDefinitionResponse:  _('Go to: type definition'),
    lsp_types.DeclarationResponse:     _('Go to: declaration'),
}

[... The file is too long to show in full. I'll provide the key changes needed for the message handling section ...]

class Language:
    # ... [keep all class variables as before] ...
    
    def _on_lsp_msg(self, msg, message_id=None):
        if DEBUG_MESSAGES:
            self._dbg_msgs = (self._dbg_msgs + [msg])[-128:]

        # Handle initialization
        if isinstance(msg, dict) and msg.get('_initialized'):
            self.scfg = ServerConfig(msg, self.langids, self.lang_str)
            app_proc(PROC_EXEC_PLUGIN, 'cuda_lsp,on_lang_inited,'+self.name)
            return

        # Handle shutdown
        if isinstance(msg, dict) and msg.get('_shutdown'):
            print(f'{LOG_NAME}: {self.lang_str}[{self.client_state_str}] - got shutdown response, exiting')
            self.client.exit()
            self.process_queues()
            self.shutdown_start_time = time.time()
            return

        # Handle completion
        if isinstance(msg, dict) and msg.get('_completion'):
            reqpos = self.request_positions.pop(message_id, None)
            completion_list = msg.get('completion_list')
            
            if completion_list:
                items = completion_list['items']
            else:
                items = []
                completion_list = {'isIncomplete': False}

            if reqpos:
                try:
                    compl = CompletionMan(self, carets=reqpos.carets, h_ed=reqpos.h_ed)
                    _last_complete = compl.prepare_complete(message_id, items, completion_list.get('isIncomplete', False))
                    if _last_complete:
                        self._last_complete = _last_complete
                        compl.show_complete(self._last_complete.message_id, self._last_complete.filtered_items)
                except AssertionError as e:
                    print("NOTE:", e)
            return

        # Handle hover
        if isinstance(msg, lsp_types.Hover):
            if message_id in self.request_positions:
                _reqpos = self.request_positions.pop(message_id)
                
                if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed:
                    contents = msg.contents
                    if not isinstance(contents, list):
                        items = [contents] if contents else []
                    else:
                        items = contents

                    if items:
                        def parse_item(item):
                            if isinstance(item, str):
                                return item, lsp_types.MarkupKind.Markdown, None
                            if isinstance(item, lsp_types.MarkupContent):
                                return item.value, item.kind, None
                            if hasattr(item, 'language') and hasattr(item, 'value'):
                                lang = item.language
                                val = f"```{lang}\n{item.value}\n```"
                                return val, lsp_types.MarkupKind.Markdown, lang
                            return str(item), lsp_types.MarkupKind.PlainText, None

                        parsed_items = [parse_item(it) for it in items]
                        _, main_kind, main_lang = parsed_items[0]
                        full_text = "\n\n---\n\n".join(it[0] for it in parsed_items)

                        filtered_cmds = self.scfg.filter_commands(self._caret_cmds)
                        Hint.show(
                            full_text,
                            caret=_reqpos.target_pos_caret,
                            cursor_loc_start=_reqpos.cursor_ed,
                            markupkind=main_kind,
                            language=main_lang,
                            caret_cmds=filtered_cmds,
                        )
                    else:
                        msg_status(f'{LOG_NAME}: {self.lang_str}: Hover - no info')
            return

        # Handle signature help
        if isinstance(msg, lsp_types.SignatureHelp):
            if message_id in self.request_positions:
                _reqpos = self.request_positions.pop(message_id)
                if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed:
                    signatures = msg.signatures
                    if signatures:
                        SignaturesDialog.set_text((signatures, msg.active_signature, msg.active_parameter))
                        SignaturesDialog.show()
                    else:
                        SignaturesDialog.hide()
                        msg_status(f'{LOG_NAME}: {self.lang_str}: Signature help - no info')
            return

        # Handle semantic tokens
        if isinstance(msg, lsp_types.SemanticTokens):
            reqpos = self.request_positions.pop(message_id)
            self.on_semantic_tokens(reqpos.h_ed, resultId=msg.resultId, data=msg.data)
            return

        # Handle GOTOs
        if type(msg) in GOTO_EVENT_TYPES:
            skip_dlg = type(msg) == lsp_types.DefinitionResponse
            dlg_caption = GOTO_TITLES.get(type(msg), f'Go to {type(msg).__name__}')
            reqpos = self.request_positions.pop(message_id)
            self.do_goto(items=msg.result, dlg_caption=dlg_caption, skip_dlg=skip_dlg, reqpos=reqpos)
            return

        # Handle formatting responses
        if isinstance(msg, (lsp_types.DocumentFormattingResponse, lsp_types.DocumentRangeFormattingResponse)):
            if message_id in self.request_positions:
                _reqpos = self.request_positions.pop(message_id)
                if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed:
                    ed.set_prop(PROP_RO, False)

                    if msg.result:
                        if msg.result[0].range.start.line < msg.result[-1].range.start.line:
                            msg.result.reverse()
                        msg.result.sort(reverse=True, key=lambda x: x.range.start)
                        for edit in msg.result:
                            EditorDoc.apply_edit(ed, edit)
                    else:
                        msg_status(f'{LOG_NAME}: {self.lang_str}: Document formatting - no info')
            return

        # Handle diagnostics
        if isinstance(msg, lsp_types.PublishDiagnosticsParams):
            if IS_WIN:
                msg.uri = normalize_drive_letter(msg.uri)
            self.diagnostics_man.set_diagnostics(uri=msg.uri, diag_list=msg.diagnostics)
            return

        # Handle configuration request
        if isinstance(msg, dict) and msg.get('_configuration_request'):
            cfgs = [ServerConfig.get_configuration(self._cfg, cfgitem) for cfgitem in msg['items']]
            self.client._send_response(msg['_id'], cfgs)
            return

        # Handle log/show messages
        if isinstance(msg, lsp_types.LogMessageParams):
            if self._shutting_down is not None:
                return
            severity_str = SEVERITY_MAP[msg.type.value]
            self.plog.log_str(msg.message, type_=type(msg), severity=severity_str, scroll=True)
            return

        if isinstance(msg, lsp_types.ShowMessageParams):
            severity_str = SEVERITY_MAP[msg.type.value]
            self.plog.log_str(msg.message, type_=type(msg), severity=severity_str, scroll=True)
            return

        # Handle response errors
        if isinstance(msg, lsp_types.ResponseError):
            _reqpos = self.request_positions.pop(message_id, None)
            data = self.metadata_goto_requests.pop(message_id, None)
            if data:
                errstr = f'OmniSharp Metadata ResponseError[{msg.code}]: {msg.message}'
                self.plog.log_str(errstr, type_=_('Response Error'), severity=SEVERITY_ERR)
            else:
                errstr = f'ResponseError[{msg.code}]: {msg.message}'
                self.plog.log_str(errstr, type_=_('Response Error'), severity=SEVERITY_ERR)
            return

        # Handle progress
        if isinstance(msg, dict) and msg.get('_progress_create'):
            self._on_progress({'create': True, 'token': msg['token'], '_id': msg['_id']})
            return
        if isinstance(msg, dict) and msg.get('_progress_begin'):
            self._on_progress({'begin': True, 'token': msg['token'], 'value': msg['value']})
            return
        if isinstance(msg, dict) and msg.get('_progress_report'):
            self._on_progress({'report': True, 'token': msg['token'], 'value': msg['value']})
            return
        if isinstance(msg, dict) and msg.get('_progress_end'):
            self._on_progress({'end': True, 'token': msg['token'], 'value': msg['value']})
            return

        # Handle workspace folders request
        if isinstance(msg, dict) and msg.get('_workspace_folders'):
            self.client._send_response(
                msg['_id'],
                None if self.workspace_folders is None else [lsp.Converter.unstructure(f) for f in self.workspace_folders]
            )
            return

        # Handle register capability
        if isinstance(msg, dict) and msg.get('_register_capability'):
            self.scfg.on_register(msg['registrations'])
            self.client._send_response(msg['_id'], {})
            self.process_queues()
            app_proc(PROC_EXEC_PLUGIN, 'cuda_lsp,on_lang_inited,'+self.name)
            return

        # Handle document symbols
        if isinstance(msg, dict) and msg.get('_document_symbols'):
            _reqpos = self.request_positions.pop(message_id)
            if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed and self.treeman:
                self.treeman.fill_tree(msg['result'])
            return

        # Handle metadata
        if isinstance(msg, dict) and msg.get('_metadata'):
            data = self.metadata_goto_requests.pop(message_id, None)
            if data:
                reqpos, targetrange, dlg_caption = data
                self._handle_metadata(msg['result'], targetrange, reqpos, dlg_caption)
            else:
                print(f'{LOG_NAME}: {self.lang_str} - unknown Metadata id: {message_id}')
            return

        print(f'{LOG_NAME}: {self.lang_str} - unknown Message type: {type(msg)}')

    def _on_progress(self, msg):
        if msg.get('create'):
            self.progresses.setdefault(msg['token'], None)
            self.client._send_response(msg['_id'], None)
            return

        token = msg['token']
        val = msg['value']
        
        if msg.get('begin'):
            self.progresses[token] = msg
            title = val.title
            msg_str = f': {val.message}' if val.message else ''
        elif msg.get('report'):
            title = self.progresses[token]['value'].title
            msg_str = ''
            if val.message:
                msg_str = f': {val.message}'
            elif val.percentage is not None:
                msg_str = f' [{val.percentage}%]'
        elif msg.get('end'):
            title = self.progresses.pop(token)['value'].title
            msg_str = f': {val.message}' if val.message else ' [Done]'
        else:
            return

        if title:
            msg_status(f'{LOG_NAME}: {self.lang_str} - {title + msg_str}')

    # ... [rest of the methods remain largely the same] ...
