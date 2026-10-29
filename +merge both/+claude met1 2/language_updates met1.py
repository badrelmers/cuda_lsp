# Complete _on_lsp_msg method for language.py

def _on_lsp_msg(self, msg, message_id=None):
    if DEBUG_MESSAGES:
        self._dbg_msgs = (self._dbg_msgs + [msg])[-128:]

    msgtype = type(msg)

    if msgtype == lsp_types.InitializeResponse:
        self.scfg = ServerConfig(msg, self.langids, self.lang_str)
        print("ServerConfig msg", msg)
        app_proc(PROC_EXEC_PLUGIN, 'cuda_lsp,on_lang_inited,'+self.name)

    elif msgtype == lsp_types.RegisterCapabilityRequest:
        self.scfg.on_register(msg)
        self.client._send_response(id=msg.id, result={})
        self.process_queues()
        app_proc(PROC_EXEC_PLUGIN, 'cuda_lsp,on_lang_inited,'+self.name)

    elif msgtype == lsp_types.WorkspaceFoldersRequest:
        result = None if self.workspace_folders is None else [lsp.Converter.unstructure(f) for f in self.workspace_folders]
        self.client._send_response(id=msg.id, result=result)

    elif msgtype == lsp_types.CompletionResponse:
        reqpos = self.request_positions.pop(message_id, None)

        result = msg.result
        if result:
            if isinstance(result, lsp_types.CompletionList):
                items = result.items
                is_incomplete = result.is_incomplete or False
            elif isinstance(result, list):
                items = result
                is_incomplete = False
            else:
                items = []
                is_incomplete = False
        else:
            items = []
            is_incomplete = False

        if reqpos:
            try:
                compl = CompletionMan(self, carets=reqpos.carets, h_ed=reqpos.h_ed)
                pass;       LOG and print(f'got completion({len(items)}): {time.time():.3f} {message_id} in {list(self.request_positions)}')
                _last_complete = compl.prepare_complete(message_id, items, is_incomplete)
                if _last_complete:
                    self._last_complete = _last_complete
                    compl.show_complete(self._last_complete.message_id, self._last_complete.filtered_items)
            except AssertionError as e:
                print("NOTE:",e)

    elif msgtype == lsp_types.HoverResponse:
        if message_id in self.request_positions:
            _reqpos = self.request_positions.pop(message_id)
            
            if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed:
                # Extract hover contents
                result = msg.result
                if not result or not result.contents:
                    msg_status(f'{LOG_NAME}: {self.lang_str}: Hover - no info')
                    return
                
                # 1. Normalize contents to a list for consistent processing
                contents = result.contents
                if not isinstance(contents, list):
                    items = [contents] if contents else []
                else:
                    items = contents

                if items:
                    # 2. Define a parser for any version of LSP Hover content
                    def parse_item(item):
                        """Returns (text_value, markup_kind, language_id)"""
                        # Case: Simple string (Deprecated but common)
                        if isinstance(item, str):
                            return item, lsp_types.MarkupKind.Markdown, None
                        
                        # Case: MarkupContent (The modern standard)
                        if isinstance(item, lsp_types.MarkupContent):
                            return item.value, item.kind, None
                        
                        # Case: MarkedStringWithLanguage (Deprecated code blocks)
                        # We wrap this in markdown fences so the UI can highlight it.
                        if hasattr(item, 'language') and hasattr(item, 'value'):
                            lang = item.language
                            val = f"```{lang}\n{item.value}\n```"
                            return val, lsp_types.MarkupKind.Markdown, lang
                        
                        return str(item), lsp_types.MarkupKind.PlainText, None

                    # 3. Extract data from all items
                    parsed_items = [parse_item(it) for it in items]
                    
                    # Use the first item to determine the Hint's primary metadata
                    _, main_kind, main_lang = parsed_items[0]
                    
                    # 4. Combine all items into one string for display
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
                        
    elif msgtype == lsp_types.SignatureHelpResponse:
        if message_id in self.request_positions:
            _reqpos = self.request_positions.pop(message_id)
            if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed:
                result = msg.result
                if result and result.signatures:
                    signatures = result.signatures
                    active_signature = result.active_signature
                    active_parameter = result.active_parameter
                    
                    SignaturesDialog.set_text((signatures, active_signature, active_parameter))
                    SignaturesDialog.show()
                else:
                    SignaturesDialog.hide()
                    msg_status(f'{LOG_NAME}: {self.lang_str}: Signature help - no info')

    elif msgtype == lsp_types.SemanticTokensResponse:
        reqpos = self.request_positions.pop(message_id)
        result = msg.result
        if result:
            self.on_semantic_tokens(reqpos.h_ed, resultId=result.result_id, data=result.data)

    # GOTOs
    elif msgtype in GOTO_EVENT_TYPES:
        skip_dlg = msgtype == lsp_types.DefinitionResponse
        dlg_caption = GOTO_TITLES.get(msgtype, f'Go to {msgtype.__name__}')
        reqpos = self.request_positions.pop(message_id)
        self.do_goto(items=msg.result, dlg_caption=dlg_caption, skip_dlg=skip_dlg, reqpos=reqpos)

    elif msgtype == lsp_types.DocumentSymbolResponse:
        _reqpos = self.request_positions.pop(message_id)
        if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed  and  self.treeman:
            self.treeman.fill_tree(msg.result)

    elif msgtype == lsp_types.DocumentFormattingResponse or msgtype == lsp_types.DocumentRangeFormattingResponse:
        if message_id in self.request_positions:
            _reqpos = self.request_positions.pop(message_id)
            if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed:
                ed.set_prop(PROP_RO, False)  # doc is set 'RO' during format-on-save

                if msg.result:
                    # need reverse order for applying
                    # usually result are sorted by position (asc or desc) => reverse if [0] < [-1]
                    if msg.result[0].range.start.line < msg.result[-1].range.start.line:
                        msg.result.reverse()
                    # sort in descending order
                    msg.result.sort(reverse=True, key=lambda x:x.range.start)
                    for edit in msg.result:
                        EditorDoc.apply_edit(ed, edit)
                else:
                    msg_status(f'{LOG_NAME}: {self.lang_str}: Document formatting - no info')

    elif msgtype == lsp_types.PublishDiagnosticsNotification:
        if IS_WIN:
            msg.params.uri = normalize_drive_letter(msg.params.uri)
        self.diagnostics_man.set_diagnostics(uri=msg.params.uri, diag_list=msg.params.diagnostics)

    elif msgtype == lsp_types.ConfigurationRequest:
        cfgs = [ServerConfig.get_configuration(self._cfg, cfgitem) for cfgitem in msg.params.items]
        self.client._send_response(id=msg.id, result=cfgs)

    elif msgtype == lsp_types.LogMessageNotification:
        # abandoning server - ignore logs
        if self._shutting_down is not None:
            return
        # Convert to old format for logger
        severity_str = SEVERITY_MAP[msg.params.type.value]
        self.plog.log_str(msg.params.message, type_='log', severity=severity_str, scroll=True)

    elif msgtype == lsp_types.ShowMessageNotification:
        # Convert to old format for logger
        severity_str = SEVERITY_MAP[msg.params.type.value]
        self.plog.log_str(msg.params.message, type_='message', severity=severity_str, scroll=True)

    elif msgtype == ResponseError:
        _reqpos = self.request_positions.pop(message_id, None)  # discard
        data = self.metadata_goto_requests.pop(message_id, None)
        if data:
            # Log error for OmniSharp metadata
            errstr = f'OmniSharp Metadata ResponseError[{msg.code}]: {msg.message}'
            self.plog.log_str(errstr, type_=_('Response Error'), severity=SEVERITY_ERR)
        else:
            errstr = f'ResponseError[{msg.code}]: {msg.message}'
            self.plog.log_str(errstr, type_=_('Response Error'), severity=SEVERITY_ERR)

    elif isinstance(msg, lsp_types.WorkDoneProgressCreateRequest)  or  msgtype == lsp_types.ProgressNotification:
        self._on_progress(msg)

    elif msgtype == lsp_types.ShutdownResponse:
        print(f'{LOG_NAME}: {self.lang_str}[{self.client_state_str}] - got shutdown response, exiting')
        self.client.exit()
        self.process_queues()
        self.shutdown_start_time = time.time()

    elif msgtype == Metadata:
        data = self.metadata_goto_requests.pop(message_id, None)
        if data:
            reqpos, targetrange, dlg_caption = data
            self._handle_metadata(msg.result, targetrange, reqpos, dlg_caption)
        else:
            print(f'{LOG_NAME}: {self.lang_str} - unknown Metadata id: {message_id}')
            
    else:
        print(f'{LOG_NAME}: {self.lang_str} - unknown Message type: {msgtype}')


def _on_progress(self, msg):
    if isinstance(msg, lsp_types.WorkDoneProgressCreateRequest):
        # on buggy servers token can already exist at this stage.
        # such server bugs must be silently ignored without crashing our plugin.
        token = msg.params.token
        self.progresses.setdefault(token, None)  # set to None ONLY if it doesn't exist
        self.client._send_response(id=msg.id, result=None)

    elif isinstance(msg, lsp_types.ProgressNotification):
        token = msg.params.token
        val = msg.params.value
        title = None
        
        if isinstance(val, lsp_types.WorkDoneProgressBegin):
            self.progresses[token] = msg
            title = val.title
            msg_str = f': {val.message}'  if val.message else ''

        elif isinstance(val, lsp_types.WorkDoneProgressReport):
            if token in self.progresses:
                title = self.progresses[token].params.value.title
            msg_str = ''
            if val.message:
                msg_str = f': {val.message}'
            elif val.percentage is not None:
                msg_str = f' [{val.percentage}%]'

        elif isinstance(val, lsp_types.WorkDoneProgressEnd):
            if token in self.progresses:
                title = self.progresses.pop(token).params.value.title  # deletes start-message
            msg_str = f': {val.message}'  if val.message else  ' [Done]'

        if title:
            msg_status(f'{LOG_NAME}: {self.lang_str} - {title + msg_str}')

# 1. Update imports at the top of the file:
from .sansio_lsp_client import client as lsp
from .sansio_lsp_client.client import ResponseError, Metadata  # Import custom types
from lsprotocol import types as lsp_types

# 2. Remove old imports that no longer exist:
# DELETE: from .sansio_lsp_client import events
# DELETE: from .sansio_lsp_client.events import ShowMessage, LogMessage

# 3. Update type checking in _on_lsp_msg method:

def _on_lsp_msg(self, msg, message_id=None):
    if DEBUG_MESSAGES:
        self._dbg_msgs = (self._dbg_msgs + [msg])[-128:]

    msgtype = type(msg)

    # InitializeResponse instead of Initialized
    if msgtype == lsp_types.InitializeResponse:
        self.scfg = ServerConfig(msg, self.langids, self.lang_str)
        app_proc(PROC_EXEC_PLUGIN, 'cuda_lsp,on_lang_inited,'+self.name)

    elif msgtype == lsp_types.RegisterCapabilityRequest:
        self.scfg.on_register(msg)
        msg.reply() # send confirmation reply to server
        self.process_queues()
        app_proc(PROC_EXEC_PLUGIN, 'cuda_lsp,on_lang_inited,'+self.name)

    elif msgtype == lsp_types.WorkspaceFoldersRequest:
        msg.reply(folders=self.workspace_folders)

    elif msgtype == lsp_types.CompletionResponse:
        reqpos = self.request_positions.pop(message_id, None)
        
        # Extract completion items from response
        result = msg.result
        if result:
            if isinstance(result, lsp_types.CompletionList):
                items = result.items
                is_incomplete = result.is_incomplete or False
            elif isinstance(result, list):
                items = result
                is_incomplete = False
            else:
                items = []
                is_incomplete = False
        else:
            items = []
            is_incomplete = False

        if reqpos:
            try:
                compl = CompletionMan(self, carets=reqpos.carets, h_ed=reqpos.h_ed)
                _last_complete = compl.prepare_complete(message_id, items, is_incomplete)
                if _last_complete:
                    self._last_complete = _last_complete
                    compl.show_complete(self._last_complete.message_id, self._last_complete.filtered_items)
            except AssertionError as e:
                print("NOTE:",e)

    elif msgtype == lsp_types.HoverResponse:
        if message_id in self.request_positions:
            _reqpos = self.request_positions.pop(message_id)
            
            if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed:
                # Extract hover contents
                result = msg.result
                if not result or not result.contents:
                    msg_status(f'{LOG_NAME}: {self.lang_str}: Hover - no info')
                    return
                    
                contents = result.contents
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

    elif msgtype == lsp_types.SignatureHelpResponse:
        if message_id in self.request_positions:
            _reqpos = self.request_positions.pop(message_id)
            if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed:
                result = msg.result
                if result and result.signatures:
                    signatures = result.signatures
                    active_signature = result.active_signature
                    active_parameter = result.active_parameter
                    SignaturesDialog.set_text((signatures, active_signature, active_parameter))
                    SignaturesDialog.show()
                else:
                    SignaturesDialog.hide()
                    msg_status(f'{LOG_NAME}: {self.lang_str}: Signature help - no info')

    elif msgtype == lsp_types.SemanticTokensResponse:
        reqpos = self.request_positions.pop(message_id)
        result = msg.result
        if result:
            self.on_semantic_tokens(reqpos.h_ed, resultId=result.result_id, data=result.data)

    # GOTO responses
    elif msgtype in {lsp_types.DefinitionResponse, lsp_types.ReferencesResponse, 
                     lsp_types.ImplementationResponse, lsp_types.TypeDefinitionResponse,
                     lsp_types.DeclarationResponse}:
        skip_dlg = msgtype == lsp_types.DefinitionResponse
        dlg_caption = GOTO_TITLES.get(msgtype, f'Go to {msgtype.__name__}')
        reqpos = self.request_positions.pop(message_id)
        self.do_goto(items=msg.result, dlg_caption=dlg_caption, skip_dlg=skip_dlg, reqpos=reqpos)

    elif msgtype == lsp_types.DocumentSymbolResponse:
        _reqpos = self.request_positions.pop(message_id)
        if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed  and  self.treeman:
            self.treeman.fill_tree(msg.result)

    elif msgtype in {lsp_types.DocumentFormattingResponse, lsp_types.DocumentRangeFormattingResponse}:
        if message_id in self.request_positions:
            _reqpos = self.request_positions.pop(message_id)
            if ed.get_prop(PROP_HANDLE_SELF) == _reqpos.h_ed:
                ed.set_prop(PROP_RO, False)
                
                if msg.result:
                    # Sort edits in descending order
                    if msg.result[0].range.start.line < msg.result[-1].range.start.line:
                        msg.result.reverse()
                    msg.result.sort(reverse=True, key=lambda x:x.range.start)
                    for edit in msg.result:
                        EditorDoc.apply_edit(ed, edit)
                else:
                    msg_status(f'{LOG_NAME}: {self.lang_str}: Document formatting - no info')

    elif msgtype == lsp_types.PublishDiagnosticsNotification:
        if IS_WIN:
            msg.params.uri = normalize_drive_letter(msg.params.uri)
        self.diagnostics_man.set_diagnostics(uri=msg.params.uri, diag_list=msg.params.diagnostics)

    elif msgtype == lsp_types.ConfigurationRequest:
        cfgs = [ServerConfig.get_configuration(self._cfg, cfgitem) for cfgitem in msg.params.items]
        msg.reply(cfgs)

    elif msgtype == lsp_types.LogMessageNotification:
        if self._shutting_down is not None:
            return
        # Convert to old format for logger
        severity_str = SEVERITY_MAP[msg.params.type.value]
        self.plog.log_str(msg.params.message, type_='log', severity=severity_str, scroll=True)

    elif msgtype == lsp_types.ShowMessageNotification:
        # Convert to old format for logger
        severity_str = SEVERITY_MAP[msg.params.type.value]
        self.plog.log_str(msg.params.message, type_='message', severity=severity_str, scroll=True)

    elif msgtype == ResponseError:
        _reqpos = self.request_positions.pop(message_id, None)
        data = self.metadata_goto_requests.pop(message_id, None)
        if data:
            errstr = f'OmniSharp Metadata ResponseError[{msg.code}]: {msg.message}'
            self.plog.log_str(errstr, type_=_('Response Error'), severity=SEVERITY_ERR)
        else:
            errstr = f'ResponseError[{msg.code}]: {msg.message}'
            self.plog.log_str(errstr, type_=_('Response Error'), severity=SEVERITY_ERR)

    elif msgtype in {lsp_types.WorkDoneProgressCreateRequest, lsp_types.ProgressNotification}:
        self._on_progress(msg)

    elif msgtype == lsp_types.ShutdownResponse:
        print(f'{LOG_NAME}: {self.lang_str}[{self.client_state_str}] - got shutdown response, exiting')
        self.client.exit()
        self.process_queues()
        self.shutdown_start_time = time.time()

    elif msgtype == Metadata:
        data = self.metadata_goto_requests.pop(message_id, None)
        if data:
            reqpos, targetrange, dlg_caption = data
            self._handle_metadata(msg.result, targetrange, reqpos, dlg_caption)
        else:
            print(f'{LOG_NAME}: {self.lang_str} - unknown Metadata id: {message_id}')
            
    else:
        print(f'{LOG_NAME}: {self.lang_str} - unknown Message type: {msgtype}')


# 4. Update _on_progress method:
def _on_progress(self, msg):
    if isinstance(msg, lsp_types.WorkDoneProgressCreateRequest):
        # Token might already exist on buggy servers
        token = msg.params.token
        msg.reply()

    elif isinstance(msg, lsp_types.ProgressNotification):
        token = msg.params.token
        val = msg.params.value
        title = None
        
        if isinstance(val, lsp_types.WorkDoneProgressBegin):
            self.progresses[token] = msg
            title = val.title
            msg_str = f': {val.message}'  if val.message else ''

        elif isinstance(val, lsp_types.WorkDoneProgressReport):
            if token in self.progresses:
                start_msg = self.progresses[token]
                title = start_msg.params.value.title if hasattr(start_msg.params.value, 'title') else None
            msg_str = ''
            if val.message:
                msg_str = f': {val.message}'
            elif val.percentage is not None:
                msg_str = f' [{val.percentage}%]'

        elif isinstance(val, lsp_types.WorkDoneProgressEnd):
            if token in self.progresses:
                start_msg = self.progresses.pop(token)
                title = start_msg.params.value.title if hasattr(start_msg.params.value, 'title') else None
            msg_str = f': {val.message}'  if val.message else  ' [Done]'

        if title:
            msg_status(f'{LOG_NAME}: {self.lang_str} - {title + msg_str}')

# 5. Update GOTO_EVENT_TYPES set:
GOTO_EVENT_TYPES = {
    lsp_types.DefinitionResponse,
    lsp_types.ReferencesResponse,
    lsp_types.ImplementationResponse,
    lsp_types.TypeDefinitionResponse,
    lsp_types.DeclarationResponse,
}

# 6. Update ServerConfig.__init__ to handle InitializeResponse:
def __init__(self, initialized, langids, lang_str):
    # Extract capabilities from InitializeResponse
    if hasattr(initialized, 'result'):
        capabilities = initialized.result.capabilities
    else:
        capabilities = initialized.capabilities
    # ... rest of the code
