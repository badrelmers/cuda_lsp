Plugin for CudaText.
Adds support for Language Server Protocol (LSP) servers.
For each language server needs to be installed separately.

For each LSP server, add config to the folder "settings" (folder of user.json CudaText config).
Config file must be named lsp_*.json ("lsp_" prefix and ".json" suffix).
See Wiki information about many ready configurations:
https://wiki.freepascal.org/CudaText_plugins

"Hover" dialog feature: dialog appears when you stop moving the mouse cursor, over some
identifier, with Ctrl-key pressed (on macOS: with Command-key).
"Hover" dialog gives several buttons to call other features of LSP:
* Definition
* References
* Implementation
* Declaration
* Type definition
All these features can also be called from menu "Plugins / LSP Client" or from editor's
Command Palette (menu "Help / Command palette").


Dependencies (Python modules)
-----------------------------

Dependencies on Windows.

Plugin needs pure-Python modules "lsprotocol", "attrs", "cattrs" (plus their
dependencies "typing_extensions" and "exceptiongroup").
They are preinstalled in the plugin's subfolder "py\cuda_lsp\lsp_modules" and
work with any Python from 3.8 to 3.14+, so no additional downloads are needed.
(Replaces the former "pydantic" dependency, which needed a compiled
"pydantic_core" binary per Python version.)

Dependencies on Linux and Unix-like OS.

Plugin needs additional Python modules installed into OS Python:
- lsprotocol
- attrs
- cattrs
- wcmatch
- bracex

Typical installation from terminal is:
$ pip install lsprotocol attrs cattrs
$ pip install wcmatch bracex


Example for Python
------------------
Python LSP server can be installed in the Linux by command:
$ pip3 install python-language-server
It creates the script "~/.local/bin/pyls". Basic config would look like this:

  {
    "lexers": {
        "Python": "python"
    },
    "cmd_unix": ["~/.local/bin/pyls"]
  }


Server common options
---------------------
Plugin supports 3 keys for running commands:
- "cmd_windows" for Windows,
- "cmd_macos" for macOS,
- "cmd_unix" for all other OS.

Each cmd-key must be a list of strings, e.g.
  "cmd_windows": ["C:\\Python_folder\\pyls.exe", "--param", "param"],

The config key "lexers" contains mapping between CudaText lexer names and LSP language names.
For example, while CudaText lexer name is "C#", LSP language name is "csharp", so you need
  "lexers": {
     "C#": "csharp"
  }
This mapping is needed also when you have some renamed/changed lexer, e.g. "MyPython".
Some list of LSP language names can be seen here:
https://microsoft.github.io/language-server-protocol/specifications/specification-current/#-textdocumentitem-

Allows to fill code-tree from LSP server:
  "enable_code_tree": true

Which document symbols to show in the code-tree, can be configured with a comma-separated
list of symbol kinds:
  "tree_types_show": "file,module,namespace,package,class,method,property,field,constructor,enum,interface,function,variable,constant,string,number,boolean,array,object,key,null,enummember,struct,event,operator,typeparameter" 
Default value is: "namespace,class,method,constructor,interface,function,struct"

Reformat the document on every file-saving (off by default). Server needs to support document
formatting.
  "format_on_save": true

Log 'stderr' of server's process to log-panel (off by default):
  "log_stderr": true

Working directory for the server's process; it is also sent to the server as the
workspace root (rootUri) in 'initialize', and the server process is started in
that directory. Project-aware servers (OmniSharp, clangd...) discover projects
from that folder: without it the server picks its own location, and files
outside every loaded project only get limited diagnostics (e.g. OmniSharp gives
syntax-only diagnostics for such "misc" files):
  "work_dir": "C:\\path\\to\\project_or_solution"

Note: a much more convenient alternative is CudaText's built-in Project Manager
(plugins are shipped together with CudaText). Opening a project there does the
same thing - actually more: every folder node of the project tree is sent to
the LSP server as a "workspace folder" (LSP multi-root workspace), and the
folder containing the currently opened file is used as rootUri/working
directory. So the project's folders can even live in different places on disk,
and the server is told about all of them. When you open or close a project, or
switch between projects, running servers adapt: servers which support folder
change notifications get them live, others are restarted with the new root.
In short: 'work_dir' is useful only when you don't use the Project Manager,
e.g. when all your projects live inside one big folder and you want a fixed
root for the server regardless of the opened file.

Force "single-root" handling for a server (per-folder instances):
  "single_root": true
Single-root servers read only rootUri from 'initialize' and ignore workspace
folders entirely (OmniSharp: it requires a single root at startup and has no
handler for folder-change notifications - see OmniSharp/omnisharp-roslyn#909;
it even ADVERTISES workspaceFolders support in its capabilities while silently
dropping the notification). For such servers the plugin uses the method of
VS Code's multi-root samples: ONE SERVER INSTANCE PER project folder, and each
file is served by the instance of the folder containing it. Files under no
project folder share one fallback instance over all folders (like before the
multi-root support). When a folder is removed from the project, its instance
is shut down; when a folder is added, its instance starts on the first file
opened from that folder. OmniSharp needs no config: it is auto-detected from
its command line ('omnisharp' in it) and from its serverInfo after
initialization.

Re-send the full document text as a single 'textDocument/didChange' after
'textDocument/didOpen'. Modes:
  "resync_after_open": "auto"   (default, new smart behavior)
  "resync_after_open": true     (always, immediately - old blind behavior)
  "resync_after_open": false    (never)
'auto' sends the re-sync only to servers known to DISCARD the didOpen buffer
for documents they don't know yet (OmniSharp up to v1.39.x: out-of-project
"misc" files get no diagnostics until a full-text didChange/didSave registers
them) - and only when the server did NOT prove it processed the didOpen: a
publishDiagnostics for the file (even with 0 entries) or any didChange/
didSave-with-text cancels it. Nothing proved within the delay (server config
"resync_after_open_delay_ms", default 1500) - the server silently dropped the
didOpen, and the re-sync is sent then. Well-behaved servers NEVER see the
redundant full-text didChange anymore (it made them re-analyze the just
opened file - a "double analysis" of every file); true restores the old
always-immediately behavior (for other servers with the same bug), false
disables it.
A document with UNSAVED changes at open time is synced immediately (no
delay): OmniSharp discards the didOpen buffer for every document, so the
server would keep analyzing the DISK copy while the editor diffs from its
own modified baseline - and for a never-registered "misc" file the first
full-text change only registers it (from disk), the buffer itself arrives
with the second one (both sent by the plugin in that case).

Force fresh diagnostics when the server is behind (VS Code's model):
  "force_diag_on_focus": "auto"   (default)
  "force_diag_on_focus": true     (every server)
  "force_diag_on_focus": false    (never)
VS Code's C# extension re-sends the FULL BUFFER on every active editor
switch ("O# does not recompute all diagnostics ... we want to at least
provide up to date diagnostics for the active document") and re-validates
everything when a project changes, a NuGet restore finishes or the
background analysis finishes. The LSP translation: one full-text
didChange - but EVIDENCE-gated, so nothing is ever re-analyzed twice: the
kick is sent only when the server is provably behind (it never published
diagnostics for the document, or published for an older version than the
last one sent - publishDiagnostics carries the analyzed version), at most
once per document version, and only for didOpen-dropper servers in "auto"
mode (OmniSharp; true = every server, false = never). Triggers: switching
the focused tab to a document, the editor window regaining focus, and the
OmniSharp events "project changed" / "package restore finished" /
"background analysis finished" (gated while packages are restoring, like
VS Code's Advisor).

How to disable auto-completion in "comments" and "strings". Overrides the same global option.
If "c" in value - disable in "comments"; if "s" in value - disable in "strings".
User must remove "s" from value for LSP servers that can auto-complete inside quotes
('class' attribute in HTML, etc).
  "disabled_contexts": "cs"
  

Server-specific options
-----------------------
Some servers can be additionally configured, this configuration can be placed
a) in the server config file settings/lsp_*.json
b) or in the project config file *.cuda-proj-lsp, near the project file *.cuda-proj
Use command "Plugins / LSP Client / Configure server for current project".

For example, Golang server "gopls" has docs about its options:
https://github.com/golang/tools/blob/master/gopls/doc/settings.md
Options can be written to:

a) settings/lsp_go.json
  ...
  "settings": {
    "gopls": {
        "hoverKind": "NoDocumentation"
    }
  }
  ...

b) project config myname.cuda-proj-lsp
  {
    "gopls": {
      "hoverKind": "NoDocumentation"
    }
  }

You can also use dot-path notation to specify sections in simple format:
  ...
  "settings": {
    "python.analysis.typeCheckingMode": "off",
  }
  ...

Another example. Python server "Jedi" gives server-specific option
to disable 'snippets' insertion by auto-completion. When 'snippets' are
disabled, auto-completion inserts only simple text, and if 'snippets' are
enabled, auto-completion inserts full-featured snippets, like plugin
Snippets does, with red-triangle 'markers' (for snippets with markers).
To disable 'snippets', write in lsp_*.json file:

  ...
  "settings": {
    "completion.disableSnippets": true,
  }
  ...


Plugin options
--------------
Plugin has the config file, which can be opened in CudaText by:
"Options / Settings-plugins / LSP Client / Config".
Possible options are listed in another text file in the LSP Client's "readme" sub-folder.


Semantic tokens
---------------
Semantic Tokens according to LSP specification is providing information about ID's kind
(class/var/param/macro/etc) and modifiers (global/static/readonly/etc).
For example, you want all 'classes' to be painted green, or all 'readonly vars' be painted
in teal color, etc.

Some servers provide the support for this feature, some don't. Tested with C++ (clangd), Java,
Lua, JS, TypeScript, Markdown, Rust.
Example .cpp file is located in the "readme" folder (cuda_lsp\readme\test_semantic_tokens.cpp).

To enable and configure this, call "LSP Client / Config" command and see the following options:
- "enable_semantic_tokens"
- "semantic_colors_light"
- "semantic_colors_dark"


LSP panel (bottom panel "LSP", one icon for ALL servers)
---------------------------------------------------------
There is a SINGLE LSP panel. It shows the logs of the FOCUSED EDITOR TAB
and nothing else: the focused file's diagnostics block, the focused file's
Spy traffic (JSON-RPC messages which mention that file), and the
server-level messages (server stderr/stdout, OmniSharp 'o#/...' events,
Messages/Logs, unhandled methods, response errors) of the focused file's
server instance. Switching a tab refreshes the panel immediately - like
Zed's contextual logs pane; messages of other files/servers are not mixed
in (they appear when their file gets the focus).
Empty states are explained in place ("No LSP server for this file"...).
Memory stays bounded: per-file Spy history is freed when the document
closes, and the history lists are ring buffers - 10000 server-level
messages per instance and 5000 Spy messages per file by default
(options "log_cap_server_msgs" / "log_cap_file_spy", 0 = unlimited).
DIAGNOSTICS ARE NEVER CAPPED: they are the current state of the document,
not a history stream - the panel always shows every diagnostic the server
published for the focused file.
Rendering is coalesced (~120 ms): bursts of messages cost one append, not
one full re-render per message. While the panel page is not the active
bottom-panel page, rendering is skipped (the button badge still counts).
Scrolling auto-follows the end ONLY while the memo is at its bottom
(terminal behaviour); scroll up to read old messages - auto-follow pauses
and NO later re-render (diagnostics replacement, message bursts, hiding/
showing the page) forces the scroll back down. Switching the context
(another file) shows the end of the new file's log.

Cells in the panel's top bar:
- instance cell - name of the shown server instance (fixed width; 'name
  (folder)' for per-folder instances of single-root servers like OmniSharp);
  click for a dropdown of ALL running instances of ALL servers, click an
  entry to PIN the panel to that ONE server instance: only its logs are
  shown - its server-level messages plus all its files (logs of other
  servers are never mixed in) - until the next tab switch; the first entry
  '(follow focused tab)' cancels the pin immediately; a pinned instance is
  marked with a trailing ' *' in the cell; the counter on the cell shows
  the number of running instances; hovering shows the full instance
  identity: server name, complete folder path, and the server command;
- category cells (Messages, Logs, Diagnostics, Spy, OmniSharp, server
  stderr...) and severity icons - toggle filters; counters on the cells
  show the message totals of the context ALWAYS (also for disabled
  categories), so you see there is something without enabling the category.

Every server instance has its own message store; nothing is ever mixed.
The panel's context is always re-derived from the focused tab (also
self-correcting when a server instance finishes initializing and starts
sending its analysis) - it can never get stuck on another tab's messages.
Double-click a 'Line N: ...' diagnostic to jump to it.
The category filters and word wrap are remembered globally (one panel).
The 'Messages' category receives 'window/showMessage' - one-shot messages
with a severity which the server wants to SHOW to the user (e.g. "project
loaded", or an error banner); most servers send none, that is why the
category is often empty. 'Logs' receives 'window/logMessage' (plain log
lines) - that is the one usually filled.


About
-----
Authors:
- Shovel, https://github.com/halfbrained/
- Yuriy Balyuk, https://github.com/veksha/
- snippet_engine.py by Alexey Torgashin (CudaText) & helpers

License: MIT
