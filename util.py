import os
import pathlib
import re

import cudatext as ct
import cudax_lib as appx

from .dlg import Hint

USER_DIR = os.path.expanduser('~')

def get_first(gen):
    try:
        #if notnone:
            #for val in gen:
                #if val is not None:
                    #return val
        #else:
        return next(gen)
    except StopIteration:
        pass
    return None

def lex2langid(lex):
    return lex_ids.get(lex)

def langid2lex(langid_):
    for name,langid in lex_ids.items():
        if langid == langid_:
            return name

def is_ed_visible(ed):
    gr_ed = ct.ed_group(ed.get_prop(ct.PROP_INDEX_GROUP))
    return ed == gr_ed

def get_visible_eds():
    for i in range(8):
        ed = ct.ed_group(i)
        if ed:
            yield ed

def replace_on_right():
    lex = ct.ed.get_prop(ct.PROP_LEXER_FILE, '')
    r = appx.get_opt(
        'autocomplete_replace_on_right',
        True,
        appx.CONFIG_LEV_ALL,
        ct.ed,
        lex)
    return r
    
def get_word(x, y):
    ed = ct.ed
    if not 0<=y<ed.get_line_count():
        return
    s = ed.get_text_line(y)
    if not 0<=x<=len(s):
        return

    x0 = x
    while (x0>0) and _isword(s[x0-1]):
        x0-=1
    text1 = s[x0:x]

    x0 = x
    while (x0<len(s)) and _isword(s[x0]):
        x0+=1
    text2 = s[x:x0]

    if not replace_on_right():
        text2 = ''

    return (text1, text2)

def get_nonwords_chars():
    ed = ct.ed
    lex = ed.get_prop(ct.PROP_LEXER_FILE, '')
    _nonwords = appx.get_opt(
        'nonword_chars',
        r'''-+*=/\()[]{}<>"'.,:;~?!@#$%^&|`…''',
        appx.CONFIG_LEV_ALL,
        ed,
        lex)
    return _nonwords

def _isword(s):
    nonwords = get_nonwords_chars()
     
    return s not in ' \t'+nonwords


def path_to_uri(path):
    """ Canonical file uri of a path - THE form used everywhere in the
    plugin (didOpen/didChange params, per-file log keys, editor-doc uris):
    the minimal-encoding form of canonical_uri() - what VS Code clients
    send, the de-facto interop standard LSP servers are tested against
    (pathlib's as_uri over-encodes: '+' as '%2B', ':' as '%3A' - jdt.ls
    answers those with a DIFFERENTLY spelled uri, see canonical_uri). """
    return canonical_uri(pathlib.Path(path).as_uri())

# untitled-tab uri dedupe: tab handle -> [title, assigned uri]. Two
# unsaved tabs can carry the SAME title (session restore, split views,
# plugin-made tabs): they must never share one LSP document identity -
# DocBook is keyed by uri, so the second new_doc() would silently
# OVERWRITE the first tab's doc, and _get_doc()'s uri fallback would
# cross-match the sibling tabs. The '~2', '~3' suffix keeps the uris
# distinct; records are keyed by tab handle (stable for the tab's
# lifetime) and re-validated against the title on every call (a handle
# reused after an untracked close must not inherit a stale uri).
_UNTITLED_URIS = {}

def ed_uri(ed):
    fn = ed.get_filename('*') # '*' get filepath for image/binary tabs too
    if fn:
        #return 'file://'+ed.get_filename()
        return path_to_uri(fn)
    # unsaved tab: 'file:///<tab title>' names no real file - percent-
    # encoded by canonical_uri, and DEDUPED here (see _UNTITLED_URIS)
    title = (ed.get_prop(ct.PROP_TAB_TITLE) or '?').lstrip('*')
    h = ed.get_prop(ct.PROP_HANDLE_SELF)
    rec = _UNTITLED_URIS.get(h)
    if rec is not None and rec[0] == title:
        return rec[1]
    uri = canonical_uri('file:///' + title)
    taken = {u for _t, u in _UNTITLED_URIS.values()}
    n = 2
    while uri in taken:
        uri = canonical_uri('file:///{}~{}'.format(title, n))
        n += 1
    _UNTITLED_URIS[h] = (title, uri)
    return uri

def forget_ed_uri(ed):
    """ The tab closed: drop its untitled-uri dedupe record (real files
    never enter the map). Called by DocBook.on_close; a tab closed without
    ever becoming an LSP document leaves a stale record at most - harmless,
    the title check on lookup never matches a different title. """
    try:
        _UNTITLED_URIS.pop(ed.get_prop(ct.PROP_HANDLE_SELF), None)
    except Exception:
        pass

def uri_to_path(uri):

    # https://stackoverflow.com/a/61922504
    # ~heavy import
    from urllib.parse import urlparse
    from urllib.request import url2pathname

    # NOTE: url2pathname() percent-decodes by itself (on posix it IS
    # unquote, on nt it unquotes each component) - an extra unquote() here
    # would decode TWICE and corrupt names with a literal '%' (file
    # 'a%20b.java' -> uri 'a%2520b.java' -> path 'a b.java').
    path = urlparse(uri).path
    return url2pathname(path)

def collapse_path(path):
    if path  and  (path + os.sep).startswith(USER_DIR + os.sep):
        path = path.replace(USER_DIR, '~', 1)
    return path
    
def normalize_drive_letter(uri, is_win=None):
    """ Canonical form of a file uri (see path_to_uri): upper-case the
    Windows drive letter, because Windows drive letters are case-insensitive
    and .NET servers (OmniSharp) lower-case them in echoed uris. No-op on
    other systems (paths are case-sensitive there - '/a:b' must not be
    touched); 'is_win' overrides the OS check for tests. """
    if is_win is None:
        is_win = os.name == 'nt'
    if not is_win or not isinstance(uri, str):
        return uri
    parts = uri.split("file:///")
    if len(parts) == 2 and parts[0] == '' and len(parts[1]) >= 2 and parts[1][1] == ':':
        uri = "file:///" + parts[1][:1].upper() + parts[1][1:]
    return uri

# RFC 3986 path characters which never need percent-encoding in the path of
# a file uri ('pchar' minus '%', plus '/'): unreserved + sub-delims +
# ':' + '@' - the minimal-encoding set VS Code clients use.
_URI_PATH_SAFE = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    "/-._~!$&'()*+,;=:@"
)

def canonical_uri(uri, is_win=None):
    """ ONE canonical spelling of a document uri, so the same file NEVER
    gets two per-file keys in the panel/log model.

    Servers do not agree on how much of a path to percent-encode, and the
    plugin itself over-encodes (pathlib: '+' -> '%2B', ':' -> '%3A'). A
    didOpen of '+lexers/__individual files/java.java' goes out as
    '.../%2Blexers/__individual%20files/java.java' while jdt.ls answers
    with '.../+lexers/__individual%20files/java.java' (Java keeps '+'
    literal) - the file's spy traffic is then stored under one key and its
    publishDiagnostics under ANOTHER: the instance picker lists the file
    TWICE, and the file's panel shows no diagnostics (the block lives under
    the other key). .NET servers additionally lower-case the drive letter,
    older ones send 'file:/' with one slash.

    The canonical form is the minimal-encoding one: percent-escapes of
    path-safe characters are decoded to the literal char, everything else
    is (re-)encoded as an uppercase-hex UTF-8 escape, the Windows drive
    letter is upper-cased, and the slash count after 'file:' is folded to
    exactly three (a 2-slash uri with a non-drive authority - UNC
    'file://server/share' - is left untouched, as are non-file uris like
    jdt.ls's 'jdt:contents://...': they name no file on disk).
    Idempotent; 'is_win' overrides the OS check for tests. """
    if not isinstance(uri, str) or not uri:
        return uri
    if is_win is None:
        is_win = os.name == 'nt'

    rest = None
    if uri.startswith('file:///'):
        rest = uri[len('file:///'):]
    elif uri.startswith('file://'):
        head = uri[len('file://'):]
        if len(head) >= 2 and head[1] == ':' and head[0].isalpha():
            rest = head                # 'file://F:/x' - drive read as path
    elif uri.startswith('file:/'):
        rest = uri[len('file:/'):]     # 'file:/F:/x', 'file:/home/x'
    if rest is None:
        return normalize_drive_letter(uri, is_win=is_win)

    from urllib.parse import unquote_to_bytes, quote
    text = unquote_to_bytes(rest).decode('utf-8', 'surrogateescape')
    if is_win and len(text) >= 2 and text[1] == ':' and text[0].isalpha():
        text = text[0].upper() + text[1:]
    return 'file:///' + quote(text, safe=_URI_PATH_SAFE,
                              errors='surrogateescape')

def command(f):
    def d(*args, **vargs): #SKIP
        if Hint.is_visible():
            Hint.hide()
        return f(*args, **vargs)
    return d

class ValidationError(Exception):
    pass

def replace_unbracketed(s, target_char, repl, brackets):
    depth = 0
    start_char = None
    end_char = None
    result = ''
    for c in s:
        if c in brackets:
            if depth == 0:
                start_char = c
                end_char = brackets[start_char]
                depth += 1
            elif c == start_char:
                    depth += 1

        elif c == end_char:
            depth -= 1
            if depth == 0:
                start_char = None
                end_char = None

        elif depth == 0  and  c == target_char:
            c = repl

        result += c
    return result

def split_text_by_length(text, max_length, prepare_for_corner=False):
    lines_out = []
    for line in text.split('\n'):
        if prepare_for_corner:
            line = re.sub(r"^\[.*?Err.*?\]:\s*" , "⛔️ ", line) 
            line = re.sub(r"^\[.*?Wrn.*?\]:\s*" , "⚠️ ", line) 
            line = re.sub(r"^\[.*?Inf.*?\]:\s*" , "ℹ️ ", line) 
            line = re.sub(r"^\[.*?Hint.*?\]:\s*", "📜️ ", line) 
        words = line.split()
        parts = []
        current_part = ''
        for word in words:
            if len(current_part) + len(word) <= max_length:
                if current_part:
                    current_part += ' ' + word
                else:
                    current_part = word
            else:
                parts.append(current_part)
                current_part = word
        if current_part:
            parts.append(current_part)
        lines_out.extend(parts)
    return '\n'.join(lines_out)


class TimerScheduler:
    """ orchestrates growing timer telta
        `restart()` - restarts timer from `mintime`, and grows timer period by
            accumulating `delta` between calls
        NOTE: weakref because timer keeps references
    """

    def __init__(self, callback, mintime=10, maxtime=250, delta=10):
        """ default: len==24;  t:10, 30, 60, 100, 150, ... 2100, 2310, 2530, 2760
        """
        import weakref

        self._callback_wr   = weakref.ref(callback)

        self._mintime       = mintime
        self._maxtime       = maxtime
        self._delta         = delta

        self._last_period = 0

    def timer_callback(self, tag='', info=''):
        callback = self._callback_wr()

        if callback is not None:
            callback(tag, info)

            if self._last_period < self._maxtime:
                self._last_period = min(self._maxtime, self._last_period + self._delta)
                ct.timer_proc(ct.TIMER_START, self.timer_callback, self._last_period)

        else:
            ct.timer_proc(ct.TIMER_STOP, self.timer_callback, 0)

    def restart(self):
        self._last_period = self._mintime
        ct.timer_proc(ct.TIMER_START, self.timer_callback, self._last_period)

    def stop(self):
        ct.timer_proc(ct.TIMER_STOP, self.timer_callback, 0)


def update_lexmap(upd):
    lex_ids.update(upd)

# https://microsoft.github.io/language-server-protocol/specifications/specification-current/#-textdocumentitem-
lex_ids = {
    'ABAP': 'abap',
    'Batch files': 'bat', # spec: 'Windows Bat'
    'BibTeX': 'bibtex',
    'Clojure': 'clojure',
    'CoffeeScript': 'coffeescript', # spec: 'Coffeescript'
    'C': 'c',
    'C++': 'cpp',
    'C#': 'csharp',
    'CSS': 'css',
    'Diff': 'diff',
    'Dart': 'dart',
    'Dockerfile': 'dockerfile',
    'Elixir': 'elixir',
    'Erlang': 'erlang',
    'F#': 'fsharp',
    #'Git': 'git-commit and git-rebase', #TODO
    'Go': 'go',
    'Groovy': 'groovy',
    'HTML Handlebars': 'handlebars', # spec: 'Handlebars'
    'HTML': 'html',
    'Ini files': 'ini', # spec: 'Ini'
    'Java': 'java',
    'JavaScript': 'javascript',
    #'JavaScript React': 'javascriptreact', # Not in CudaText
    'JSON': 'json',
    'LaTeX': 'latex',
    'LESS': 'less', # spec: 'Less'
    'Lua': 'lua',
    'Makefile': 'makefile',
    'Markdown': 'markdown',
    'Objective-C': 'objective-c',
    #'Objective-C++': 'objective-cpp', # Not in CudaText
    'Perl': 'perl',
    #'Perl 6': 'perl6', # Not in CudaText
    'PHP': 'php',
    'PowerShell': 'powershell', # spec: 'Powershell'
    'Pug': 'jade',
    'Python': 'python',
    'R': 'r',
    'Razor': 'razor', # spec: 'Razor (cshtml)'
    'Ruby': 'ruby',
    'Rust': 'rust',
    #'SCSS': 'scss (syntax using curly brackets), sass (indented syntax)', #TODO
    'Scala': 'scala',
    #'ShaderLab': 'shaderlab', # not in CudaText
    'Bash script': 'shellscript', # spec: 'Shell Script (Bash)'
    'SQL': 'sql',
    'Swift': 'swift',
    'TypeScript': 'typescript',
    #'TypeScript React': 'typescriptreact', # Not in CudaText
    #'TeX': 'tex', # Not in CudaText
    #'Visual Basic': 'vb', # Not in CudaText
    'XML': 'xml',
    'XSLT': 'xsl', # spec: 'XSL'
    'YAML': 'yaml',
}
