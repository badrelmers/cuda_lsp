"""Single LSP panel: ONE bottom-panel page, one icon, per-file context.

MODEL (LogStore) - one per server INSTANCE (Language):
  * srv_msgs   - server-level messages: server stderr/stdout, OmniSharp
                 'o#/...' events, window/showMessage + logMessage, unhandled
                 server messages, response errors, server-level spy traffic
                 (initialize etc). Ring buffer, cap SRV_MSGS_CAP.
  * file_spy   - {uri: [LogMsg]}: per-document spy traffic (didOpen,
                 didChange, completion requests/responses...). Ring buffer,
                 cap FILE_SPY_CAP per file. Dropped when the document closes.
  * file_diags - {uri: [LogMsg]}: per-document diagnostics block, REPLACED
                 atomically on every publishDiagnostics. NO cap: diagnostics
                 are the CURRENT STATE of the document, not a history stream
                 (a file has exactly as many as the server reports - hiding
                 or dropping them would lie about the file's errors).
  Chronological order across all lists is kept by a per-store sequence
  number; the view merges by it (heapq.merge of pre-sorted lists).

VIEW (LspPanel) - a single bottom-panel page "LSP" (one icon), created lazily
  when the first server starts. It follows the ACTIVE editor tab - the
  editor holding keyboard focus, ELSE the most recently opened/activated
  visible tab (VS Code's 'active editor' notion: keyboard focus can sit
  on a side panel, e.g. the project-manager tree re-focusing itself
  right after opening a file, with no on_focus/on_tab_change fired for
  the new tab): the context (store, uri) is set ONLY by
  Command.sync_panel() - lsp.py owns the
  "focused tab -> server instance" resolution, nobody else touches panel
  internals. The visible messages are the focused file's diagnostics + spy
  traffic + the server-level messages of the focused file's server instance.
  The instance picker lists every server instance with its files NESTED
  under it (indented tree - they visibly belong to their server): a manual
  pick of a SERVER pins the panel to that ONE instance (its server-level
  messages and ALL its files - logs of other servers are never mixed in)
  until the next tab switch; a pick of one FILE pins it to that file ONLY
  (that file's spy traffic + diagnostics block + its server's own
  messages); '(follow focused tab)' cancels any pin immediately.

Rendering is COALESCED: every model change schedules one UI tick
  (TICK_MS); the tick appends only the NEW visible messages (fast path) or
  fully re-renders (context switch, filter change, diagnostics replacement,
  ring-buffer eviction). The append path CONSUMES its queue - every message
  is rendered exactly once - and filters disabled categories exactly like
  the full render, so the view always mirrors the model. When the panel page is not the active bottom-panel
  page, UI work is skipped (button badge only) and redone when it is shown
  (on_show). Auto-follow scrolling: the panel scrolls to the end ONLY while
  the memo is at its bottom (terminal behaviour) or right after a context
  switch; scrolling up pauses auto-scrolling - re-renders (diagnostics
  replacement, ring eviction, page re-show) NEVER force the scroll.

BACKGROUND-ANALYSIS QUIET MODE (the 'log flood' of big workspaces):
  while a server loads a big workspace and runs its workspace-wide
  background analysis (OmniSharp: the o#/projectadded/restore events of
  the load phase, then o#/backgrounddiagnosticstatus Started..Finished
  of the sweep - thousands of messages on a 100+ project solution:
  logMessage per project step, per-file publishDiagnostics + the Spy
  raw-JSON twin of both), the store enters 'analysis' state (omnisharp.py
  drives it via analysis_touch/_start/_progress/_finish):
  * VIEW: the panel shows one compact PROGRESS PAGE instead of the stream
    (analysis is running, done/total files, elapsed, hidden totals, the
    last few KEPT events) - O(1) per refresh, re-armed at
    ANALYSIS_TICK_MS; the Diagnostics cell stays LIVE for the focused
    file. On finish, the normal view is fully re-rendered from the model.
  * MODEL: the two flood categories are NOT stored, only counted -
    info/log-level window/logMessage and SERVER-LEVEL Spy traffic (the
    raw twin of the same stream). Kept: errors/warnings (lost evidence
    otherwise), OmniSharp event lines (the meaningful history), per-file
    Spy as one compact bodyless line (keeps every analyzed file listed
    in the instance picker at ~zero cost), stderr, Messages, Unhandled.
    The finish line reports what was hidden; the full untruncated stream
    stays available in the 'spy_file' option dump. This is the model of
    VS Code (window/logMessage goes into a level-filtered LogOutputChannel,
    never a live-rendered panel) and Neovim (log_level filters
    window/logMessage, logs go to a file) - progress belongs to the status
    bar, not to a rendered log view.
  * Safety: no o#/ workspace event for LOADING_STALE_MS (load phase) /
    ANALYSIS_STALE_MS (confirmed sweep) auto-resumes the normal view (an
    older/hung server must never freeze the panel); any fresh o#/ event
    re-arms the quiet mode. The staleness valve runs in the render tick
    BOTH while the page is shown and while it is hidden (hidden messages
    keep the tick alive via analysis_note_hidden -> _notify_tick), so a
    stale phase cannot keep hiding messages just because nobody watches.

UI-thread only: stores are fed from process_queues()/DiagnosticsMan/
  omnisharp handlers, which all run in the app thread. The reader/writer
  threads of a server go through queues and never touch this module.
"""

import os
import re
import time
import heapq
from collections import namedtuple, deque
from itertools import count
from operator import itemgetter

from cudatext import *
import cudax_lib as apx
import cudatext_cmd as cmds

from lsprotocol import types as lsp

from .util import uri_to_path

_ = apx.get_translation(__file__)  # I18N

# ---------------------------------------------------------------------------
# message kinds
# ---------------------------------------------------------------------------

TYPE_MSG       = 'type_msgs'      # window/showMessage
TYPE_LOG       = 'type_logs'      # window/logMessage
TYPE_DIAG      = 'type_diags'     # publishDiagnostics blocks (per file)
TYPE_SPY       = 'type_spy'       # debug spy of raw JSON-RPC traffic
TYPE_UNHANDLED = 'type_unhandled' # server messages without a handler
TYPE_OMNISHARP = 'type_omnisharp' # OmniSharp-specific 'o#/...' events

SEVERITY_ERR  = 'svr_err'
SEVERITY_WRN  = 'svr_wrn'
SEVERITY_INFO = 'svr_inf'
SEVERITY_LOG  = 'svr_log'
SEVERITY_NA   = 'svr_na'

SEVERITYS = (SEVERITY_ERR, SEVERITY_WRN, SEVERITY_INFO, SEVERITY_LOG)

SEVERITY_MAP = {
    1: SEVERITY_ERR,
    2: SEVERITY_WRN,
    3: SEVERITY_INFO,
    4: SEVERITY_LOG,
}

_icons_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'icons')
SEVERITY_IC_PATHS = {
    SEVERITY_ERR:  os.path.join(_icons_dir, 'error.png'),
    SEVERITY_WRN:  os.path.join(_icons_dir, 'warning.png'),
    SEVERITY_INFO: os.path.join(_icons_dir, 'information.png'),
    SEVERITY_LOG:  os.path.join(_icons_dir, 'hint.png'),
    SEVERITY_NA:   os.path.join(_icons_dir, 'severity_na.png'),
}

PANEL_CAPTIONS = {
    TYPE_MSG:       _('Messages'),
    TYPE_LOG:       _('Logs'),
    TYPE_DIAG:      _('Diagnostics'),
    TYPE_SPY:       _('Spy'),
    TYPE_UNHANDLED: _('Unhandled'),
    TYPE_OMNISHARP: _('OmniSharp'),

    SEVERITY_ERR:   _('Error'),
    SEVERITY_WRN:   _('Warning'),
    SEVERITY_INFO:  _('Info'),
    SEVERITY_LOG:   _('Log'),
}

# message: 'seq' keeps chronological order across the store's lists
LogMsg = namedtuple('LogMsg', 'seq text type severity')

# ring-buffer caps: hard bounds on the memory one server instance's logs
# use. These are the DEFAULTS - overridden at plugin start by the cuda_lsp.json
# options 'log_cap_server_msgs' / 'log_cap_file_spy' (see lsp.py); a value
# <= 0 disables the cap. Diagnostics have NO cap at all: they are the
# current state of the document, not a history stream.
SRV_MSGS_CAP = 10000  # server-level messages per instance
FILE_SPY_CAP = 5000   # spy traffic per document

PLACEHOLDER_NO_SERVER   = _('No LSP server for this file')
PLACEHOLDER_NO_SERVER_2 = _('Open a file with a lexer served by a configured server')
PLACEHOLDER_NO_MSGS     = _('(no log messages for this file)')
PLACEHOLDER_NO_MSGS_ALL = _('(no log messages)')

# trailing column range of a diagnostics entry, appended by
# DiagnosticsMan._diag_pos_suffix (language.py): '(21-22)' normal single-line
# range, '(21)' zero-width insertion point, '(130:21-144:34)' range spanning
# several lines (both positions carry their line). Anchored at end-of-line:
# the suffix is always appended last, so even a message that itself ends in
# '(9)' cannot shadow the real range. group(1): start char, or start LINE
# when the suffix is multi-line; group(2): start char of a multi-line range.
_RE_DIAG_RANGE = re.compile(r'\((\d+)(?::(\d+))?(?:-\d+(?::\d+)?)?\)$')


# ---------------------------------------------------------------------------
# MODEL
# ---------------------------------------------------------------------------

class LogStore:
    """ Log model of ONE server instance (see module docstring). Carries the
    logging API used by language.py / omnisharp.py: log_str(), log(),
    set_file_diags(), clear_diagnostics(), drop_file(), clear(), detach().
    """

    def __init__(self, display_name, full_name=None):
        self.display_name = display_name
        self.full_name = full_name or display_name  # picker hover hint
        self.live = True        # False after detach()
        self._seq = count()
        self.srv_msgs = []      # server-level LogMsgs (uri == None)
        self.file_spy = {}      # uri -> [LogMsg]
        self.file_diags = {}    # uri -> [LogMsg] (block, replaced atomically)
        self.diag_filenames = {}  # uri -> path (dbl-click jump)
        self.extra_types = set()  # every message type ever logged (filter bar)
        # background-analysis quiet mode: dict while the server runs a
        # workspace-wide background analysis (OmniSharp
        # o#/backgrounddiagnosticstatus Started..Finished). See the module
        # docstring - None = normal mode.
        self.analysis = None

    @property
    def name(self):
        return self.display_name

    def total_msgs(self):
        """ Total messages kept (button badge). """
        n = len(self.srv_msgs)
        for lst in self.file_spy.values():
            n += len(lst)
        for lst in self.file_diags.values():
            n += len(lst)
        return n

    def _note_type(self, type_):
        if type_ not in self.extra_types:
            self.extra_types.add(type_)
            return True   # new type: the filter bar must learn it
        return False

    def log_str(self, text, type_, severity=SEVERITY_NA, uri=None):
        """ Append one message. 'uri' tags it to one document (per-file
        scope); None = server-level. Cheap (one append + cap eviction); the
        panel renders later, coalesced. Never touches the UI here.

        While a background analysis runs (self.analysis), the two flood
        categories are NOT stored, only counted (VS Code/Neovim model: log
        streams below warning level are dropped by the log level, the user
        watches the status bar progress instead): info/log-level
        window/logMessage and server-level Spy traffic. Errors, warnings,
        OmniSharp events, per-file traffic and stderr are kept - they are
        low-volume and are what the user actually needs after the analysis.
        """
        if not self.live:
            return
        if not isinstance(text, str):
            text = str(text)
        if not text.endswith('\n'):
            text += '\n'
        if not isinstance(type_, str):
            type_ = str(type_)

        if self.analysis is not None and self._hide_in_analysis(type_,
                                                                severity,
                                                                uri):
            self.analysis_note_hidden(type_)
            return

        msg = LogMsg(next(self._seq), text, type_, severity)
        if uri is None:
            lst = self.srv_msgs
            cap = SRV_MSGS_CAP
        else:
            lst = self.file_spy.setdefault(uri, [])
            cap = FILE_SPY_CAP

        evicted = False
        if cap > 0 and len(lst) >= cap:   # cap<=0: unlimited
            del lst[:len(lst) - cap + 1]
            evicted = True
        lst.append(msg)

        if self.analysis is not None and uri is None:
            # kept server-level event: echo it in the progress view's tail
            # (short text - one line, no bodies)
            tail = text.strip()
            if len(tail) > 200:
                tail = tail[:197] + '...'
            self.analysis['tail'].append(tail)

        new_type = self._note_type(type_)
        _notify_msg(self, msg, uri, evicted, new_type)

    def _hide_in_analysis(self, type_, severity, uri):
        """ Should this message be HIDDEN (counted, not stored) while a
        background analysis runs? The rule mirrors what other editors do
        with server log streams (level filtering):
        * TYPE_LOG below warning severity - the main flood form: OmniSharp
          logs every project load/analysis step as window/logMessage at
          info/log level; hundreds to thousands per big workspace;
        * TYPE_SPY of server-level traffic - the raw JSON twin of the same
          stream (and of the o#/... events), i.e. the flood again, bigger.
        Everything else is KEPT (rendering is what the progress view pauses,
        not collection): errors/warnings would be lost evidence otherwise,
        per-file Spy lines keep the analyzed files listed in the instance
        picker, and the compact OmniSharp event lines are the meaningful
        history of what was analyzed.
        """
        if type_ == TYPE_LOG and severity not in (SEVERITY_ERR, SEVERITY_WRN):
            return True
        if type_ == TYPE_SPY and uri is None:
            return True
        return False

    # -- background analysis quiet mode ----------------------------------

    def analysis_start(self, total=0, projects=0, sweep=True):
        """ A workspace-wide background analysis began: either the SWEEP
        itself (OmniSharp o#/backgrounddiagnosticstatus Status==0; sweep=
        True, with file/project numbers) - or the LOADING phase was opened
        earlier by analysis_touch() (first o#/projectadded / restore event)
        and this call UPGRADES it to the sweep. An already-open phase keeps
        its hidden counters: the load flood and the sweep flood are ONE
        quiet period for the user, and the finish line must report them
        together. Until analysis_finish(): the panel's view of this
        instance is replaced by a compact progress page, while the flood
        categories are only counted (see _hide_in_analysis). """
        now = time.monotonic() * 1000
        if self.analysis is not None:
            an = self.analysis
            an['sweep'] = an['sweep'] or bool(sweep)
            if isinstance(total, int):
                an['total'] = total
                an['remaining'] = total
            if isinstance(projects, int):
                an['projects'] = projects
            an['last_event_ms'] = now
            _notify_change(self, None)
            return
        self.analysis = {
            'sweep': bool(sweep),
            'total': total if isinstance(total, int) else 0,
            'remaining': total if isinstance(total, int) else 0,
            'projects': projects if isinstance(projects, int) else 0,
            'started_ms': now,
            'last_event_ms': now,
            'hidden': {},      # message type -> count (the hidden flood)
            'hidden_total': 0,
            'tail': deque(maxlen=ANALYSIS_TAIL),  # kept server-level texts
        }
        _notify_change(self, None)

    def analysis_touch(self, projects=None):
        """ A workspace (RE)LOAD began: the first o#/projectadded /
        o#/packagerestore* event. Opens the quiet mode in its LOADING
        phase (no sweep numbers yet - the progress page says 'projects
        loading') if it was closed; refreshes the staleness clock if it was
        already open (a mid-sweep project change must not reset the hidden
        counters). OmniSharp loads ALL projects - and floods a logMessage
        per step - BEFORE the background-diagnostic sweep even starts, so
        the quiet mode cannot wait for the sweep's Started event. """
        if self.analysis is None:
            self.analysis_start(projects=projects if projects else 0,
                                sweep=False)
            return
        an = self.analysis
        if isinstance(projects, int):
            an['projects'] = projects
        an['last_event_ms'] = time.monotonic() * 1000
        _notify_change(self, None)

    def analysis_progress(self, remaining, total=None, projects=None):
        """ Progress update (o#/backgrounddiagnosticstatus Status==1):
        refresh the numbers only - the panel re-renders its progress page
        coalesced, never per event. A progress event also proves a sweep
        is running (marks the phase as sweep). """
        an = self.analysis
        if an is None:
            return
        if isinstance(remaining, int):
            an['remaining'] = remaining
        if isinstance(total, int):
            an['total'] = total
        if isinstance(projects, int):
            an['projects'] = projects
        an['sweep'] = True
        an['last_event_ms'] = time.monotonic() * 1000
        _notify_change(self, None)

    def analysis_finish(self):
        """ The analysis finished (Status==2) - or the phase is dropped
        (stale/expiry): back to the normal log view. The hidden totals are
        reported by the CALLER (omnisharp.py appends them to the 'analysis
        finished' line) BEFORE this runs, while self.analysis still lives.
        """
        if self.analysis is None:
            return
        self.analysis = None
        _notify_change(self, None)

    def analysis_stale_ms(self):
        """ ms since the last analysis status event, 0 when not analyzing. """
        an = self.analysis
        if an is None:
            return 0
        return time.monotonic() * 1000 - an['last_event_ms']

    def analysis_note_hidden(self, type_):
        """ Count one message hidden by the analysis gating (used by
        log_str, and directly by language._on_spy_message which skips
        server-level spy traffic BEFORE serializing its body). """
        an = self.analysis
        if an is None:
            return False
        an['hidden'][type_] = an['hidden'].get(type_, 0) + 1
        an['hidden_total'] += 1
        # keep the panel's coalesced tick ALIVE while the flood is being
        # hidden: hidden messages schedule no _notify_msg of their own, so
        # without this a stale analysis phase would never be re-examined
        # while the panel page is not shown (the staleness valve lives in
        # the tick) - and the progress page's hidden-totals line would go
        # stale between status events too.
        _notify_tick()
        return True

    def analysis_hidden_str(self):
        """ '5231 message(s) (Logs 3498, Spy 1733)' for the finish line;
        '' when nothing was hidden (small workspaces - nothing to explain).
        """
        an = self.analysis
        if an is None or not an['hidden_total']:
            return ''
        parts = ', '.join(f'{PANEL_CAPTIONS.get(k, k)} {n}'
                          for k, n in sorted(an['hidden'].items()))
        return f"{an['hidden_total']} {_('message(s)')} ({parts})"

    def log(self, params):
        """ window/showMessage / window/logMessage params. """
        type_ = TYPE_MSG if isinstance(params, lsp.ShowMessageParams) else TYPE_LOG
        mtype = getattr(params, 'type', None)
        severity = SEVERITY_MAP.get(mtype.value if mtype is not None else None,
                                    SEVERITY_NA)
        self.log_str(params.message, type_, severity)

    def set_file_diags(self, uri, lines, filename=None):
        """ Replace the whole diagnostics block of one document (atomic).
        'lines': list of (text, severity) already formatted for display; an
        empty list clears the block. Independent of gutter/lint options -
        the panel always shows diagnostics. NO cap: every diagnostic the
        server published is kept and shown.
        """
        if not self.live:
            return
        if filename:
            self.diag_filenames[uri] = filename

        if not lines:
            if self.file_diags.pop(uri, None) is not None:
                _notify_change(self, uri)
            return

        msgs = [LogMsg(next(self._seq),
                       text if text.endswith('\n') else text + '\n',
                       TYPE_DIAG, severity)
                for text, severity in lines]
        self.file_diags[uri] = msgs
        # no _note_type: the Diagnostics cell is a PERMANENT cell of the bar
        # (always shown), so a diagnostics block can never grow the bar
        _notify_change(self, uri)

    def clear_diagnostics(self, uri=None):
        """ Drop diagnostic blocks - of one document, or of all (uri=None). """
        if not self.live:
            return
        if uri is None:
            if self.file_diags:
                self.file_diags.clear()
                _notify_change(self, None)
        elif self.file_diags.pop(uri, None) is not None:
            _notify_change(self, uri)

    def drop_file(self, uri):
        """ Document closed: its spy traffic is unreachable now (the tab is
        gone) - free it. The (small) diagnostics block is kept: it is the
        last known state, replaced on the next publish.
        """
        if not self.live:
            return
        if self.file_spy.pop(uri, None) is not None:
            _notify_change(self, uri)

    def log_files(self):
        """ Documents of this instance which have any log messages (per-file
        spy traffic or a diagnostics block), most recently active first -
        the instance picker lists them nested under their server.
        """
        latest = {}
        for uri, lst in self.file_spy.items():
            if lst:
                latest[uri] = lst[-1].seq
        for uri, lst in self.file_diags.items():
            if lst:
                seq = lst[-1].seq
                if seq > latest.get(uri, -1):
                    latest[uri] = seq
        return [uri for uri, _ in sorted(latest.items(),
                                         key=lambda kv: kv[1], reverse=True)]

    def file_msg_count(self, uri):
        """ Messages kept for ONE document (per-file Spy + its diagnostics
        block) - the instance picker shows it next to the file name, so a
        file's activity is visible WITHOUT opening/rendering its log.
        """
        return len(self.file_spy.get(uri, ())) + len(self.file_diags.get(uri, ()))

    def clear(self):
        """ User 'Clear': drop everything of this instance. """
        if not self.live:
            return
        self.srv_msgs.clear()
        self.file_spy.clear()
        self.file_diags.clear()
        self.diag_filenames.clear()
        _notify_change(self, None)

    def detach(self):
        """ Instance is being shut down: forget it in the panel. """
        self.live = False
        _unregister(self)


# ---------------------------------------------------------------------------
# VIEW
# ---------------------------------------------------------------------------

# statusbar cells which are not category/severity filters
CELL_INSTANCE = '__instance__'

# fixed width of the instance cell (pixels): 'server (project-folder)'
# names must not resize the bar on every switch
INSTANCE_CELL_W = 180

# the Diagnostics cell is separated from the other filter cells by this
# margin (pixels): it is the heart of the panel, the eye must find it first
MARGIN_CELL_W = 16

# state line color of the Diagnostics cell (BGR): amber - every other
# filter cell uses the green 'line_enabled_color'
DIAG_LINE_COLOR = 0x14A2E0

PANEL_NAME = 'LSP'   # the single bottom-panel page caption

# background-analysis quiet mode (see LogStore.analysis): how long the
# progress view stays up without ANY analysis status event before the panel
# gives up waiting and resumes the normal log view (a hung/older server must
# never leave the panel stuck on 'analysis is running'). Two valves: the
# workspace-LOADING phase (opened by the first o#/projectadded/restore
# event, no sweep numbers yet) closes after LOADING_STALE_MS; the confirmed
# SWEEP phase (o#/backgrounddiagnosticstatus Started..Finished) after
# ANALYSIS_STALE_MS (longer: a big sweep can be quiet between progress
# batches)
LOADING_STALE_MS = 30_000
ANALYSIS_STALE_MS = 90_000
# refresh period of the progress view while an analysis runs (re-armed
# one-shot ticks, so no extra timer machinery is needed)
ANALYSIS_TICK_MS = 500
# how many recently KEPT server-level messages the progress view echoes
# (errors/warnings/OmniSharp events - visibility without the flood)
ANALYSIS_TAIL = 4


class LspPanel:
    """ The single LSP log panel (bottom panel, one icon). See module
    docstring. Created lazily by make_store() on the first server start.
    """

    fn_icon = os.path.join(os.path.dirname(__file__), 'icons', 'lsp.png')

    # Command.sync_panel: re-derives the panel context from the focused
    # editor tab. Registered once by Command.__init__; the panel calls it as
    # a coalesced self-heal (store registered / died / logged while not
    # shown). None when no Command runs (unit tests of Language alone).
    sync_hook = None

    TICK_MS = 120        # coalesced render period
    HEAL_MS = 300        # coalesced self-heal period
    PENDING_CAP = 400    # more pending appends than this -> full re-render
    # ring evictions drop the memo's OLDEST lines; re-rendering fully on
    # EVERY eviction would cost a full pass per message in a steady stream
    # (cap reached) - tolerate a few stale top lines, rebuild in bulk
    FULL_ON_EVICTIONS = 64
    # background analysis quiet mode (see LogStore.analysis): the view
    # refresh period while the progress page is up
    PROGRESS_TICK_MS = ANALYSIS_TICK_MS

    _colors = None
    _instance = None

    def __init__(self, state=None):
        self.stores = []       # registered LogStores (all servers, in order)
        self.store = None      # shown store (context)
        self.uri = None        # focused document uri (None = pinned instance)
        self._picked = False   # a manual instance-picker pick sticks
        self._ctx_follow = True  # context switch: next render shows the end

        state = state if isinstance(state, dict) else {}
        self._disabled_items = set(state.get('log_panel_filter') or ())
        self._is_wrap = state.get('is_wrap', True)

        # deferred rendering state
        self._pending = []     # LogMsgs to append on the next tick
        self._need_full = True # full re-render needed on the next tick
        self._sb_dirty = False # filter bar must be rebuilt on the next tick
        self._timer_on = False
        self._heal_scheduled = False
        self._placeholder = True # memo currently shows a placeholder line
        self._evictions = 0     # ring evictions since the last full render

        self._counts = {}        # cell name -> count of the context (text suffix)
        self._diag_sevs = {}     # severity str -> count of TYPE_DIAG messages
        self._inst_caption = '-' # instance cell caption (count/pin appended live)
        self._inst_pin = ''      # ' *' while a manual picker pick is pinned
        self._severity_ims = {}  # severity str -> imagelist index
        self._sb_cellind_map = {}  # cell name -> statusbar cell index
        self._h_btn_sidebar = None
        self._h_ed_menu = None
        self._decor_tag = app_proc(PROC_GET_UNIQUE_TAG, '')

        self._init_form()
        self._setup_severity_icons()
        self._update_sb()

    # -- singleton access ---------------------------------------------------

    @classmethod
    def get(cls, create=True):
        """ The panel instance; None (create=False) when not created yet. """
        if cls._instance is None and create:
            cls._instance = LspPanel(_pending_state)
        return cls._instance

    # -- lifecycle ----------------------------------------------------------

    def _init_form(self):
        self.h_dlg = dlg_proc(0, DLG_CREATE)
        dlg_proc(self.h_dlg, DLG_PROP_SET, prop={'on_show': self.on_show})

        # log view (embedded editor)
        n = dlg_proc(self.h_dlg, DLG_CTL_ADD, prop='editor')
        dlg_proc(self.h_dlg, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'memo',
            'align': ALIGN_CLIENT,
            'on_menu': self.on_ed_menu,
            })
        h_memo = dlg_proc(self.h_dlg, DLG_CTL_HANDLE, index=n)
        self._memo = Editor(h_memo)
        dlg_proc(self.h_dlg, DLG_CTL_PROP_SET, index=n, prop={
            'on_click_dbl': self.memo_on_click_dbl,
            } )

        # top bar: filters / instance / file
        n = dlg_proc(self.h_dlg, DLG_CTL_ADD, prop='statusbar')
        dlg_proc(self.h_dlg, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'statusbar',
            'align': ALIGN_TOP,
            })
        self._h_sb = dlg_proc(self.h_dlg, DLG_CTL_HANDLE, index=n)

        self._set_memo_wrap(self._is_wrap)

        self._memo.set_prop(PROP_GUTTER_ALL,    True)
        self._memo.set_prop(PROP_GUTTER_BM,     True)
        self._memo.set_prop(PROP_GUTTER_FOLD,   False)
        self._memo.set_prop(PROP_GUTTER_NUM,    False)
        self._memo.set_prop(PROP_GUTTER_STATES, False)

        self._memo.set_prop(PROP_UNDO_LIMIT,       0)
        self._memo.set_prop(PROP_MINIMAP,          False)
        self._memo.set_prop(PROP_MICROMAP,         False)
        self._memo.set_prop(PROP_LAST_LINE_ON_TOP, False)
        self._memo.set_prop(PROP_HILITE_CUR_LINE,  False)

        self._set_log_lexer()

        dlg_proc(self.h_dlg, DLG_SCALE)

        app_proc(PROC_BOTTOMPANEL_ADD_DIALOG, (PANEL_NAME, self.h_dlg, self.fn_icon))
        for props in app_proc(PROC_BOTTOMPANEL_ENUM_ALL, ''):
            if props['cap'] == PANEL_NAME:
                self._h_btn_sidebar = props['btn_h']
                break

    def _set_log_lexer(self):
        """ Color the log view with a log lexer. Preference: the
        user-installable 'Logfiles' lexer, else CudaText's built-in lite
        lexer 'Log files ^' (lite lexer names carry the ' ^' suffix - CudaText
        wiki, 'Lite lexers'); 'Log files' without the suffix is also probed
        defensively. lexer_proc(LEXER_GET_PROP) returns None for a missing
        lexer, so nothing is set (plain text, as before) when none exists. """
        try:
            for name in ('Logfiles', 'Log files ^', 'Log files'):
                if lexer_proc(LEXER_GET_PROP, name):
                    self._memo.set_prop(PROP_LEXER_FILE, name)
                    return name
        except Exception:
            pass
        return None

    def _setup_severity_icons(self):
        h_im = self._memo.decor(DECOR_GET_IMAGELIST)
        statusbar_proc(self._h_sb, STATUSBAR_SET_IMAGELIST, value=h_im)
        for severity, icon_path in SEVERITY_IC_PATHS.items():
            self._severity_ims[severity] = imagelist_proc(
                h_im, IMAGELIST_ADD, value=icon_path)

    def close(self):
        timer_proc(TIMER_STOP, self._on_tick, 0)
        timer_proc(TIMER_STOP, self._do_heal, 0)
        self._memo.set_text_all('')
        self.stores.clear()
        self.store = None
        app_proc(PROC_BOTTOMPANEL_REMOVE, PANEL_NAME)
        dlg_proc(self.h_dlg, DLG_FREE)
        LspPanel._instance = None

    # -- store registry -----------------------------------------------------

    def register(self, store):
        if store not in self.stores:
            self.stores.append(store)
            # a new instance may serve the focused tab: re-derive the context
            self._request_heal()
            self._schedule()

    def _unregister(self, store):
        if store in self.stores:
            self.stores.remove(store)
        if self.store is store:
            self.store = None
            self.uri = None
            self._picked = False
            self._pending.clear()
            self._need_full = True
            self._sb_dirty = True   # instance cell must not show a dead name
        # the focused tab may belong to a remaining instance: re-derive
        self._request_heal()
        self._schedule()

    # -- context ------------------------------------------------------------

    def set_context(self, store, uri):
        """ Show this server instance, scoped to this document uri (the
        focused editor tab). uri=None = PINNED instance (a manual picker
        pick: the whole instance - its server-level messages and all its
        files; no other server is shown). store=None blanks the panel.
        No-op when unchanged. Only Command.sync_panel() calls this.
        """
        if store is not None and store not in self.stores:
            return  # stale focus event of a shut-down instance
        if self.store is store and self.uri == uri:
            return
        self.store = store
        self.uri = uri
        self._ctx_follow = True   # fresh context: its end = the latest logs
        self._pending.clear()
        self._need_full = True
        self._update_sb()   # instance cell + the store's type cells
        self._schedule()

    def clear_picked(self):
        """ A manual instance-picker pick dies on the tab switch: the panel
        follows the focused tab again. """
        self._picked = False

    @property
    def picked(self):
        return self._picked

    # -- model -> view notifications (UI thread only) ------------------------

    def _on_store_msg(self, store, msg, uri, evicted, new_type):
        if store is self.store:
            # visible in this context: server-level messages (uri None -
            # they belong to the focused server) and the focused file's
            # per-file messages; a pinned instance shows everything
            if uri is None or self.uri is None or uri == self.uri:
                if self._placeholder:
                    # placeholder shown: the memo no longer mirrors the
                    # model - rebuild it (the message is in the model)
                    self._need_full = True
                    self._pending.clear()
                elif evicted:
                    # oldest entry dropped from a FULL ring: tolerate a few
                    # stale top lines, rebuild in bulk (steady streams would
                    # otherwise pay a full render per message). The message
                    # itself still queues below - dropping it here made it
                    # INVISIBLE until the bulk rebuild (a steady stream at
                    # the cap showed only every 64th message!)
                    self._evictions += 1
                    if self._evictions >= self.FULL_ON_EVICTIONS:
                        self._need_full = True
                        self._pending.clear()
                if not self._need_full:
                    # queue for the append path; the tick CONSUMES the
                    # queue, so every message is rendered exactly once
                    self._pending.append(msg)
                    if len(self._pending) > self.PENDING_CAP:
                        self._need_full = True
                        self._pending.clear()
            # messages of OTHER files: stored, shown when they get the focus
            if new_type:
                self._sb_dirty = True
        else:
            # not shown: either the panel rightly follows another tab, or
            # the context is stale (this store's instance was just created
            # for the focused tab) - re-derive, coalesced
            self._request_heal()
        self._schedule()

    def _on_store_change(self, store, uri):
        """ The visible history changed SHAPE (diagnostics block replaced /
        cleared, file dropped, store cleared) - full re-render when it
        affects the context. uri=None means 'everything changed'.
        NOTE: no _sb_dirty here - the bar's cell set only ever GROWS via a
        NEW message type, which _on_store_msg already dirties (log_str's
        _note_type); the Diagnostics cell is permanent, so a diagnostics
        replace (the most frequent event - every publishDiagnostics) must
        NOT rebuild the whole bar (new cell indices would churn on every
        server analysis). """
        if store is self.store:
            if self.uri is None or uri is None or uri == self.uri:
                self._need_full = True
                self._pending.clear()
        self._schedule()

    # -- coalesced UI tick ----------------------------------------------------

    def _schedule(self, ms=None):
        if not self._timer_on:
            self._timer_on = True
            timer_proc(TIMER_START_ONE, self._on_tick,
                       ms if ms is not None else self.TICK_MS)

    def _on_tick(self, tag='', info=''):
        self._timer_on = False

        if not self._page_shown():
            # the user is not looking at the panel: badge only; the render
            # happens when the page is shown (on_show re-schedules)
            self._need_full = True
            self._pending.clear()
            self._update_badge()
            # the quiet-mode staleness valve must ALSO run while the page
            # is hidden: a stale analysis phase (hung/old server, no more
            # o#/ events) would otherwise keep hiding - counting, not
            # storing - the instance's messages for as long as the page
            # stays unopened. Closing it here only flips the model back to
            # normal collection; the view itself catches up via on_show.
            self._valve_stale_analysis()
            return

        if self._sb_dirty:
            self._sb_dirty = False
            self._update_sb()

        if self._in_analysis():
            # background analysis quiet mode: the whole message stream is
            # REPLACED by one small progress page (set_text_all of ~10 lines
            # - O(1) per refresh, independent of the flood's volume); the
            # pending queue is included in the model, rendered by the full
            # re-render which analysis_finish() schedules. Re-armed at
            # PROGRESS_TICK_MS so the elapsed time/progress stay live even
            # between status events.
            if not self._valve_stale_analysis():
                self._render_progress()
                self._update_counts()
                self._update_badge()
                self._schedule(self.PROGRESS_TICK_MS)
                return
            # the valve closed a stale phase: fall through to the normal
            # path - analysis_finish()'s notification already marked the
            # full re-render as needed

        if self._need_full:
            self._render_full()
        elif self._pending:
            self._render_append()

        self._update_counts()
        self._update_badge()

    def _in_analysis(self):
        """ Is the SHOWN store currently in background-analysis quiet mode?
        (Only the context store matters: another tab's server analyzing
        must not blank THIS view.) """
        st = self.store
        return st is not None and st.analysis is not None

    def _valve_stale_analysis(self):
        """ Staleness valve of the quiet mode - returns True when it closed
        the phase. Two limits (both refreshed by every o#/ workspace event
        via analysis_touch/progress): the LOADING phase gives up waiting
        for the sweep's Started quickly (LOADING_STALE_MS), the confirmed
        sweep waits longer (quiet gaps between progress batches are
        normal). With no such event within the limit, the phase is dropped:
        an older/hung server must never leave the panel stuck on 'analysis
        is running' - NOR keep hiding (counting, not storing) its messages
        just because the page is not being watched. The report lines are
        logged while the phase is still open (kept: TYPE_OMNISHARP), then
        analysis_finish()'s notification schedules the normal view's full
        re-render. """
        st = self.store
        an = st.analysis if st is not None else None
        if an is None:
            return False
        stale_limit = (ANALYSIS_STALE_MS if an.get('sweep')
                       else LOADING_STALE_MS)
        if st.analysis_stale_ms() <= stale_limit:
            return False
        if an.get('sweep'):
            st.log_str(
                _('background analysis status stopped arriving - '
                  'resuming the log view (the server may still be '
                  'busy); messages hidden so far: ') +
                (st.analysis_hidden_str() or _('none')),
                type_=TYPE_OMNISHARP, severity=SEVERITY_WRN)
        elif an['hidden_total']:
            # silent for small workspaces (nothing was hidden);
            # when the load flood WAS hidden, report it once
            st.log_str(
                _('workspace load finished without a background '
                  'analysis sweep; hidden while loading: ') +
                st.analysis_hidden_str(),
                type_=TYPE_OMNISHARP, severity=SEVERITY_INFO)
        st.analysis_finish()
        return True

    def _page_shown(self):
        """ Is the LSP page the active bottom-panel page? """
        try:
            return app_proc(PROC_BOTTOMPANEL_GET, '') == PANEL_NAME
        except Exception:
            return True

    # -- self-heal -------------------------------------------------------------

    def _request_heal(self):
        """ Ask Command.sync_panel() to re-derive the context from the
        focused tab - coalesced and never missed (a pending request always
        fires). """
        if LspPanel.sync_hook is None or self._heal_scheduled:
            return
        self._heal_scheduled = True
        timer_proc(TIMER_START_ONE, self._do_heal, self.HEAL_MS)

    def _do_heal(self, tag='', info=''):
        self._heal_scheduled = False
        if LspPanel.sync_hook is not None:
            LspPanel.sync_hook()

    # -- rendering ---------------------------------------------------------------

    @property
    def colors(self):
        if self._colors is None:
            self._colors = app_proc(PROC_THEME_UI_DICT_GET, '')
        return self._colors

    def _context_lists(self):
        """ Model lists of the current context, each pre-sorted by seq. """
        st = self.store
        if st is None:
            return []
        if self.uri is None:
            # pinned instance (manual pick): everything of this ONE instance
            return [st.srv_msgs, *st.file_spy.values(), *st.file_diags.values()]
        return [st.srv_msgs,
                st.file_spy.get(self.uri, ()),
                st.file_diags.get(self.uri, ())]

    def _context_msgs(self):
        lists = self._context_lists()
        if not lists:
            return []
        if len(lists) == 1:
            return lists[0]
        return heapq.merge(*lists, key=itemgetter(0))

    def _filter_ok(self, msg):
        return (msg.type not in self._disabled_items
                and msg.severity not in self._disabled_items)

    def _render_full(self):
        self._need_full = False
        self._evictions = 0
        # the whole model is rendered now - a queued remainder is included
        # in it; anything still pending would be appended TWICE
        self._pending.clear()

        # terminal behaviour: scroll to the end only if the memo WAS at its
        # bottom before the re-render (the user scrolled up to read history -
        # keep the position!), or right after a context switch (a different
        # file's log: its end = the latest messages). Queried BEFORE any
        # memo mutation.
        follow = self._ctx_follow or self._at_bottom()
        self._ctx_follow = False

        counts = {}
        diag_sevs = {}   # severity str -> count, TYPE_DIAG messages only
        visible = []
        for m in self._context_msgs():
            counts[m.type] = counts.get(m.type, 0) + 1
            counts[m.severity] = counts.get(m.severity, 0) + 1
            if m.type == TYPE_DIAG:
                diag_sevs[m.severity] = diag_sevs.get(m.severity, 0) + 1
            if self._filter_ok(m):
                visible.append(m)
        self._counts = counts
        self._diag_sevs = diag_sevs

        if visible:
            self._placeholder = False
            self._memo.set_text_all(''.join(m.text for m in visible))
            self._memo.decor(DECOR_DELETE_BY_TAG, tag=self._decor_tag)
            start = 0
            for m in visible:
                self._memo.decor(DECOR_SET, line=start,
                                 image=self._severity_ims[m.severity],
                                 tag=self._decor_tag)
                start += m.text.count('\n')
        else:
            self._render_placeholder()

        self._fix_memo_after_render()
        if follow:
            self._goto_end()

    def _render_progress(self):
        """ The background-analysis progress page - what the user asked for
        the big-workspace flood: 'the analysis is running, wait' WITH the
        numbers (VS Code shows the same in its status bar), instead of
        rendering thousands of messages nobody reads. Everything the page
        shows is O(1) to compute: the analysis dict's counters, the elapsed
        clock, the last few KEPT server-level texts (an at-most-4 tail). """
        st = self.store
        an = st.analysis
        self._need_full = False
        self._evictions = 0
        # the whole model is rendered by the full re-render which
        # analysis_finish() schedules; anything still pending is included
        # in the model - dropping it here is what keeps this path O(1)
        self._pending.clear()
        self._placeholder = False

        total = an['total']
        done = max(total - an['remaining'], 0)
        pct = (100 * done // total) if total else 0
        secs = int((time.monotonic() * 1000 - an['started_ms']) / 1000)

        lines = [
            _('Background analysis is running - the log view is paused '
              'until it finishes'),
            '',
            f"{_('Instance')}: {st.display_name}",
        ]
        if an.get('sweep'):
            lines.append(
                f"{_('Progress')}: {done}/{total} {_('file(s)')} ({pct}%), "
                f"{an['projects']} {_('project(s)')}, "
                f"{_('elapsed')} {secs // 60:02d}:{secs % 60:02d}")
        else:
            # loading phase: no sweep numbers yet, projects are still being
            # loaded (the first o#/projectadded / restore event opened this)
            lines.append(
                f"{_('Loading workspace')}: {an['projects']} "
                f"{_('project(s)')}, "
                f"{_('elapsed')} {secs // 60:02d}:{secs % 60:02d}")
        if an['hidden_total']:
            lines.append(_('Hidden while analyzing') + ': ' +
                         st.analysis_hidden_str())
        lines.append('')
        lines.append(_('Errors, warnings and server events are still '
                       'collected and shown when the analysis finishes; '
                       'progress is also in the status bar, analyzed files '
                       'are listed in the instance picker (click the '
                       'instance cell above).'))
        if an['tail']:
            lines.append('')
            lines.append(_('Recent events:'))
            lines.extend('  ' + t for t in an['tail'])

        self._memo.set_text_all('\n'.join(lines) + '\n')
        self._memo.decor(DECOR_DELETE_BY_TAG, tag=self._decor_tag)
        self._memo.decor(DECOR_SET, line=0,
                         image=self._severity_ims[SEVERITY_INFO],
                         tag=self._decor_tag)

        # truthful cells while the stream is paused: recompute the
        # context's counts from the model (the KEPT messages only - the
        # hidden flood is reported on the page's 'hidden' line, it must
        # not stay in the cells as stale pre-analysis numbers). Includes
        # the Diagnostics cell, LIVE for the focused file: its block is
        # one small list - recomputing it is O(its diagnostics), nothing
        # like the flood. The kept set is small BY DESIGN (the flood is
        # what _hide_in_analysis skips), so this stays cheap per refresh.
        counts = {}
        diag_sevs = {}
        for m in self._context_msgs():
            counts[m.type] = counts.get(m.type, 0) + 1
            counts[m.severity] = counts.get(m.severity, 0) + 1
            if m.type == TYPE_DIAG:
                diag_sevs[m.severity] = diag_sevs.get(m.severity, 0) + 1
        self._counts = counts
        self._diag_sevs = diag_sevs

        self._fix_memo_after_render()

    def _render_placeholder(self):
        self._placeholder = True
        self._memo.decor(DECOR_DELETE_BY_TAG, tag=self._decor_tag)
        if self.store is None:
            text = PLACEHOLDER_NO_SERVER + '\n' + PLACEHOLDER_NO_SERVER_2 + '\n'
        elif self.uri is None:
            text = PLACEHOLDER_NO_MSGS_ALL + '\n'
        else:
            text = PLACEHOLDER_NO_MSGS + '\n'
        self._memo.set_text_all(text)

    def _render_append(self):
        """ Fast path: append only the messages logged since the last render.
        Chronologically correct: every pending message has a higher seq than
        anything already shown (per-store counter), so appending to the memo
        end keeps the order. TYPE_DIAG never arrives here (a diagnostics
        block is REPLACED atomically -> always a full re-render), so
        _diag_sevs needs no update in this path.

        The pending queue is CONSUMED here (self._pending = []): every
        message is rendered exactly ONCE. (Regression: the queue used to
        survive the tick, so every following tick re-appended EVERYTHING
        still queued - with real-app timing, one message batch per tick,
        the view and the cell counts grew QUADRATICALLY between two full
        renders: 'Spy 6000' after a burst of activity, back to the true
        number on every publishDiagnostics, growing again - forever.)
        DISABLED categories are filtered here exactly like in _render_full.
        (Regression: they used to leak back in through this path within one
        tick after the user disabled them.) """
        if self._placeholder:
            # the memo shows a placeholder: it does not mirror the model
            self._render_full()
            return

        msgs = self._pending
        self._pending = []
        follow = self._at_bottom()

        visible = [m for m in msgs if self._filter_ok(m)]
        if visible:
            # all messages end with '\n' -> the last memo line is empty:
            # the insertion point is the START of that (last) line == text
            # end. Decor line starts are computed for the VISIBLE messages
            # only - filtered ones occupy no lines.
            y_ins = self._memo.get_line_count() - 1
            starts = []
            line = y_ins
            for m in visible:
                starts.append(line)
                line += m.text.count('\n')

            self._memo.insert(0, y_ins, ''.join(m.text for m in visible))
            for m, start in zip(visible, starts):
                self._memo.decor(DECOR_SET, line=start,
                                 image=self._severity_ims[m.severity],
                                 tag=self._decor_tag)

        # counts are NOT category-filtered (a disabled category still shows
        # its total): count every consumed message, exactly once
        for m in msgs:
            self._counts[m.type] = self._counts.get(m.type, 0) + 1
            self._counts[m.severity] = self._counts.get(m.severity, 0) + 1

        if visible and follow:
            self._goto_end()

    def _fix_memo_after_render(self):
        # workarounds for CudaText repaint bugs (kept from the old panel):
        # line_top must never exceed line_count-1; re-setting it forces a
        # repaint after removing many lines
        try:
            line_top = int(self._memo.get_prop(PROP_LINE_TOP) or 0)
        except (TypeError, ValueError):
            line_top = 0
        line_cnt = self._memo.get_line_count()
        if line_top >= line_cnt - 1:
            self._memo.set_prop(PROP_LINE_TOP, max(0, line_cnt - 1))
        else:
            self._memo.set_prop(PROP_LINE_TOP, line_top)

    def _at_bottom(self):
        try:
            info = self._memo.get_prop(PROP_SCROLL_VERT_INFO)
            return info['pos'] >= info['pos_last']
        except Exception:
            return True

    def _goto_end(self):
        self._memo.cmd(cmds.cCommand_GotoTextEnd)

    # -- top bar (statusbar) -------------------------------------------------------

    def _theme_color(self, key, fallback):
        """ Color of a UI theme part, with a fallback for exotic themes. """
        try:
            return self.colors[key]['color']
        except (KeyError, TypeError):
            return fallback

    def _update_sb(self):
        """ Rebuild the filter bar (left to right):
            [instance picker] [Diagnostics] [margin] [other category cells]
            [stretch] [severity icons]
        THREE designs, one per kind of cell:
        * instance cell - not a panel but a PICKER: distinct background,
          no state underline (it has no on/off state), fixed width;
        * Diagnostics cell - the heart of the plugin: ALWAYS present (even
          with 0 entries), directly after the picker, separated from the
          other cells by a margin so the eye finds the errors first; amber
          state line + the worst-severity icon of the context (its count is
          always shown, even 'Diagnostics 0');
        * every other category cell - one shared look (green state line
          when enabled).
        Cell texts carry their counts as a trailing number (_update_counts)
        - an overlay used to cover the caption. Called on context change /
        theme change / when the shown store learns a new message type. """
        h_sb = self._h_sb

        bg_color = self.colors['TabActive']['color']
        inst_bg_color = self._theme_color('TabInactive', bg_color)
        font_enabled_color = self.colors['TabFontActive']['color']
        font_disabled_color = self.colors['TabFontMod']['color']
        line_enabled_color = 0x7cc87c

        self._sb_cellind_map.clear()
        statusbar_proc(h_sb, STATUSBAR_DELETE_ALL)
        statusbar_proc(h_sb, STATUSBAR_SET_COLOR_BORDER_R,
                       value=self.colors['TabBorderActive']['color'])

        callbac_fstr = 'module=cuda_lsp.panel;func=_on_sb_click;info="{}";'

        # instance picker (fixed width); a trailing '*' marks a manual pick
        # (pinned: ONLY the picked target is shown - a server pick shows that
        # server and all its files, a file pick shows that file alone -
        # until the next tab switch)
        inst_caption = self.store.display_name if self.store else '-'
        inst_pin = ''
        if self.store is not None and self._picked:
            if self.uri is not None:
                # pinned to ONE file: name it (fixed width truncates the rest)
                path = uri_to_path(self.uri)
                inst_caption += ' / ' + (os.path.basename(path)
                                         if path else self.uri)
            inst_pin = ' *'
        self._inst_caption = inst_caption
        self._inst_pin = inst_pin
        cellind = statusbar_proc(h_sb, STATUSBAR_ADD_CELL, index=-1)
        self._sb_cellind_map[CELL_INSTANCE] = cellind
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_CALLBACK, index=cellind,
                       value=callbac_fstr.format(CELL_INSTANCE))
        if self.store:
            inst_hint = self.store.full_name
            if self._picked:
                if self.uri is None:
                    inst_hint += '\n' + _('Pinned: only this server is shown (all its files); switching a tab follows the focused file again')
                else:
                    inst_hint += '\n' + _("Pinned: only this file is shown (its traffic, its diagnostics, its server's own messages); switching a tab follows the focused file again")
        else:
            inst_hint = _('Server instance (click to pick)')
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_HINT, index=cellind,
                       value=inst_hint)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_ALIGN, index=cellind, value='C')
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_SIZE, index=cellind,
                       value=INSTANCE_CELL_W)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_BACK, index=cellind,
                       value=inst_bg_color)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_FONT, index=cellind,
                       value=font_enabled_color)

        # Diagnostics cell: the heart of the panel - ALWAYS present (even
        # before the server published anything), its own design: amber state
        # line + the context's worst-severity icon (_update_counts); its
        # count is ALWAYS shown ('Diagnostics 0' = no problems known)
        cellind = statusbar_proc(h_sb, STATUSBAR_ADD_CELL, index=-1)
        self._sb_cellind_map[TYPE_DIAG] = cellind
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_CALLBACK, index=cellind,
                       value=callbac_fstr.format(TYPE_DIAG))
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_HINT, index=cellind,
                       value=_('Diagnostics of the focused file (click to show/hide them)'))
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_AUTOSIZE, index=cellind, value=True)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_BACK, index=cellind,
                       value=bg_color)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_FONT, index=cellind,
                       value=font_disabled_color if TYPE_DIAG in self._disabled_items
                       else font_enabled_color)
        if TYPE_DIAG not in self._disabled_items:
            statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_LINE2, index=cellind,
                           value=DIAG_LINE_COLOR)

        # margin: separates the Diagnostics cell from the SECONDARY panels -
        # not a filter, not in _sb_cellind_map (inert, just background)
        cellind = statusbar_proc(h_sb, STATUSBAR_ADD_CELL, index=-1)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_SIZE, index=cellind,
                       value=MARGIN_CELL_W)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_BACK, index=cellind,
                       value=bg_color)

        # other category cells of the shown store (one shared design);
        # their texts (with the trailing counts) are set by _update_counts
        extra = self.store.extra_types if self.store else set()
        for name in [TYPE_MSG, TYPE_LOG, *sorted(extra - {TYPE_MSG, TYPE_LOG, TYPE_DIAG})]:
            cellind = statusbar_proc(h_sb, STATUSBAR_ADD_CELL, index=-1)
            self._sb_cellind_map[name] = cellind

            statusbar_proc(h_sb, STATUSBAR_SET_CELL_CALLBACK, index=cellind,
                           value=callbac_fstr.format(name))

            if name not in self._disabled_items:
                statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_LINE2, index=cellind,
                               value=line_enabled_color)
            statusbar_proc(h_sb, STATUSBAR_SET_CELL_AUTOSIZE, index=cellind, value=True)
            statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_BACK, index=cellind,
                           value=bg_color)
            statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_FONT, index=cellind,
                           value=font_disabled_color if name in self._disabled_items
                           else font_enabled_color)

        # spacer
        cellind = statusbar_proc(h_sb, STATUSBAR_ADD_CELL, index=-1)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_AUTOSTRETCH, index=cellind, value=True)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_BACK, index=cellind, value=bg_color)

        # severity filters
        for name in SEVERITYS:
            cellind = statusbar_proc(h_sb, STATUSBAR_ADD_CELL, index=-1)
            self._sb_cellind_map[name] = cellind

            statusbar_proc(h_sb, STATUSBAR_SET_CELL_IMAGEINDEX, index=cellind,
                           value=self._severity_ims[name])
            statusbar_proc(h_sb, STATUSBAR_SET_CELL_CALLBACK, index=cellind,
                           value=callbac_fstr.format(name))
            statusbar_proc(h_sb, STATUSBAR_SET_CELL_HINT, index=cellind,
                           value=PANEL_CAPTIONS.get(name, 'NA'))
            statusbar_proc(h_sb, STATUSBAR_SET_CELL_ALIGN, index=cellind, value='C')
            if name not in self._disabled_items:
                statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_LINE2, index=cellind,
                               value=line_enabled_color)
            statusbar_proc(h_sb, STATUSBAR_SET_CELL_AUTOSIZE, index=cellind, value=True)
            statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_BACK, index=cellind,
                           value=bg_color)

        self._update_counts()

    def _update_counts(self):
        """ Counts on the cells - appended to the END of the cell text (an
        overlay used to cover the caption when the number grew long).
        Counts come from the last render pass (context messages, NOT
        category-filtered: a disabled category still shows its total).
        * Diagnostics cell: ALWAYS numbered, even 'Diagnostics 0', and its
          icon shows the worst diagnostic severity of the context
          (error > warning > info > log; grey = none);
        * other category cells: 'name N' while N > 0, plain caption else;
        * severity icon cells: icon-only, the number stays an overlay
          (nothing to cover there);
        * instance cell: its caption + ' [N]' only when several instances
          run (the number carries no information otherwise). """
        counts = self._counts
        for name, cellind in self._sb_cellind_map.items():
            n = counts.get(name, 0)
            if name == CELL_INSTANCE:
                continue
            if name in SEVERITYS:
                statusbar_proc(self._h_sb, STATUSBAR_SET_CELL_OVERLAY,
                               index=cellind, value=str(n) if n else '')
            elif name == TYPE_DIAG:
                statusbar_proc(self._h_sb, STATUSBAR_SET_CELL_TEXT,
                               index=cellind,
                               value=f"{PANEL_CAPTIONS.get(name, name)} {n}")
                worst = next((s for s in (SEVERITY_ERR, SEVERITY_WRN,
                                          SEVERITY_INFO, SEVERITY_LOG)
                              if self._diag_sevs.get(s)), None)
                statusbar_proc(self._h_sb, STATUSBAR_SET_CELL_IMAGEINDEX,
                               index=cellind,
                               value=self._severity_ims.get(worst,
                                   self._severity_ims[SEVERITY_NA]))
            else:
                cap = PANEL_CAPTIONS.get(name, name)
                statusbar_proc(self._h_sb, STATUSBAR_SET_CELL_TEXT,
                               index=cellind,
                               value=f"{cap} {n}" if n else cap)

        # instance cell: caption (set by _update_sb) + live ' [N]' + pin '*'
        cellind = self._sb_cellind_map.get(CELL_INSTANCE)
        if cellind is not None:
            n = len(self.stores)
            value = self._inst_caption
            if n > 1:
                value += f" [{n}]"
            value += self._inst_pin
            statusbar_proc(self._h_sb, STATUSBAR_SET_CELL_TEXT,
                           index=cellind, value=value)

    def _update_badge(self):
        """ Overlay on the bottom-panel button: total messages of ALL
        instances - "the panel has something" without activating it. """
        if self._h_btn_sidebar:
            n = sum(store.total_msgs() for store in self.stores)
            button_proc(self._h_btn_sidebar, BTN_SET_OVERLAY,
                        str(n) if n > 0 else '')

    # -- interactions ----------------------------------------------------------------

    def on_show(self, *args, **vargs):
        # the page became visible: catch up deferred renders (hidden periods
        # skip UI work). Does NOT force-scroll: if the user had scrolled up
        # before hiding the page, the position survives the catch-up.
        self._need_full = True
        self._pending.clear()
        self._schedule()
        # re-derive the CONTEXT too (coalesced): the ACTIVE tab may have
        # changed while the page was hidden without any focus event
        # (project-manager open) - the previous render could still be a
        # stale placeholder. A manual picker pin still wins (sync_panel
        # returns early while picked). This is the recovery path that
        # made 'close the panel and reopen it' work around the bug.
        self._request_heal()

    def on_cell_click(self, info):
        if info == CELL_INSTANCE:
            self._pick_instance()
            return

        # toggle a category / severity filter
        if info in self._disabled_items:
            self._disabled_items.remove(info)
        else:
            self._disabled_items.add(info)

        self._need_full = True
        self._pending.clear()
        self._update_sb()
        self._schedule()

    def _file_captions(self, uris):
        """ Picker captions of one instance's files: the basename, with the
        parent dir prefixed when the instance has two files with the same
        basename (they must stay distinguishable). """
        paths = [uri_to_path(u) for u in uris]
        caps = [os.path.basename(p) if p else u for u, p in zip(uris, paths)]
        cnt = {}
        for c in caps:
            cnt[c] = cnt.get(c, 0) + 1
        out = []
        for p, cap in zip(paths, caps):
            if cnt[cap] > 1 and p:
                out.append(os.path.basename(os.path.dirname(p)) + os.sep + cap)
            else:
                out.append(cap)
        return out

    def _pick_instance(self):
        """ Dropdown of ALL running instances (all servers), their files
        NESTED under them (indented - they visibly belong to their server).
        Picking a SERVER pins the panel to that ONE instance: ONLY its logs
        are shown - its server-level messages plus all its files; logs of
        other servers are never mixed in. Picking a FILE pins it to that
        file ONLY: its spy traffic + diagnostics block + its server's own
        messages. Any pin dies on the next tab switch; '(follow focused
        tab)' cancels it immediately. """
        if not self.stores:
            return

        names = ['(' + _('follow focused tab') + ')']
        entries = [None]                 # menu index -> (store, uri) | None
        focused = 0
        for store in self.stores:
            if store is self.store:
                focused = len(names)     # the shown instance's server row
            names.append(store.display_name)
            entries.append((store, None))
            uris = store.log_files()
            for uri, cap, n in zip(uris, self._file_captions(uris),
                                   (store.file_msg_count(u) for u in uris)):
                # per-file message total next to the name: the file's
                # activity is visible WITHOUT opening/rendering its log
                # ('file.cs [12]' - 12 kept messages of that file)
                names.append(f'    {cap}  [{n}]')
                entries.append((store, uri))

        ind = dlg_menu(DMENU_LIST_ALT, names,
                       caption=_('Server instances'), focused=focused)
        if ind is None:
            return
        if entries[ind] is None:
            self._picked = False
            self._request_heal()   # re-derive the context from the focused tab
            return

        store, uri = entries[ind]
        # picking the target already shown still pins it (per-file follow
        # -> a pick of the same server must stick like any other pick)
        self._picked = True
        self.set_context(store, uri)   # uri None: whole instance; else file
        self._update_sb()   # the '*' pin marker also when the context is unchanged

    def memo_on_click_dbl(self, id_dlg, id_ctl, data='', info=''):
        """ Double-click a 'Line N: ... (x-y)' diagnostics entry: jump to the
        file and put the caret at the range START column (x) of that line -
        column 0 for entries without a column suffix. The filename comes
        from the store's cache, with a fallback scan of the shown text
        ('File: ' lines). """
        y = self._memo.get_carets()[0][1]

        fn = None
        if self.store is not None and self.uri is not None:
            fn = self.store.diag_filenames.get(self.uri)
        if not fn:
            lines = self._memo.get_text_all().splitlines()
            for i in reversed(range(min(y, len(lines)))):
                line_txt = lines[i]
                if line_txt.startswith('File: '):
                    fn = line_txt[6:]
                    break
        if not fn:
            return

        text = self._memo.get_text_line(y)
        if not text.startswith('Line '):
            return
        n = text.find(': ')
        if n < 0:
            return
        try:
            line = int(text[5:n]) - 1
        except ValueError:
            return
        m = _RE_DIAG_RANGE.search(text)
        if m is not None:
            if m.group(2) is not None:   # multi-line '(130:21-144:34)':
                line = int(m.group(1))   # the start LINE is in the suffix too
                col = int(m.group(2))
            else:                       # '(21)' / '(21-22)': char only
                col = int(m.group(1))
        else:
            col = 0
        file_open(fn)
        ed.set_caret(col, line)
        ed.focus()

    def toggle_wrap(self):
        self._is_wrap = not self._is_wrap
        self._set_memo_wrap(self._is_wrap)

    def _set_memo_wrap(self, is_wrap):
        self._memo.set_prop(PROP_WRAP,
                            WRAP_ON_WINDOW if is_wrap else WRAP_OFF)

    def clear(self):
        """ User 'Clear' (context menu): drop everything of the shown store. """
        if self.store is not None:
            self.store.clear()

    # -- context menu of the log view -------------------------------------------------

    TAG_ED_MENU_WRAP = 'ed_wrap'

    def _get_ed_menu(self):
        if self._h_ed_menu is None:
            self._h_ed_menu = menu_proc(0, MENU_CREATE)
            h_menu = self._h_ed_menu

            _la_copy =       lambda *a, **k: self._memo.cmd(cmds.cCommand_ClipboardCopy)
            _la_select_all = lambda *a, **k: self._memo.cmd(cmds.cCommand_SelectAll)
            _la_wrap =       lambda *a, **k: self.toggle_wrap()
            _la_clear =      lambda *a, **k: self.clear()

            menu_proc(h_menu, MENU_ADD, command=_la_copy, caption=_('Copy'))
            menu_proc(h_menu, MENU_ADD, command=_la_select_all, caption=_('Select all'))
            menu_proc(h_menu, MENU_ADD, caption='-')
            menu_proc(h_menu, MENU_ADD, command=_la_wrap, caption=_('Toggle word wrap'),
                      tag=self.TAG_ED_MENU_WRAP)
            menu_proc(h_menu, MENU_ADD, caption='-')
            menu_proc(h_menu, MENU_ADD, command=_la_clear, caption=_('Clear'))
        return self._h_ed_menu

    def on_ed_menu(self, id_dlg, id_ctl, data='', info=''):
        h_menu = self._get_ed_menu()
        for item in menu_proc(h_menu, MENU_ENUM):
            if item.get('tag') == self.TAG_ED_MENU_WRAP:
                menu_proc(item['id'], MENU_SET_CHECKED, command=self._is_wrap)
                break
        menu_proc(h_menu, MENU_SHOW)
        return False

    # -- state / theme ---------------------------------------------------------------

    def get_state(self):
        return {
            'log_panel_filter': sorted(self._disabled_items),
            'is_wrap': self._is_wrap,
        }

    @classmethod
    def on_theme_change(cls):
        panel = cls._instance
        if panel is None:
            return
        import cudatext as ct

        colors = app_proc(PROC_THEME_UI_DICT_GET, '')
        panel._colors = colors
        panel._update_sb()

        for name, val in vars(ct).items():
            if name.startswith('COLOR_ID_') and type(val) == str:
                theme_item = colors.get(val)
                if theme_item is not None:
                    panel._memo.set_prop(PROP_COLOR, (val, theme_item['color']))


# ---------------------------------------------------------------------------
# module API
# ---------------------------------------------------------------------------

_pending_state = None
def set_pending_state(state):
    """ Panel filter/wrap state loaded from cuda_lsp_state.json (key
    'panel') - consumed when the panel gets created. """
    global _pending_state
    _pending_state = state


def _on_sb_click(id_dlg, id_ctl, data='', info=''):
    """ Statusbar cell callback (string-dispatched by CudaText). """
    panel = LspPanel.get(create=False)
    if panel is not None:
        panel.on_cell_click(info)


def _notify_msg(store, msg, uri, evicted, new_type):
    panel = LspPanel.get(create=False)
    if panel is not None:
        panel._on_store_msg(store, msg, uri, evicted, new_type)


def _notify_change(store, uri):
    panel = LspPanel.get(create=False)
    if panel is not None:
        panel._on_store_change(store, uri)


def _notify_tick():
    """ Schedule the panel's coalesced render tick without touching any
    model/view state - used by LogStore.analysis_note_hidden so that a
    flood of HIDDEN messages still keeps the tick (and with it the
    quiet-mode staleness valve) running. """
    panel = LspPanel.get(create=False)
    if panel is not None:
        panel._schedule()


def _unregister(store):
    panel = LspPanel.get(create=False)
    if panel is not None:
        panel._unregister(store)


def make_store(display_name, full_name=None):
    """ Create the LogStore of one server instance and register it in the
    single panel (created here if this is the first server). """
    store = LogStore(display_name, full_name)
    LspPanel.get(True).register(store)
    return store


def panel_exists():
    return LspPanel._instance is not None
