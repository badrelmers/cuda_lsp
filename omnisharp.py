"""Handlers for OmniSharp's server-specific ``o#/...`` notifications.

OmniSharp emits its internal workspace events as JSON-RPC notifications with
custom ``o#/<eventname>`` method names (lowercase), because they have no LSP
spec equivalents. They arrive in the plugin as raw parsed dicts (lsprotocol
has no types for them) and are dispatched here instead of ending up in the
'Unhandled' panel category.

Method names and payload shapes follow OmniSharp's
``LanguageServerEventEmitter`` / ``EventTypes`` (omnisharp-roslyn repo):

    o#/projectadded, o#/projectchanged, o#/projectremoved
        {MsBuildProject: {Path, AssemblyName, TargetFramework,
         TargetFrameworks: [{Name, FriendlyName, ShortName}],
         SourceFiles: [...], Configuration, Platform, IsExe, ...}}
    o#/msbuildprojectdiagnostics
        {FileName, Warnings: [...], Errors: [...]} - .csproj load problems
        (each item: {LogLevel, FileName, Text, StartLine, StartColumn, ...};
        MSBuild lines are 1-based)
    o#/backgrounddiagnosticstatus
        {Status: 0=Started|1=Progress|2=Finished, NumberProjects,
         NumberFilesTotal, NumberFilesRemaining}
    o#/projectdiagnosticstatus  (obsolete shim, twin of the above)
        {Type, Status: 0=Started|1=Ready, ProjectFilePath} - quirk: OmniSharp
        puts the percent string '(NN %)' into ProjectFilePath, not a path
    o#/projectconfiguration
        {ProjectId, TargetFrameworks, References, SdkStyleProject, ...} -
        big payload of opaque hash ids, only shown compactly
    o#/error
        {Text, FileName, Line, Column} - Line/Column are 0-based (LSP-style)
    o#/packagerestorestarted, o#/packagerestorefinished
        {FileName, Succeeded}
    o#/unresolveddependencies
        {FileName, UnresolvedDependencies: [{Name, Version}]}

Progress-type events (status) only touch the status bar; discrete events
(project / MSBuild / restore / errors) are logged to the LSP panel under the
'OmniSharp' category. The raw JSON of every message stays visible in the
panel's 'Spy' category regardless. Unknown future ``o#/...`` methods (none of
the above) still go through the loud 'Unhandled' notification path.

All handlers are defensive: payloads are non-spec and vary between OmniSharp
versions, so nothing here may raise - ``handle_omnisharp_notification()``
wraps every call and reports failures as panel errors instead.
"""

import json

from cudatext import msg_status

from .dlg import TYPE_OMNISHARP, SEVERITY_ERR, SEVERITY_INFO, SEVERITY_WRN


LOG_NAME = 'LSP'


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _basename(path):
    """ File name of a server-provided path - server paths can be windows-
    or unix-style regardless of the client OS, and are never opened here.
    """
    if not isinstance(path, str) or not path:
        return '?'
    return path.replace('\\', '/').rstrip('/').rsplit('/', 1)[-1]


def _short(s, limit):
    s = str(s)
    if len(s) <= limit:
        return s
    return s[:limit - 3] + '...'


def _log(session, text, severity):
    """ One entry in the LSP panel's 'OmniSharp' category. """
    session.plog.log_str(
        f'OmniSharp: {text}',
        type_=TYPE_OMNISHARP, severity=severity, scroll=True)


def _status(session, text):
    """ Transient progress info - status bar only. """
    msg_status(f'{LOG_NAME}: OmniSharp: {text}')


def _is_dict(obj):
    return isinstance(obj, dict)


# --------------------------------------------------------------------------
# event handlers:  session, params (dict) -> None
# --------------------------------------------------------------------------

def _project_event(session, params, verb):
    info = params.get('MsBuildProject')
    if _is_dict(info):
        asm = info.get('AssemblyName') or _basename(info.get('Path'))
        tfms = [tf.get('ShortName') or tf.get('Name')
                for tf in (info.get('TargetFrameworks') or [])
                if _is_dict(tf)]
        srcs = info.get('SourceFiles')
        details = []
        if tfms:
            details.append('/'.join(str(t) for t in tfms))
        if isinstance(srcs, list):
            details.append(f'{len(srcs)} file(s)')
        extra = f' ({", ".join(details)})' if details else ''
        _log(session,
             f"project '{asm}' {verb}: {_basename(info.get('Path'))}{extra}",
             SEVERITY_INFO)
    else:
        # non-MSBuild project systems send other shapes: compact dump
        _log(session,
             f'project {verb}: {_short(json.dumps(params, ensure_ascii=False), 200)}',
             SEVERITY_INFO)


def on_project_added(session, params):
    _project_event(session, params, 'added')


def on_project_changed(session, params):
    _project_event(session, params, 'changed')


def on_project_removed(session, params):
    _project_event(session, params, 'removed')


def _msbuild_item_str(item):
    text = item.get('Text') or '?'
    loc = ''
    line = item.get('StartLine')
    col = item.get('StartColumn')
    if isinstance(line, int) and line > 0:
        # MSBuild diagnostics lines are 1-based: shown as-is
        loc = f'({_basename(item.get("FileName"))}:{line}'
        if isinstance(col, int) and col > 0:
            loc += f':{col}'
        loc += ')'
    return _short(f'{text} {loc}'.rstrip(), 300)


def on_msbuild_project_diagnostics(session, params):
    """ .csproj load diagnostics - THE signal when IntelliSense is broken
    because the project failed to load (missing SDK, broken targets...).
    """
    fname = _basename(params.get('FileName'))
    errors = params.get('Errors')
    warnings = params.get('Warnings')
    errors = errors if isinstance(errors, list) else []
    warnings = warnings if isinstance(warnings, list) else []

    sev = SEVERITY_ERR if errors else (SEVERITY_WRN if warnings else SEVERITY_INFO)
    _log(session,
         f'MSBuild project {fname}: {len(errors)} error(s), {len(warnings)} warning(s)',
         sev)
    for item in errors:
        if _is_dict(item):
            _log(session, f'  {_msbuild_item_str(item)}', SEVERITY_ERR)
    for item in warnings:
        if _is_dict(item):
            _log(session, f'  {_msbuild_item_str(item)}', SEVERITY_WRN)


def on_background_diagnostic_status(session, params):
    status = params.get('Status')
    if not isinstance(status, int):
        return
    total = params.get('NumberFilesTotal') or 0
    remaining = params.get('NumberFilesRemaining') or 0
    projects = params.get('NumberProjects') or 0

    if status == 2:    # Finished
        _status(session, f'analysis finished ({total} file(s), {projects} project(s))')
        _log(session,
             f'background analysis finished: {total} file(s) in {projects} project(s)',
             SEVERITY_INFO)
    elif status == 0:  # Started
        _status(session, f'analysis started: {total} file(s) in {projects} project(s)')
    else:              # 1 = Progress (updates are high-volume: status bar only)
        done = max(total - remaining, 0)
        pct = (100 * done // total) if total else 100
        _status(session, f'analyzing: {done}/{total} file(s) ({pct}%)')


def on_project_diagnostic_status(session, params):
    """ Obsolete twin of backgrounddiagnosticstatus, emitted right after it
    (kept by OmniSharp 'for compatibility with older clients'). Its
    ProjectFilePath field actually carries the percent string '(NN %)'.
    """
    if params.get('Status') == 0:  # Started
        pct = str(params.get('ProjectFilePath') or '').strip('() %')
        if pct.isdigit():
            _status(session, f'analyzing: {pct}%')
    # Status == 1 (Ready): the twin backgrounddiagnosticstatus 'Finished'
    # event already reports completion - nothing to do here.


def on_project_configuration(session, params):
    """ Big payload of opaque hash ids - only a compact confirmation line. """
    tfms = params.get('TargetFrameworks')
    refs = params.get('References')
    sdk = params.get('SdkStyleProject')
    parts = []
    if isinstance(tfms, list) and tfms:
        parts.append(', '.join(str(t) for t in tfms))
    if isinstance(refs, list):
        parts.append(f'{len(refs)} references')
    if sdk is not None:
        parts.append('SDK-style' if sdk else 'classic')
    extra = f' ({"; ".join(parts)})' if parts else ''
    _log(session, f'project configured{extra}', SEVERITY_INFO)


def on_error(session, params):
    text = params.get('Text') or '?'
    fname = params.get('FileName')
    line = params.get('Line')
    col = params.get('Column')
    loc = ''
    if fname and isinstance(line, int) and line >= 0:
        # Line/Column are 0-based on the wire (LSP-style indices)
        loc = f'({_basename(fname)}:{line + 1}'
        if isinstance(col, int) and col >= 0:
            loc += f':{col + 1}'
        loc += ')'
    _log(session, _short(f'error: {text} {loc}'.rstrip(), 300), SEVERITY_ERR)
    _status(session, _short(f'error: {text}', 100))


def on_package_restore_started(session, params):
    _status(session, f'restoring NuGet packages: {_basename(params.get("FileName"))}')


def on_package_restore_finished(session, params):
    fname = _basename(params.get('FileName'))
    if params.get('Succeeded'):
        _log(session, f'NuGet packages restored: {fname}', SEVERITY_INFO)
        _status(session, f'NuGet restore finished: {fname}')
    else:
        _log(session, f'NuGet package restore FAILED for {fname}', SEVERITY_ERR)
        _status(session, f'NuGet restore FAILED: {fname}')


def on_unresolved_dependencies(session, params):
    deps = params.get('UnresolvedDependencies')
    fname = _basename(params.get('FileName'))
    names = []
    if isinstance(deps, list):
        for dep in deps:
            if _is_dict(dep):
                name = dep.get('Name') or '?'
                version = dep.get('Version')
                names.append(f'{name} {version}' if version else str(name))
    listed = ', '.join(names[:8])
    if len(names) > 8:
        listed += f', ... (+{len(names) - 8} more)'
    _log(session,
         _short(f'unresolved dependencies in {fname}: {listed or "?"}', 300),
         SEVERITY_WRN)
    _status(session, _short(f'unresolved dependencies: {fname}', 100))


# --------------------------------------------------------------------------
# registry & entry point
# --------------------------------------------------------------------------

OMNISHARP_NOTIF = {
    'o#/projectadded':              on_project_added,
    'o#/projectchanged':            on_project_changed,
    'o#/projectremoved':            on_project_removed,
    'o#/msbuildprojectdiagnostics': on_msbuild_project_diagnostics,
    'o#/backgrounddiagnosticstatus': on_background_diagnostic_status,
    'o#/projectdiagnosticstatus':   on_project_diagnostic_status,
    'o#/projectconfiguration':      on_project_configuration,
    'o#/error':                     on_error,
    'o#/packagerestorestarted':     on_package_restore_started,
    'o#/packagerestorefinished':    on_package_restore_finished,
    'o#/unresolveddependencies':    on_unresolved_dependencies,
}


def handle_omnisharp_notification(session, method, params):
    """ Dispatch one ``o#/...`` notification to its handler.

    Returns True when the method is a known OmniSharp event (handled - the
    caller must not report it as unhandled). Never raises: a failing handler
    (malformed/evolved payload) is reported as a panel error instead of
    killing the recv loop.
    """
    handler = OMNISHARP_NOTIF.get(method)
    if handler is None:
        return False
    try:
        if not _is_dict(params):
            params = {}
        handler(session, params)
    except Exception as err:
        try:
            session.plog.log_str(
                f'OmniSharp: handler failed for {method}: {err}\n',
                type_=TYPE_OMNISHARP, severity=SEVERITY_ERR, scroll=True)
        except Exception:
            pass
    return True
