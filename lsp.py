import os
import sys
import time

_plugin_dir = os.path.dirname(os.path.realpath(__file__))

if os.name=='nt': # on Unix-like, user needs installation of all modules into OS Python
    sys.path.insert(0, os.path.join(_plugin_dir, 'lsp_modules'))

from cudatext import *
from cudax_lib import _json_loads

from cudax_lib import get_translation
_ = get_translation(__file__)  # I18N

from . import dlg
from .dlg import Hint, SignaturesDialog
from .util import (
        lex2langid,
        update_lexmap,
        langid2lex,
        ed_uri,
        is_ed_visible,
        command, # hides hint
        get_visible_eds,
        collapse_path,

        ValidationError,
    )

# imported on access
#from .language import Language
#from .book import DocBook

from .language import CompletionMan, DiagnosticsMan, Language

LOG = False
LOG_NAME = 'LSP'
IS_WIN = os.name=='nt'
SERVER_RESPONSE_DIALOG_LEN = 80

# Project Manager's tree-node events (APPSTATE 48/49, 'proj_mgr' core
# patch): fired via app_proc(APP_PROC_PROJECT_NODE_ADD/_DEL) after its
# global_project_info was refreshed. Official CudaText builds don't
# export them yet - fall back to the raw numbers, so on_state simply
# never sees these states there (the on_tab_change re-check covers it)
import cudatext as _ct
APPSTATE_PROJECT_NODE_ADD = getattr(_ct, 'APPSTATE_PROJECT_NODE_ADD', 48)
APPSTATE_PROJECT_NODE_DEL = getattr(_ct, 'APPSTATE_PROJECT_NODE_DEL', 49)

# considering all 'lsp_*.json' - server configs
dir_settings    = app_path(APP_DIR_SETTINGS)
fn_config       = os.path.join(dir_settings, 'cuda_lsp.json')
fn_opt_descr    = os.path.join(_plugin_dir,  'readme', 'options_description.md')
fn_state        = os.path.join(dir_settings, 'cuda_lsp_state.json')

LINT_STYLE_MAP = {0:1, 1:4, 2: 2, 3:6}

STATE = {} # like log-panel's filter state

opt_spy_file = ''

opt_enable_mouse_hover = True
opt_root_dir_source = [0]
opt_send_change_on_request = False
opt_hover_max_lines = 10
opt_hover_additional_commands = [
    "Definition",
    "References",
    "Implementation",
    "Declaration",
    "Type definition",
]
opt_hover_with_ctrl = True
opt_cudatext_in_py_env = False
opt_lint_type = 'dc'
opt_lint_underline_style = 2  # solid 0, dotted 1, dashes 2, wave 3
opt_enable_code_tree = False
opt_tree_types_show = ''

# to close - change lexer (then back)
opt_manual_didopen = None # debug help "manual_didopen"
opt_auto_append_bracket = True
opt_hard_filter = False
opt_use_cache = True
opt_servers_shutdown_max_time = 2 # seconds
SERVERS_SHUTDOWN_CHECK_PERIOD = 0.1 # seconds

opt_enable_semantic_tokens = False
opt_semantic_max_lines = 10000
opt_semantic_colors_light = '#BC7676,#15AD00,#BF00AF,#BF00AF,,,#FF2436,,#d79e3f,#00B3B7'
opt_semantic_colors_dark = '#E38F8F,#0f0,#EB67E0,#EB67E0,,,#FF2436,,#ffe226,#0ff'

opt_disabled_contexts = 'cs'
opt_complete_from_text = False
opt_use_markers=True
opt_diagnostics_in_a_corner = False

api_ver = app_api_version()

"""
file:///install.inf
file:///book.py
file:///language.py
file:///util.py

https://microsoft.github.io/language-server-protocol/specifications/specification-current/#exit

#TODO
* print server stderr to Output panel
* test hover with OS scaled
* handle lite lexers
* test older python

* ! kill css server properly

#TODOC
* server root uri
* config tcp port
* commands + options; +hover-Control

#TODO later (random order)
* add status messages
* hover dialog - add 'hide' to dialog just in case
* remember active_ed,caret - dont show dialog-respose if changed (not only for completion)
* check if need snippet support in completion
* find server supporting 'prepareCallHierarchy' stuff
* 'PartialResultParams'
* 'WorkDoneProgressParams'
* urls in hover dialog
* generic completion result cache?
* sidebar panel - tree (server/doc), config, shutdown server, manual file opening
* markdown Editor display
* () on functions completion?
* 'hover' dialog -- add  context menu - apply any lexer
* separate log panel for server's `LogMessage`
* unregistering capabilities


#TODO features
+ Document:
    codeAction
    codeLens
    rename
    onTypeFormatting
    selectionRange
    callHierarch
    moniker
    --documentHighlight
    --documentLink
    --colorProvider
    --foldingRange
    --linkedEditingRange
    --semanticTokens

+ Workspace:
    applyEdit
    symbol
    configuration
    [file operations]

+ Window:
    workDoneProgress
    showMessage
    showDocument

+ General:
    regularExpressions
    markdown

"""

_projman_failed = False

def _projman():
    """ Module handle of the built-in Project Manager plugin, or None when it
    is not installed (then all project/workspace-folder support is off).
    """
    global _projman_failed
    if _projman_failed:
        return None
    try:
        import cuda_project_man
        return cuda_project_man
    except ImportError:
        _projman_failed = True
        print(f'NOTE: {LOG_NAME}: built-in Project Manager plugin not found,'
              ' "work_dir" is the only workspace root source')
        return None


def get_workspace_roots(ed_file=None):
    """ Workspace folders of the opened CudaText project (see readme:
    "work_dir" / Project Manager).

    Returns (root, folders):
      root    - single dir for rootUri and the server process cwd: the project
                folder CONTAINING ed_file (deepest match wins), else the first
                value of opt_root_dir_source that exists (0 - dir of the
                '.cuda-proj' file, 1 - first folder node, 2 - main-file dir).
      folders - ALL top-level folder nodes of the project (order kept, dupes
                and non-dirs dropped) - they all go to the server as LSP
                workspaceFolders, so a project may combine folders from
                different places on disk.
    Both are empty when no project is opened.
    """
    pm = _projman()
    if pm is None:
        return None, []

    info = pm.global_project_info
    if not info.get('filename'):    # no project opened
        return None, []

    folders = []
    for node in info.get('nodes') or []:
        if os.path.isdir(node) and node not in folders:
            folders.append(node)

    # the folder holding the file (which starts/uses the server) is the best
    # single root: servers which only read rootUri (OmniSharp) then discover
    # the project/solution this file belongs to
    root = None
    if ed_file:
        norm_file = os.path.normcase(os.path.normpath(ed_file))
        best_len = -1
        for folder in folders:
            norm_folder = os.path.normcase(os.path.normpath(folder)) + os.sep
            if norm_file.startswith(norm_folder) and len(folder) > best_len:
                root = folder
                best_len = len(folder)

    if root is None:
        for optval in opt_root_dir_source:
            if optval == 0:    # project file dir
                path = pm.project_variables()["ProjDir"]
            elif optval == 1:  # first folder node
                path = folders[0] if folders else None
            else:              # project's main-file dir
                path = info.get('mainfile')
                if path:
                    path = os.path.dirname(path)

            if path and os.path.isdir(path):
                root = path
                break

    if root and root not in folders:
        # rootUri must be one of workspaceFolders (like other LSP clients)
        folders.insert(0, root)
    return root, folders


def _same_dirs(dirs1, dirs2):
    def _norm(dirs):
        return {os.path.normcase(os.path.normpath(d)) for d in dirs}
    return _norm(dirs1 or []) == _norm(dirs2 or [])


def get_project_lsp_cfg_path():
    pm = _projman()
    if pm is None:
        return None

    fn_proj = pm.global_project_info.get('filename')
    if fn_proj:
        return os.path.splitext(fn_proj)[0] + '.cuda-proj-lsp'

def get_project_lsp_cfg():
    fn_cfg = get_project_lsp_cfg_path()
    if fn_cfg  and  os.path.exists(fn_cfg):
        with open(fn_cfg, 'r', encoding='utf-8') as f:
            return _json_loads(f.read())


def get_server_cfg_fns():
    if os.path.exists(dir_settings):
        _fns = os.listdir(dir_settings)
        _lsp_fns = [name for name in _fns  if name.startswith('lsp_')
                                                and name.lower().endswith('.json')]
        return _lsp_fns

class Command:

    def __init__(self):
        self.is_loading_sesh = False # is this broken when on_state~ is lazy?
        
        # editors not on_open'ed durisg sesh-load;  on_open visibles when sesh loaded
        self._sesh_eds = []
        self._langs = {} # langid -> Language
        self._book = None

        self._load_config()

        # hover dlg calls these with "caret" named param, caret is tuple(caretx, carety)
        self._hint_cmds = {
            _('Definition'):        self.call_definition,
            _('References'):        self.call_references,
            _('Implementation'):    self.call_implementation,
            _('Declaration'):       self.call_declaration,
            _('Type definition'):   self.call_typedef,
        }
        ### filter commands by option: opt_hover_additional_commands
        # to lower case for case-insensitive comparison
        _user_cmds = {name.lower() for name in opt_hover_additional_commands}
        for name in self._hint_cmds:
            if name.lower() not in _user_cmds: # if removed by user
                self._hint_cmds[name] = None # None values are dimmed in hover

        ### dbg
        if opt_manual_didopen:
            # first call only starts server, subsequent - send didOpen
            app_proc(PROC_SET_SUBCOMMANDS, 'cuda_lsp;force_didopen;LSP-Open-Doc\t')

    @property
    def book(self):
        if self._book is None:
            from .book import DocBook

            self._book = DocBook()
        return self._book

    def config(self):
        self._save_config()
        file_open((fn_config, fn_opt_descr))
        se = Editor(ed.get_prop(PROP_HANDLE_SECONDARY))
        se.set_prop(PROP_WRAP, True)

        # underline demo
        underline = {'"solid"':  1, '"dotted"': 4, '"dashes"': 2, '"wave"':   6, }
        _colors = app_proc(PROC_THEME_UI_DICT_GET, '')
        err_col = _colors['EdMicromapSpell']['color']
        for text,style in underline.items():
            res = se.action(EDACTION_FIND_ONE, text, "c")
            if res:
                se.attr(MARKERS_ADD, x=res[0], y=res[1], len=res[2]-res[0],
                            color_border=err_col, border_down=style)

    def config_server(self):
        fn_cfg = get_project_lsp_cfg_path()
        if fn_cfg:
            if not os.path.exists(fn_cfg):
                with open(fn_cfg, 'w', encoding='utf-8') as f:
                    f.write('{\n    \n}\n')
            file_open(fn_cfg)
            ed.set_prop(PROP_LEXER_FILE, 'JSON')
        else:
            msg_status(_('No project opened'))

    def edit_server_cfg(self):
        _lsp_fns = get_server_cfg_fns() # in `dir_settings`
        if _lsp_fns:
            _lsp_fns.sort()
            ind = dlg_menu(DMENU_LIST, _lsp_fns, caption=_('Choose config to edit'))
            if ind is not None:
                file_open(os.path.join(dir_settings, _lsp_fns[ind]))
        else:
            msg_status(_('No server configs exist'))

    #NOTE also gets called for unsaved from session
    def on_open(self, ed_self):
        if not self.is_loading_sesh:
            self._do_on_open(ed_self)
        else: # sesh is loading - delay
            self._sesh_eds.append(ed_self)

    def _do_on_open(self, ed_self: Editor):
        """ Creates 'doc' only if 'ed' is visible
                (to not didOpen all opened files at start)
            * on new capability - only visible 'ed's are 'didOpen'-ed
            * ? tab change
            (updates existing doc when needed)
        """
        if opt_manual_didopen  or  not is_ed_visible(ed_self):
            return

        doc = self.book.get_doc(ed_self) # get existing

        lex = ed_self.get_prop(PROP_LEXER_FILE)
        langid = lex2langid(lex)

        if lex is None  or  langid is None:
            if doc:
                doc.update()
            return


        try:
            lang = self._get_lang(ed_self, langid) # uses dynamic server registrationed
        except ValidationError as ex:
            print(ex)
            return

        pass;       LOG and print(f'on_open: lex, langid, filename:{lex, langid, ed_self.get_filename()} =>> lang:{lang.name if lang else "none"}')

        # if have server for this lexer
        if lang:
            if not doc:
                self.book.new_doc(ed_self)
                doc = self.book.get_doc(ed_self)

            if lang.on_open(doc): # doc's .lang is set only when was actually didOpen-ed
                doc.update(lang=lang)

                if lang.tree_enabled:
                    lang.update_tree(doc)
                if opt_enable_semantic_tokens and ed_self.get_line_count() <= opt_semantic_max_lines:
                    lang.request_semantic_tokens(doc)

    def on_focus(self, ed_self):
        doc = self.book.get_doc(ed_self)
        if doc and doc.lang and doc.lang.tree_enabled:
            doc.lang.update_tree(doc)

    def on_save(self, ed_self):
        """ handles changed uri for LSP doc
            * if was unsaved with LSP lexer: will have a LSP 'doc' -- ok
            * lexer change via save is handles in .on_lexer()
        """
        doc = self.book.get_doc(ed_self)
        if doc:     # if owning LSP doc
            newuri = ed_uri(ed_self)
            if doc.uri != newuri:   # if uri changed (new file) - close old, open new
                pass;       LOG and print(f'* uri change: {doc.uri} => {newuri}')
                self.on_close(ed_self)
                self.on_open(ed_self)
            elif doc.lang: # just saved to same file
                doc.lang.on_save(doc)
        # handle lexer|ext change by saving (can't know if something changed)
        else:
            self.on_open(ed_self)

    def on_save_pre(self, ed_self):
        doc = self.book.get_doc(ed_self)
        if doc and doc.lang:
            doc.lang.on_save_pre(doc)

    def on_close(self, ed_self):
        doc = self.book.get_doc(ed_self)
        if doc:
            pass;       LOG and print('on_close: '+doc.uri)
            if doc.lang:
                doc.lang.on_close(doc)
            self.book.on_close(ed_self) # deletes doc

    #NOTE: also gets called when document first activated
    def on_lexer(self, ed_self):
        doc = self.book.get_doc(ed_self)
        if doc:
            newlex = ed_self.get_prop(PROP_LEXER_FILE)
            oldlex = doc.lex
            pass;       LOG and print(f'lex changed: {ed_uri(ed_self)}:: {oldlex} => {newlex}')
            if oldlex != newlex:
                if doc.lang:
                    doc.lang.on_close(doc) # sends on_close to server
                doc.update()
                self.on_open(ed_self) # changes/removes lang server of doc
        else:    # create doc if new lexer is supported by lsp server
            self.on_open(ed_self)

    def on_change_slow(self, ed_self):
        
        doc = self.book.get_doc(ed_self)
        if doc and doc.lang:
            # tree update sends changes by itself
            if doc.lang.tree_enabled and doc.lang.update_tree(doc):
                return
            if not opt_send_change_on_request:
                doc.lang.send_changes(doc)
        
        if opt_enable_semantic_tokens and ed_self.get_line_count() <= opt_semantic_max_lines:
            doc = self.book.get_doc(ed_self)
            if doc and doc.lang:
                doc.lang.request_semantic_tokens(doc)


    @command
    def on_complete(self, ed_self):
        doc = self.book.get_doc(ed_self)
        if doc and doc.lang:
            return doc.lang.on_complete(doc)

    def on_snippet(self, ed_self, snippet_id, snippet_text):
        """ for Editor.complete_alt()
        """
        for lang in self._langs.values():
            if lang.on_snippet(ed_self, snippet_id, snippet_text):
                break

    def on_mouse_stop(self, ed_self, x, y):
        if not opt_enable_mouse_hover:      return
        # require Control pressed
        if opt_hover_with_ctrl and (app_proc(PROC_GET_KEYSTATE, '') != 'c'):
            return
        if Hint.is_under_cursor()  or  Hint.is_visible():      return

        doc = self.book.get_doc(ed_self)
        #if ed_self.get_prop(PROP_FOCUSED):
        caret = ed_self.convert(CONVERT_PIXELS_TO_CARET, x, y, "")
        self.call_hover(ed_self, caret)

    #@command
    def on_func_hint(self, ed_self):
        doc = self.book.get_doc(ed_self)
        if doc  and  doc.lang  and  ed_self.get_prop(PROP_FOCUSED):
            doc.lang.request_sighelp(doc)
            return True
            
    def on_caret_slow(self, ed_self):
        if SignaturesDialog.is_visible():
            self.on_func_hint(ed_self)
        
        if opt_diagnostics_in_a_corner and api_ver >= '1.0.452':
            doc = self.book.get_doc(ed_self)
            if doc  and  doc.lang:
                doc.lang.diagnostics_man.on_caret_slow(ed_self)
            
    def on_scroll(self, ed_self):
        if SignaturesDialog.is_visible():
            SignaturesDialog.hide()

    def on_goto_def(self, ed_self):
        self.call_definition(ed_self)
        return True # supress Cud's statusbar error "no goto-defition plugins"

    def on_app_activate(self, ed_self):
        dlg.app_active = True

    def on_app_deactivate(self, ed_self):
        dlg.app_active = False

        timer_proc(TIMER_STOP, Hint.hide_check_timer, 250, tag='')
        Hint.hide()

        SignaturesDialog.hide()
        
    def on_tab_change(self, ed_self):
        if SignaturesDialog.is_visible():
            SignaturesDialog.hide()

        # FOLDER-CHANGE FALLBACK for CudaText builds without the
        # APPSTATE_PROJECT_NODE_ADD/_DEL events (official releases):
        # re-check the folder list here. On patched builds this is a
        # no-op (the event already applied the change; the diff below
        # finds nothing new). Cheap: one dict read + compare, and a
        # no-op without an opened project
        self._on_project_dirs_change()

        doc = self.book.get_doc(ed_self)
        if doc  and  doc.lang:
            doc.lang.on_ed_shown(doc)
        else: # look for matching server if not already opened
            self.on_open(ed_self)


    def on_lang_inited(self, name):
        """ when server initialized properly (handshake done) - send 'didOpen'
                for documents of this server
                (for visible editors, others - from on_tab_change())
            * if couldn't find - got shutdown before initted
        """
        for lang in self._langs.values():
            if lang.name == name:
                for doc in self.book.get_docs():
                    if doc.lang is None  and  is_ed_visible(doc.ed):
                        self.on_open(doc.ed)
                break # found initted lang

    def on_state(self, ed_self, state):
        if state == APPSTATE_SESSION_LOAD_BEGIN: # started
            self.is_loading_sesh = True

        elif state in [APPSTATE_SESSION_LOAD_FAIL, APPSTATE_SESSION_LOAD]: # ended
            self.is_loading_sesh = False
            # on_open for delayed
            eds = self._sesh_eds[:]
            self._sesh_eds.clear()
            for editor in eds:
                self._do_on_open(editor)

        elif state == APPSTATE_PROJECT:
            for name,lang in list(self._langs.items()):
                lang.plog.clear()

            self._on_project_dirs_change()

        elif state in (APPSTATE_PROJECT_NODE_ADD, APPSTATE_PROJECT_NODE_DEL):
            # folder/file node(s) added to or removed from the open
            # project's tree (Project Manager fires this AFTER refreshing
            # its global_project_info, so the re-read below is final;
            # a node moved on disk = DEL then ADD with the list already
            # updated - the first event applies the change, the second
            # diffs to a no-op)
            self._on_project_dirs_change()

        elif state == APPSTATE_THEME_UI:
            from .dlg import PanelLog

            PanelLog.on_theme_change()
            SignaturesDialog.on_theme_change()
            
            for edt in get_visible_eds():
                if opt_enable_semantic_tokens and edt.get_line_count() <= opt_semantic_max_lines:
                    doc = self.book.get_doc(edt)
                    if doc and doc.lang:
                        doc.lang.request_semantic_tokens(doc)

    def _on_project_dirs_change(self):
        """ React to the CudaText project (or its folder list) changing.
        Every server's folder set is compared against the fresh project
        folders (or, with no project open, the server config's 'work_dir'):
        servers subscribed to folder-change notifications get a live
        'workspace/didChangeWorkspaceFolders'; the others are restarted -
        their rootUri was fixed at 'initialize' (e.g. OmniSharp reads
        nothing else), and the restart re-picks the root for the file being
        opened.

        Single-root servers (OmniSharp, 'single_root': true or detected
        from serverInfo) are reconciled instead: one instance per project
        folder - VS Code's method for multi-root workspaces. Instances for
        REMOVED folders are shut down, instances for ADDED folders are
        created lazily on the next file open in that folder (starting a
        process per folder nobody works in would be waste); the 'misc'
        fallback instance (files under no project folder) is also
        reconciled when it exists.
        """
        if not self._langs:
            return

        root, folders = get_workspace_roots()

        # single-root instances: shut down the ones bound to folders which
        # left the project; the ones for added folders are created lazily
        # on the next _get_lang in that folder (no eager process spawn)
        norm_folders = {os.path.normcase(os.path.normpath(d)) for d in folders}
        for name, lang in list(self._langs.items()):
            if not isinstance(name, str) or '//' not in name:
                continue
            if not getattr(lang, 'single_root', False):
                continue    # e.g. an OmniSharp instance before detection
            folder = getattr(lang, '_root_folder', None)
            if folder is None:
                continue
            if os.path.normcase(os.path.normpath(folder)) not in norm_folders:
                print(f'{LOG_NAME}: workspace folder removed ({lang.lang_str}): '
                      f'{collapse_path(folder)}; shutting down its server instance')
                self._shutdown_server_instance(name)

        # folder sets of the remaining (multi-root) instances
        for name, lang in list(self._langs.items()):
            if getattr(lang, 'single_root', False):
                # a single-root instance which is NOT folder-bound (the
                # 'misc' fallback, work_dir-only configs, no project):
                # treat it like any other - restart unless the folder set
                # is unchanged
                if getattr(lang, '_root_folder', None) is not None:
                    continue    # folder-bound: handled above
            if folders:
                new_dirs = folders
            else:
                # no project opened: keep the server config's 'work_dir'
                wd = lang._cfg.get('work_dir')
                new_dirs = [wd] if wd else []

            if _same_dirs(lang._workspace_dirs, new_dirs):
                continue

            collapsed = ', '.join(collapse_path(d) for d in new_dirs) or _('(none)')
            print(f'{LOG_NAME}: workspace folders changed ({lang.lang_str}): '
                  f'{collapsed}; notifying server...')

            handled = lang.on_workspace_change(
                root or (new_dirs[0] if new_dirs else None), new_dirs)
            if not handled:
                self.shutdown_server(name=name)

    def _shutdown_server_instance(self, name):
        """ Shut down one _langs entry (name key, e.g. 'omnisharp//F:\\src')
        without the interactive dialog of shutdown_server(): same cleanup
        (docs detached, sibling langid keys pointing at the same instance
        removed). Used by the single-root reconcile when a folder leaves
        the project. """
        lang = self._langs.pop(name, None)
        if lang is None:
            return

        # remove referencees to Language object
        for doc in self.book.get_docs():
            if doc.lang == lang:
                doc.update(lang=None)

        # server can have multiple langids - remove all
        lang_ids = [langid for langid, lang_ in self._langs.items()
                    if lang_ == lang]
        for langid in lang_ids:
            del self._langs[langid]

        lang.shutdown()

    def on_key(self, ed_self, key, state):
        # VK_ESCAPE==27
        if key==27 and 'c' not in state and 's' not in state and 'a' not in state:
            if Hint.is_visible():
                Hint.hide()
                return False
            if SignaturesDialog.is_visible():
                SignaturesDialog.hide()
                return False
        elif key in (38,40) and 'c' not in state and 's' not in state and 'a' not in state:
            if SignaturesDialog.is_visible():
                SignaturesDialog.hide()

    def on_exit(self, *args, **vargs):
        #### save state before exiting
        state_changed = False
        # _langs holds several keys per instance (langids + name/instance
        # key) - save every Language exactly once
        seen = set()
        for lang in self._langs.values():
            if id(lang) in seen:
                continue
            seen.add(id(lang))
            key,state = lang.get_state_pair()
            if state:
                STATE[key] = state
            elif STATE.pop(key, None):
                state_changed = True
        ## if something was removed or state not empty - save
        if state_changed or STATE:
            # if started lang server - json will be imported;  otherwise no need to save server state
            try:
                js = json.dumps(STATE, indent=2)
                with open(fn_state, 'w', encoding='utf-8') as f:
                    f.write(js)
            except NameError: # for missing json
                pass


        # start servers shutdown (several _langs keys can share one instance)
        seen = set()
        for lang in self._langs.values():
            if id(lang) in seen:
                continue
            seen.add(id(lang))
            lang.shutdown()

        _start = time.time()
        while self._langs:
            time.sleep(SERVERS_SHUTDOWN_CHECK_PERIOD)
            for key,lang in list(self._langs.items()):
                lang.process_queues()
                if lang.is_client_exited():
                    del self._langs[key]

            if time.time() - _start > opt_servers_shutdown_max_time:
                break

        if not IS_WIN:
            try:
                os.waitpid(-1, os.WNOHANG) # -1 -- any child
            except ChildProcessError:
                pass


    def _get_lang(self, ed_self, langid):
        """ Find or create the Language (server instance) for an editor.

        _langs maps server name -> Language; a server registered for
        several langids appears under each of them (all values pointing to
        one instance). A 'single_root' server (OmniSharp: reads rootUri
        only, no multi-root - it even advertises workspaceFolders support
        without implementing the change notification) gets ONE INSTANCE
        PER workspace folder, name keys 'name' and 'name//folder'
        (VS Code's method for multi-root workspaces); the file's folder
        picks the instance, files under no known folder go to the
        instance of the file's folder when one exists (multi-instance
        fallback), else a fresh instance is created with the best root.
        """
        # to not import json from on_exit
        global json
        import json

        # existing instances which match this document
        matches = [lang for lang in self._langs.values()
                   if lang.is_ed_matches(ed_self, langid)]
        if matches:
            lang = self._match_lang(matches, ed_self, langid)
            pass;   LOG and print(f'* matched existing lang: {ed_self, langid} -- {lang.name}')
            return lang

        # no instance matches: create one from the server configs
        for cfg in servers_cfgs:
            if langid not in cfg.get('langids', []):
                continue

            single_root = self._is_single_root_cfg(cfg)

            # project folders (all of them) go as LSP workspaceFolders;
            # the root (rootUri/cwd) is the folder of the opened file's
            # project when set, else the server config's 'work_dir'
            proj_root, proj_dirs = get_workspace_roots(ed_self.get_filename())

            if single_root:
                # one instance per folder: pick/create the instance of the
                # file's folder
                lang = self._get_single_root_lang(cfg, langid, ed_self,
                                                  proj_root, proj_dirs)
                if lang is not None:
                    return lang
                # file under NO project folder: fall through and create the
                # 'misc' instance below (single instance over all folders,
                # like the pre-multiroot behaviour - the file gets
                # syntax-only diagnostics there instead of no server at all)

            # multi-root server - or the 'misc' instance of a single-root
            # server: single instance, all folders
            from copy import deepcopy
            cfg = deepcopy(cfg)
            # update server 'settings' with project's lsp server settings
            proj_lsp_cfg = get_project_lsp_cfg()
            cfg.setdefault('settings', {}).update(proj_lsp_cfg or {})
            if single_root:
                # keep the flag: the misc instance must also be restarted
                # (not notified) when the folder set changes - a single_root
                # server's capability advertisement cannot be trusted
                cfg['single_root'] = True
            if proj_dirs:
                cfg['work_dir'] = proj_root or proj_dirs[0]
                cfg['workspace_dirs'] = proj_dirs
            lang = self._make_lang(cfg)
            if lang is not None:
                return lang
            continue    # config invalid - try next config

        # nothing created/matched: langid-keyed entry (a server created
        # moments ago, still initializing - is_ed_matches is False until
        # its capabilities arrive; on_lang_inited re-opens the docs then)
        return self._langs.get(langid)

    def _lookup_lang(self, ed_self, langid):
        """ Final lookup after creations: the instance which matches the
        document, preferring the file's folder among single-root instances.
        """
        matches = [lang for lang in self._langs.values()
                   if lang.is_ed_matches(ed_self, langid)]
        if not matches:
            return self._langs.get(langid)
        return self._match_lang(matches, ed_self, langid)

    def _make_lang(self, cfg):
        """ Create + register one Language from a config (deep-copied by the
        caller). Registers under 'name' or, for folder-bound instances,
        'name//folder'. Returns the Language, or None on ValidationError
        (the config is then dropped from servers_cfgs to not nag on every
        on_open).
        """
        from .language import Language

        root_folder = cfg.get('_root_folder')
        key = cfg['name'] + ('//' + root_folder if root_folder else '')
        try:
            lang = Language(cfg,
                    cmds=self._hint_cmds,
                    lintstr=opt_lint_type,
                    underline_style=LINT_STYLE_MAP[opt_lint_underline_style],
                    state=STATE.get(key) or STATE.get(cfg.get('name'))
            )
        except ValidationError:
            if cfg in servers_cfgs:
                servers_cfgs.remove(cfg) # dont nag on every on_open
            return None

        # register server to all its supported langids
        for server_langid in lang.langids:
            self._langs.setdefault(server_langid, lang)
        # name key (instance key when folder-bound)
        self._langs[key] = lang
        return lang

    def _match_lang(self, matches, ed_self, langid):
        """ Pick the best instance among matches for a document: the one
        bound to the folder containing the file; when the file is under no
        known folder, prefer a non-folder-bound ('misc'/multi-root)
        instance, else any (first). """
        fn = ed_self.get_filename()
        if not fn:
            return matches[0]
        norm = os.path.normcase(os.path.normpath(fn))
        best = None
        misc = None
        for lang in matches:
            folder = getattr(lang, '_root_folder', None)
            if folder is None:
                misc = misc or lang
                continue
            if norm.startswith(os.path.normcase(os.path.normpath(folder)) + os.sep):
                best = lang  # keep the LAST/deepest? all are siblings - first wins
                break
        return best or misc or matches[0]

    def _is_single_root_cfg(self, cfg):
        """ Server config explicitly or heuristically single-root (per-folder
        instances). Explicit: 'single_root': true. Heuristic (OmniSharp -
        the KNOWN case): any server command token mentioning 'omnisharp'.
        The final authority is the server's own serverInfo after
        'initialize' (language._detect_single_root). """
        if cfg.get('single_root'):
            return True
        from .language import CMD_OS_KEY
        cmd = cfg.get(CMD_OS_KEY) or []
        if isinstance(cmd, str):
            cmd = [cmd]
        return any('omnisharp' in str(tok).lower() for tok in cmd)

    def _get_single_root_lang(self, cfg, langid, ed_self, proj_root, proj_dirs):
        """ Instance of a single-root server for the file's folder: reuse
        the existing one, or create it (name key 'name//folder'). Returns
        None when the file is under NO project folder - the caller then
        falls back to the 'misc' instance (single instance over all
        folders: the file gets syntax-only diagnostics there, like in the
        pre-multiroot plugin, instead of no server at all). """
        fn = ed_self.get_filename()
        folder = None
        if fn:
            norm = os.path.normcase(os.path.normpath(fn))
            for d in proj_dirs:
                if norm.startswith(os.path.normcase(os.path.normpath(d)) + os.sep):
                    folder = d
                    break

        if folder is None:
            # under no project folder: no per-folder instance applies
            return None

        key = cfg['name'] + '//' + folder
        lang = self._langs.get(key)
        if lang is not None:
            # exists for this folder: reuse it even while it is still
            # initializing (is_ed_matches is False until its capabilities
            # arrive - a second instance for the same folder would be wrong)
            return lang

        from copy import deepcopy
        new_cfg = deepcopy(cfg)
        proj_lsp_cfg = get_project_lsp_cfg()
        new_cfg.setdefault('settings', {}).update(proj_lsp_cfg or {})
        new_cfg['single_root'] = True
        new_cfg['work_dir'] = folder
        new_cfg['workspace_dirs'] = [folder]
        new_cfg['_root_folder'] = folder
        # drop langids so only this file's langid registers (avoids
        # cross-instance didOpen of docs of other langids? no - keep them:
        # simpler, the doc matching is per-document anyway)
        return self._make_lang(new_cfg)

    @command
    def call_hover(self, ed_self=None, caret=None):
        """ caret - if present - used instead of actual caret (for hovered stuff)
        """
        ed_self = ed_self or ed
        doc = self.book.get_doc(ed_self)
        if doc and doc.lang:
            doc.lang.on_hover(doc, caret)

    @command
    def call_definition(self, ed_self=None, caret=None):
        ed_self = ed_self or ed
        doc = self.book.get_doc(ed_self)
        if doc and doc.lang:
            doc.lang.request_definition_loc(doc, caret)

    @command
    def call_references(self, caret=None):
        doc = self.book.get_doc(ed)
        if doc and doc.lang:
            doc.lang.request_references_loc(doc, caret)

    @command
    def call_implementation(self, caret=None):
        doc = self.book.get_doc(ed)
        if doc and doc.lang:
            doc.lang.request_implementation_loc(doc, caret)

    @command
    def call_declaration(self, caret=None):
        doc = self.book.get_doc(ed)
        if doc and doc.lang:
            doc.lang.request_declaration_loc(doc, caret)

    @command
    def call_typedef(self, caret=None):
        doc = self.book.get_doc(ed)
        if doc and doc.lang:
            doc.lang.request_typedef_loc(doc, caret)


    @command
    def call_format_doc(self):
        doc = self.book.get_doc(ed)
        if doc and doc.lang:
            doc.lang.request_format_doc(doc)

    @command
    def call_format_sel(self):
        doc = self.book.get_doc(ed)
        if doc and doc.lang:
            doc.lang.request_format_sel(doc)


    def dbg_call_hierarchy_in(self):
        doc = self.book.get_doc(ed)
        if doc and doc.lang:
            doc.lang.call_hierarchy_in(doc)


    def dbg_workspace_symbols(self):
        doc = self.book.get_doc(ed)
        if doc and doc.lang:
            doc.lang.workspace_symbol(doc)


    def dbg_show_msg(self, show_bytes=False):
        lex = ed.get_prop(PROP_LEXER_FILE)
        langid = lex2langid(lex)
        lang = self._match_lang(
            [l for l in self._langs.values() if l.is_ed_matches(ed, langid)],
            ed, langid) if langid else None
        if lang is None:
            msg_status(_('No messages for server of current document'))
            return

        names = ['msg|' + str(msg)[:SERVER_RESPONSE_DIALOG_LEN]+'...\t'+type(msg).__name__
                        for msg in lang._dbg_msgs]
        ind = dlg_menu(DMENU_LIST, names, w = 900)

        if ind is not None:
            max_output_width = max(80, ed.get_prop(PROP_SCROLL_HORZ_INFO)['page'])
            file_open('')
            import pprint
            from .sansio_lsp_client import event_asdict
            try:
                ed.set_text_all(pprint.pformat(event_asdict(lang._dbg_msgs[ind]), width=max_output_width))
            except Exception:
                j = {k:str(v) for k,v in event_asdict(lang._dbg_msgs[ind]).items()}
                ed.set_text_all(pprint.pformat(j, width=max_output_width))
            ed.set_prop(PROP_LEXER_FILE, 'Python')

    def dbg_show_docs(self):
        items = [f'{doc.lang}: {doc}' for doc in self.book.get_docs()]
        dlg_menu(DMENU_LIST, items, caption=_('LSP Docs'))

    @command
    # for project folder change
    def shutdown_server(self, name=None):
        # choice dlg: instance keys ('name' / 'name//folder'), langid keys
        # shown as the instance they point to
        if name is None:
            names = []
            for key, lang in self._langs.items():
                shown = key if '//' in key or key == lang.name else f'{key} ({lang.name})'
                if shown not in names:
                    names.append(shown)
            names.sort()
            ind = dlg_menu(DMENU_LIST, names, caption=_('Shutdown server'))
            if ind is not None:
                name = names[ind]

        # shutting down and clearing remains
        if name is not None:
            # menu may show 'langid (name)' - resolve to the instance key
            target = None
            for key, lang in self._langs.items():
                shown = key if '//' in key or key == lang.name else f'{key} ({lang.name})'
                if shown == name:
                    target = key
                    break
            name = target if target is not None else name

        if name is not None  and  name in self._langs:
            lang = self._langs.pop(name)
            lang.shutdown()

            # remove referencees to Language object
            for doc in self.book.get_docs():
                if doc.lang == lang:
                    doc.update(lang=None)

            # server can have multiple langids - remove all
            lang_ids = [langid for langid,lang_ in self._langs.items()  if lang_ == lang]
            for langid in lang_ids:
                del self._langs[langid]

    def shutdown_all_servers(self):
        for name in list(self._langs):
            self.shutdown_server(name=name)

    def force_didopen(self, *args, **vargs):
        ed_self = Editor(ed.get_prop(PROP_HANDLE_SELF))

        _langid = lex2langid(ed_self.get_prop(PROP_LEXER_FILE))
        lang = self._get_lang(ed_self, _langid) # uses dynamic server registrationed
        pass;       LOG and print(f'manual didopen: lex, langid, filename:{_langid, ed_self.get_filename()} =>> lang:{lang.name if lang else "none"}')

        self.book.new_doc(ed_self)
        doc = self.book.get_doc(ed_self)
        lang.on_open(doc)
        doc.update(lang=lang)


    def _load_config(self):
        global opt_enable_mouse_hover
        global opt_root_dir_source
        global opt_manual_didopen
        global opt_send_change_on_request
        global opt_hover_max_lines
        global opt_hover_additional_commands
        global opt_hover_with_ctrl
        global opt_cudatext_in_py_env
        global opt_lint_type
        global opt_lint_underline_style
        global opt_enable_code_tree
        global opt_tree_types_show
        global opt_auto_append_bracket
        global opt_hard_filter
        global opt_use_cache
        global opt_servers_shutdown_max_time
        global opt_enable_semantic_tokens
        global opt_semantic_max_lines
        global opt_semantic_colors_light
        global opt_semantic_colors_dark
        global opt_disabled_contexts
        global opt_use_markers
        global opt_complete_from_text
        global opt_diagnostics_in_a_corner
        global opt_spy_file

        # general cfg
        if os.path.exists(fn_config):
            with open(fn_config, 'r', encoding='utf-8') as f:
                js = f.read()
            j = _json_loads(js)
            opt_enable_mouse_hover = j.get('enable_mouse_hover', opt_enable_mouse_hover)

            _opt_root_dir_source = j.get('root_dir_source', opt_root_dir_source)
            if not isinstance(_opt_root_dir_source, list):  # convert item to list
                _opt_root_dir_source = [_opt_root_dir_source]
            if all(val in {0, 1, 2} for val in _opt_root_dir_source):
                opt_root_dir_source = _opt_root_dir_source
            else:
                print(f'NOTE: {LOG_NAME}: invalid value of option "root_dir_source"'
                        +f' in {fn_config}, accepted values: 0, 1, 2')

            opt_send_change_on_request = j.get('send_change_on_request', opt_send_change_on_request)
            opt_hover_max_lines = j.get('hover_dlg_max_lines', opt_hover_max_lines)
            opt_hover_additional_commands = j.get('hover_additional_commands', opt_hover_additional_commands)
            opt_hover_with_ctrl = j.get('hover_with_ctrl', opt_hover_with_ctrl)
            opt_cudatext_in_py_env = j.get('cudatext_in_py_env', opt_cudatext_in_py_env)
            opt_lint_type = j.get('lint_type', opt_lint_type)
            opt_auto_append_bracket = j.get('auto_append_bracket', opt_auto_append_bracket)
            CompletionMan.auto_append_bracket = opt_auto_append_bracket
            opt_hard_filter = j.get('hard_filter', opt_hard_filter)
            CompletionMan.hard_filter = opt_hard_filter
            opt_use_cache = j.get('use_cache', opt_use_cache)
            CompletionMan.use_cache = opt_use_cache
            
            opt_use_markers = j.get('use_markers', opt_use_markers)
            CompletionMan.use_markers = opt_use_markers
            
            opt_servers_shutdown_max_time = j.get('servers_shutdown_max_time', opt_servers_shutdown_max_time)
            
            opt_enable_semantic_tokens = j.get('enable_semantic_tokens', opt_enable_semantic_tokens)
            opt_semantic_max_lines = j.get('semantic_max_lines', opt_semantic_max_lines)
            opt_semantic_colors_light = j.get('semantic_colors_light', opt_semantic_colors_light)
            Language.semantic_colors_light = opt_semantic_colors_light
            opt_semantic_colors_dark = j.get('semantic_colors_dark', opt_semantic_colors_dark)
            Language.semantic_colors_dark = opt_semantic_colors_dark
            opt_disabled_contexts = j.get('disabled_contexts', opt_disabled_contexts)
            Language.disabled_contexts = opt_disabled_contexts
            opt_complete_from_text = j.get('complete_from_text', opt_complete_from_text)
            Language.complete_from_text = opt_complete_from_text
            opt_diagnostics_in_a_corner = j.get('diagnostics_in_a_corner', opt_diagnostics_in_a_corner)
            DiagnosticsMan.opt_diagnostics_in_a_corner = opt_diagnostics_in_a_corner

            # full spy log file (empty = off): every JSON-RPC message of
            # every server, both directions, untruncated - see
            # language.SPY_FILE
            opt_spy_file = j.get('spy_file', '')
            language_mod_spy = __import__('cuda_lsp.language', fromlist=['language'])
            language_mod_spy.SPY_FILE = opt_spy_file
            
            opt_enable_code_tree = j.get('enable_code_tree', opt_enable_code_tree)
            opt_tree_types_show = j.get('tree_types_show', opt_tree_types_show)

            _opt_lint_underline_style = j.get('lint_underline_style', opt_lint_underline_style)
            if _opt_lint_underline_style in LINT_STYLE_MAP:
                opt_lint_underline_style = _opt_lint_underline_style

            # hidden,dbg
            opt_manual_didopen = j.get('manual_didopen', None)

            # apply options
            Hint.set_max_lines(opt_hover_max_lines)

        # plugin state
        if os.path.exists(fn_state):
            with open(fn_state, 'r', encoding='utf-8') as f:
                js = f.read()
            j = _json_loads(js)
            STATE.update(j)

        # servers
        _lsp_fns = get_server_cfg_fns()
        if _lsp_fns:
            user_lexids = {}

            for name in _lsp_fns:
                path = os.path.join(dir_settings, name)
                with open(path, 'r', encoding='utf-8') as f:
                    try:
                        j = _json_loads(f.read())
                    except:
                        _path = collapse_path(path)
                        print(f'NOTE: {LOG_NAME}: failed to load server config: {_path}')
                        continue

                # load lex map from config
                langids = j.setdefault('langids', [])
                lexmap = j.get('lexers', {})
                for lex,langid in lexmap.items():
                    langids.append(langid)
                    user_lexids[lex] = langid

                # add cuda/py to python server's PYTHONPATH env
                if opt_cudatext_in_py_env  and  'python' in langids:
                    env_paths = j.setdefault('env_paths', {})
                    py_env_paths = env_paths.setdefault('PYTHONPATH', [])
                    py_env_paths.append(app_path(APP_DIR_PY))

                if not langids:
                    _path = collapse_path(path)
                    print(f'NOTE: {LOG_NAME}: server config error - no associated lexers: {_path}')
                    continue
                if 'name' not in j:
                    j['name'] = os.path.splitext(name)[0]
                # tree options
                j.setdefault('enable_code_tree', opt_enable_code_tree)
                j.setdefault('tree_types_show', opt_tree_types_show)

                servers_cfgs.append(j)

            update_lexmap(user_lexids) # add user mapping to global map

        if not servers_cfgs:
            _dir_settings = collapse_path(dir_settings)
            print(f'NOTE: {LOG_NAME}: no server configs loaded from "{_dir_settings}"')


    def _save_config(self):
        import json

        j = {
            'root_dir_source':           opt_root_dir_source,
            'send_change_on_request':    opt_send_change_on_request,
            'enable_mouse_hover':        opt_enable_mouse_hover,
            'hover_dlg_max_lines':       opt_hover_max_lines,
            'hover_additional_commands': opt_hover_additional_commands,
            'hover_with_ctrl':           opt_hover_with_ctrl,
            'cudatext_in_py_env':        opt_cudatext_in_py_env,
            'lint_type':                 opt_lint_type,
            'lint_underline_style':      opt_lint_underline_style,
            'enable_code_tree':          opt_enable_code_tree,
            'tree_types_show':           opt_tree_types_show,
            'auto_append_bracket':       opt_auto_append_bracket,
            'hard_filter':               opt_hard_filter,
            'use_cache':                 opt_use_cache,
            'servers_shutdown_max_time': opt_servers_shutdown_max_time,
            'enable_semantic_tokens':    opt_enable_semantic_tokens,
            'semantic_max_lines':        opt_semantic_max_lines,
            'semantic_colors_light':     opt_semantic_colors_light,
            'semantic_colors_dark':      opt_semantic_colors_dark,
            'disabled_contexts':         opt_disabled_contexts,
            'complete_from_text':        opt_complete_from_text,
            'use_markers':               opt_use_markers,
            'diagnostics_in_a_corner':   opt_diagnostics_in_a_corner,
            'spy_file':                  opt_spy_file,
        }
        if opt_manual_didopen is not None:
            j['manual_didopen'] = opt_manual_didopen

        with open(fn_config, 'w', encoding='utf-8') as f:
            json.dump(j, f, indent=2)


    # DBG
    @property
    def lcs(self):
        return self._langs.get('csharp')
    @property
    def lpy(self):
        return self._langs.get('python')
    @property
    def lcpp(self):
        return self._langs.get('cpp')

    def _kill_servers(self):
        """ only use before exiting
        """
        for lang in self._langs.values():
            try:
                lang.process.kill()
            except:
                pass



servers_cfgs = []
"""
{
    'name': 'pyls',
    'langids': ['python'],
    'cmd': ['pyls'],
    'work_dir': '/mnt/H/cuda/__FM/py/cuda_runner',
    #'tcp_port': 2087,
},
#{
    #'name': 'omnisharp',
    #'langids': ['csharp'],
    #'work_dir': '/media/q/REST_API',
    #'cmd': [
        #'/home/eon/Downloads/omnisharp-linux-x64/run',
        #'-s', '/media/q/REST_API',
        #'-lsp',
        #'omnisharp.useGlobalMono:always',
    #],
#},
#{
    #'name': 'omnisharp',
    #'langids': ['csharp'],
    #'work_dir': '/media/q/websocket-sharp',
    #'cmd': [
        #'/home/eon/Downloads/omnisharp-linux-x64/run',
        #'-s', '/media/q/websocket-sharp',
        #'-lsp',
        #'omnisharp.useGlobalMono:always',
    #],
#},
#{
    #'name': 'ccls',
    #'langids': ['c', 'cpp'],
    #'cmd': ['ccls'],
    #'work_dir': '/mnt/G/del/C__menu_run/',
#},
]
"""


