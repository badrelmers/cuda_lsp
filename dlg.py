import re

from cudatext import *
import cudax_lib as apx

from lsprotocol import types as lsp

_   = apx.get_translation(__file__)  # I18N

api_ver = app_api_version()
app_active = True

FORM_W = 550
FORM_H = 350
BUTTON_H = 20
ED_MAX_LINES = 10
FORM_GAP = 4

### VSCode-derived hover timings (editorOptions.ts EditorHover defaults):
###   delay:300  hidingDelay:300  sticky:true
### Hide model (VSCode contentHoverController + contentHoverWidget):
###   - hide decisions are made ONLY on the hidingDelay(300ms) schedule,
###     never instantly from a poll;
###   - every check uses isMouseGettingCloser() with the baseline captured
###     at show() time (initialMousePos) - the mouse moving toward the
###     hover keeps it open and grants another grace period;
###   - the mouse INSIDE the hover keeps it open unconditionally;
###   - schedule chain: show() arms one check; the check that says "keep"
###     re-arms the next one (event-driven AND self-healing: it works even
###     if the form's on_mouse_enter/exit events never fire on some
###     CudaText builds - the chain alone implements the whole model);
###   - form on_mouse_enter cancels the chain (cheap), on_mouse_exit
###     re-arms it after the full hidingDelay (VSCode 'mouseleave').
HOVER_SHOW_DELAY_MS = 300      # VSCode editor.hover.delay
HOVER_HIDING_DELAY_MS = 300    # VSCode editor.hover.hidingDelay
HOVER_CLOSER_TOLERANCE_PX = 4  # VSCode isMouseGettingCloser() tolerance
HOVER_CORNER_GRIP = 16         # VSCode sash grab area, ~this size
HOVER_MIN_W = 150              # VSCode minimumSize width
HOVER_MIN_H = 60


def mix_colors(c1, c2):
    r1 = c1 & 0xFF
    g1 = c1 >> 8 & 0xFF
    b1 = c1 >> 16 & 0xFF

    r2 = c2 & 0xFF
    g2 = c2 >> 8 & 0xFF
    b2 = c2 >> 16 & 0xFF

    return (((b1+b2)//2 & 0xff) << 16) | (((g1+g2)//2 & 0xff) << 8) | ((r1+r2)//2 & 0xff);
    
def is_mouse_in_form(h_dlg):
    prop = dlg_proc(h_dlg, DLG_PROP_GET)
    if not prop['vis']: return False
    w = prop['w']
    h = prop['h']

    x, y = app_proc(PROC_GET_MOUSE_POS, '')
    x, y = dlg_proc(h_dlg, DLG_COORD_SCREEN_TO_LOCAL, index=x, index2=y)

    return (0<=x<w and 0<=y<h)

def mouse_in_form_local(h_dlg):
    """ Mouse position in form-local coords, or None when form is hidden.
    VSCode's isMousePositionWithinElement() equivalent. """
    prop = dlg_proc(h_dlg, DLG_PROP_GET)
    if not prop['vis']:
        return None
    x, y = app_proc(PROC_GET_MOUSE_POS, '')
    x, y = dlg_proc(h_dlg, DLG_COORD_SCREEN_TO_LOCAL, index=x, index2=y)
    return x, y

def dist_to_form_sqr(x, y, w, h):
    """ Squared distance from point (form-local) to form rectangle, 0 when
    inside. VSCode's computeDistanceFromPointToRectangle() without sqrt. """
    dx = max(0, -x, x - w + 1)
    dy = max(0, -y, y - h + 1)
    return dx*dx + dy*dy

# cant invoke method on 'Hint' class
def hint_callback(id_dlg, id_ctl, data='', info=''):
    Hint.on_widget_click(id_ctl, info)


class Hint:
    """ Short-lived dialog with 'Editor', hidden when mouse leaves it

    VSCode model (src/vs/editor/contrib/hover):
    - sticky: hover stays open while the mouse is over it or GETTING CLOSER
      to it (isMouseGettingCloser) - it never hides mid-travel toward it
    - hidingDelay: after the mouse leaves, a grace period passes before any
      hide decision; the first check fires after the full hidingDelay
    - event-driven, never polled: hiding is armed ONLY by show() (mouse
      never entered yet) or by the form's on_mouse_exit - while the mouse
      rests inside the hover, nothing is scheduled at all
    - immediate hides: Esc key, typed keys, app deactivated
    - resizable: corner grip; user's last size is remembered (_lastDimensions)
    """
    h = None
    theme_name = None
    current_caret = None
    re_unescape_bslash = None
    # user's manual resize (VSCode ContentHoverWidget._lastDimensions)
    user_w = 0
    user_h = 0
    resizing = False
    closest_mouse_dist_sq = None
    # mouse screen pos when the hover appeared (VSCode initialMousePosX/Y)
    initial_mouse_pos = None

    @classmethod
    def init_form(cls):
        global MarkupKind
        global FORM_H

        MarkupKind = lsp.MarkupKind

        _scale_UI_percent, _scale_font_percent = app_proc(PROC_CONFIG_SCALE_GET, '')
        cell_h = BUTTON_H + int(4 * _scale_UI_percent * 0.01)  # ~ one md_view text line
        FORM_H = FORM_GAP*2 + ED_MAX_LINES*cell_h + BUTTON_H

        h = dlg_proc(0, DLG_CREATE)

        colors = app_proc(PROC_THEME_UI_DICT_GET, '')
        color_form_bg = colors['TabBorderActive']['color']
        # THIN BORDER: 1px theme-colored edge (VSCode hover box-shadow look)
        # - 'bevel' control, one on each of the 4 sides, aligned to form
        #   edges, drawn OVER the client area (created last = on top)
        cls.color_border = mix_colors(color_form_bg, 0x000000) # slightly darker than bg
        try:
            _colors2 = app_proc(PROC_THEME_UI_DICT_GET, '')
            cls.color_border = _colors2['ListBorder']['color']
        except Exception:
            pass
        cls.color_btn_font = colors['ButtonFont']['color']
        cls.color_btn_back = colors['ButtonBgPassive']['color']
        cls.color_btn_font_disabled = colors['ButtonFontDisabled']['color']
        cls.color_btn_back_disabled = colors['ButtonBgDisabled']['color']

        dlg_proc(h, DLG_PROP_SET, prop={
                'w': FORM_W + 2*FORM_GAP,
                'border': DBORDER_NONE,
                'color': color_form_bg,
                'keypreview': True,          # form-level on_key_down: Esc hides hover
                'on_key_down': cls.form_key_down,
                # VSCode contentHoverWidget 'mouseleave' listener: leaving
                # the hover schedules the hidingDelay check - the ONLY
                # trigger for an automatic hide while the mouse rests.
                'on_mouse_enter': cls.form_mouse_enter,
                'on_mouse_exit': cls.form_mouse_exit,
                })

        cls._n_sb = dlg_proc(h, DLG_CTL_ADD, 'statusbar')
        dlg_proc(h, DLG_CTL_PROP_SET, index=cls._n_sb, prop={
                'align': ALIGN_BOTTOM,
                'sp_l': 1,
                'sp_r': 1,
                'sp_b': 1,
                'h': BUTTON_H,
                })
        cls._h_sb = dlg_proc(h, DLG_CTL_HANDLE, index=cls._n_sb)

        n = dlg_proc(h, DLG_CTL_ADD, 'md_view')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
                'align': ALIGN_CLIENT,
                'sp_a': FORM_GAP,
                'h': FORM_H,
                'on_click_link': cls.on_click_link,
                })
        cls.h_md = dlg_proc(h, DLG_CTL_HANDLE, index=n)

        ### RESIZABLE (VSCode resizableContentWidget): a corner grip
        ### control in the bottom-right; mouse-down on it starts a drag
        ### which resizes the form (and re-anchors statusbar/md_view).
        ### Not DBORDER_SIZE - that draws an OS caption bar which looks
        ### nothing like a hover.
        grip = dlg_proc(h, DLG_CTL_ADD, 'panel')
        dlg_proc(h, DLG_CTL_PROP_SET, index=grip, prop={
                'name': 'grip',
                'w': HOVER_CORNER_GRIP, 'h': HOVER_CORNER_GRIP,
                'a_r': ('', ']'), 'a_b': ('', ']'),  # anchor right/bottom to form corner
                'color': cls.color_border,
                'on_mouse_down': cls.grip_mouse_down,
                'on_mouse_move': cls.grip_mouse_move,
                'on_mouse_up': cls.grip_mouse_up,
                'on_mouse_enter': cls.grip_mouse_enter,
                'on_mouse_exit': cls.grip_mouse_exit,
                })
        cls._n_grip = grip

        ### thin border: 4 bevels on the form edges (drawn over content)
        for side, props in (
                ('t', {'align': ALIGN_TOP,    'h': 1}),
                ('b', {'align': ALIGN_BOTTOM, 'h': 1}),
                ('l', {'align': ALIGN_LEFT,   'w': 1}),
                ('r', {'align': ALIGN_RIGHT,  'w': 1}),
                ):
            n = dlg_proc(h, DLG_CTL_ADD, 'bevel')
            _p = {'name': 'brd_'+side, 'vis': True}
            _p.update(props)
            dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop=_p)

        cls.theme_name = app_proc(PROC_THEME_UI_GET, '')

        dlg_proc(h, DLG_SCALE)
        return h, None
        
    @classmethod
    def set_cursor_margin(cls, cursor_move_tolerance):
        # kept for API compatibility (lsp.py may call) - VSCode model has no
        # cursor-move-from-anchor tolerance: stickiness is handled by
        # is_mouse_getting_closer() in hide_check_timer()
        pass

    # language - from deprecated 'MarkedString'
    @classmethod
    def show(cls, text, caret, cursor_loc_start, markupkind=None, language=None, caret_cmds=None):

        if not text:
            return

        if cls.h is None  or  cls.is_theme_changed():
            if cls.h is not None: # theme changed
                dlg_proc(cls.h, DLG_FREE)

            cls.h, _ = cls.init_form()

        cls.current_caret = caret # for 'Go to Definition'
        # VSCode RenderedContentHover.initialMousePosX/Y + closestMouseDistance:
        # remember where the mouse was when hover appeared; hide logic then
        # only cares whether the mouse is getting CLOSER to the hover or not.
        cls.closest_mouse_dist_sq = None
        cls.resizing = False

        ### dialog md_view setup: control renders markdown itself,
        ### colors/fonts are applied by app from current UI theme;
        ### text is loaded via md_proc() (prop "val" is removed)
        md_proc(cls.h_md, MD_SET_TEXT, text)

        ### calculate dialog position and dimensions: x,y, h,w
        l,t,r,b = ed.get_prop(PROP_RECT_TEXT)
        cell_w, cell_h = ed.get_prop(PROP_CELL_SIZE)
        ed_size_x = r - l # text area sizes - to not obscure other ed-controls

        caret_loc_px = ed.convert(CONVERT_CARET_TO_PIXELS, x=caret[0], y=caret[1])
        if caret_loc_px is None: return
        top_hint = caret_loc_px[1]-t > b-caret_loc_px[1] # space up is larger than down
        y0,y1 = (t, caret_loc_px[1])  if top_hint else  (caret_loc_px[1], b)
        space_h = y1-y0 - FORM_GAP*2
        if not top_hint:
            space_h -= cell_h
        _scale_UI_percent, _scale_font_percent = app_proc(PROC_CONFIG_SCALE_GET, '')
        h = min(FORM_H * _scale_UI_percent // 100, space_h)
        w = min(FORM_W * _scale_UI_percent // 100, ed_size_x)

        ### honor user's manual resize (VSCode _lastDimensions): a resized
        ### hover re-appears with the size the user left it at
        if cls.user_w:
            w = cls.user_w
        if cls.user_h:
            h = max(cls.user_h, HOVER_MIN_H) if space_h > HOVER_MIN_H else h

        x = caret_loc_px[0] - int(w*0.5) # center over caret
        if x < l: # dont fit on left
            x = l + FORM_GAP
        elif x+w > r: # dont fit on right
            x = r - w - FORM_GAP

        if top_hint:
            y = (caret_loc_px[1] - (h + FORM_GAP))
        else:
            y = (caret_loc_px[1] + cell_h + FORM_GAP)


        dlg_proc(cls.h, DLG_PROP_SET, prop={
                'p': ed.get_prop(PROP_HANDLE_SELF ), #set parent to Editor handle
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                })

        cls.caret_cmds = caret_cmds
        if caret_cmds:
            cls.fill_cmds(caret_cmds, min(FORM_W, ed_size_x))

        ### Hide model (VSCode contentHoverController):
        ### - while the mouse is INSIDE the hover: nothing is scheduled,
        ###   form_mouse_exit() is the only thing that arms the timer;
        ### - the mouse has NOT entered the hover yet: one hidingDelay
        ###   check is armed - if the mouse is still moving toward the
        ###   hover (is_mouse_getting_closer) it stays and the check is
        ###   re-armed, giving another full grace period (exactly
        ###   _shouldRescheduleHoverComputation + runner.schedule);
        ### - NO repeating poll while the mouse simply rests: a poll tick
        ###   landing right after show() (mouse still near the anchor)
        ###   with jitter > 4px killed the hover an instant after it
        ###   appeared (Alexey-T/CudaText#6329).
        timer_proc(TIMER_STOP, Hint.hide_check_timer, 250, tag='')
        # baseline: closest distance is measured from where the mouse was
        # when the hover appeared (VSCode initialMousePosX/Y) - NOT from a
        # later poll position, which would poison the comparison
        cls.initial_mouse_pos = app_proc(PROC_GET_MOUSE_POS, '')
        timer_proc(TIMER_START_ONE, Hint.hide_check_timer, HOVER_HIDING_DELAY_MS, tag='first')
        dlg_proc(cls.h, DLG_SHOW_NONMODAL)

    @classmethod
    def is_mouse_getting_closer(cls):
        """ VSCode ContentHoverWidget.isMouseGettingCloser(): compare current
        mouse-to-form distance with the closest distance seen so far; when
        the mouse moves farther than closest+tolerance (squared px), it is
        going away - only then the hover may hide. """
        pos = mouse_in_form_local(cls.h)
        if pos is None:
            return False
        prop = dlg_proc(cls.h, DLG_PROP_GET)
        dist_sq = dist_to_form_sqr(pos[0], pos[1], prop['w'], prop['h'])
        if cls.closest_mouse_dist_sq is None:
            # first measurement after show(): seed the baseline with the
            # CURRENT distance (VSCode's first isMouseGettingCloser call
            # also just records and returns 'not closer' - a hide needs a
            # LATER measurement proving the distance GREW). Never seed
            # with the show-time position: the form often appears AT the
            # resting mouse (hover anchors at the hovered word), which
            # would give baseline 0 and make any move off the form read
            # as 'farther' - the hover would die on the first check.
            cls.closest_mouse_dist_sq = dist_sq
            return True
        if dist_sq > cls.closest_mouse_dist_sq + (HOVER_CLOSER_TOLERANCE_PX ** 2) * 2:
            # mouse is getting farther away
            return False
        cls.closest_mouse_dist_sq = min(cls.closest_mouse_dist_sq, dist_sq)
        return True

    @classmethod
    def fill_cmds(cls, cmds, width):
        statusbar_proc(cls._h_sb, STATUSBAR_DELETE_ALL)

        cellwidth = int(width/len(cmds)) + 1
        callback_fstr = 'module=cuda_lsp.dlg;func=hint_callback;info="{}";'
        for caption,cmd in cmds.items():
            cellind = statusbar_proc(cls._h_sb, STATUSBAR_ADD_CELL, index=-1)
            statusbar_proc(cls._h_sb, STATUSBAR_SET_CELL_TEXT, index=cellind, value=caption)
            statusbar_proc(cls._h_sb, STATUSBAR_SET_CELL_SIZE, index=cellind, value=cellwidth)

            if cmd:
                bg,fg = cls.color_btn_back,  cls.color_btn_font

                callback = callback_fstr.format(caption)
                statusbar_proc(cls._h_sb, STATUSBAR_SET_CELL_CALLBACK, index=cellind, value=callback)
            else:
                bg,fg = cls.color_btn_back_disabled,  cls.color_btn_font_disabled

            statusbar_proc(cls._h_sb,  STATUSBAR_SET_CELL_COLOR_BACK, index=cellind, value=bg)
            statusbar_proc(cls._h_sb,  STATUSBAR_SET_CELL_COLOR_FONT, index=cellind, value=fg)


    @classmethod
    def on_widget_click(cls, n, info):
        if n == cls._n_sb:
            f = cls.caret_cmds.get(info)
            if f:
                f(caret=cls.current_caret)

    @classmethod
    def on_click_link(cls, id_dlg, id_ctl, data='', info=''):
        if data:
            apx.safe_open_url(data)

    ### --- form/key events ------------------------------------------------

    @classmethod
    def form_mouse_enter(cls, id_dlg, id_ctl, data='', info=''):
        """ Mouse entered the hover (VSCode: isMouseOnContentHoverWidget ->
        _shouldKeepCurrentHover -> runner.cancel()). Nothing may be armed;
        an exit event re-arms the check. """
        cls.closest_mouse_dist_sq = 0
        timer_proc(TIMER_STOP, Hint.hide_check_timer, 250, tag='')

    @classmethod
    def form_mouse_exit(cls, id_dlg, id_ctl, data='', info=''):
        """ Mouse left the hover (VSCode contentHoverWidget 'mouseleave' ->
        _onMouseLeave -> runner.schedule(hidingDelay)): after the grace
        period, hide unless the mouse is getting closer to the hover. """
        if not cls.is_visible():
            return
        if cls.resizing:
            return
        timer_proc(TIMER_STOP, Hint.hide_check_timer, 250, tag='')
        timer_proc(TIMER_START_ONE, Hint.hide_check_timer, HOVER_HIDING_DELAY_MS, tag='leave')

    @classmethod
    def form_key_down(cls, id_dlg, id_ctl, data='', info=''):
        """ VSCode _onKeyDown: Esc hides the hover; other keys pass through.
        Return False to block the key. """
        if id_ctl == 27: # VK_ESCAPE
            if cls.is_visible():
                cls.hide()
                ed.focus()
                return False
        return None

    ### --- resize grip (VSCode resizableContentWidget sash) ---------------

    @classmethod
    def grip_mouse_down(cls, id_dlg, id_ctl, data='', info=''):
        if not isinstance(data, dict):
            cls.resizing = False
            return
        # remember form size + mouse screen pos at drag start
        prop = dlg_proc(cls.h, DLG_PROP_GET)
        cls._rs_w = prop['w']
        cls._rs_h = prop['h']
        cls._rs_x, cls._rs_y = app_proc(PROC_GET_MOUSE_POS, '')
        cls.resizing = True
        # suspend the hide-check while dragging (VSCode _isContentWidgetResizing)
        timer_proc(TIMER_STOP, Hint.hide_check_timer, 250, tag='')
        # focus stays with editor; grip keeps receiving on_mouse_move since
        # the button is held
        return False

    @classmethod
    def grip_mouse_move(cls, id_dlg, id_ctl, data='', info=''):
        if not getattr(cls, 'resizing', False) or not isinstance(data, dict):
            return
        mx, my = app_proc(PROC_GET_MOUSE_POS, '')
        dw = mx - cls._rs_x
        dh = my - cls._rs_y
        w = max(HOVER_MIN_W, cls._rs_w + dw)
        h = max(HOVER_MIN_H, cls._rs_h + dh)
        dlg_proc(cls.h, DLG_PROP_SET, prop={
                'w': w,
                'h': h,
                })
        cls.user_w = w      # VSCode _lastDimensions persistence
        cls.user_h = h

    @classmethod
    def grip_mouse_up(cls, id_dlg, id_ctl, data='', info=''):
        if getattr(cls, 'resizing', False):
            cls.resizing = False
            # re-arm the hide-check for the new geometry
            cls.closest_mouse_dist_sq = None
            timer_proc(TIMER_START, Hint.hide_check_timer, 250, tag='')
        return None

    @classmethod
    def grip_mouse_enter(cls, id_dlg, id_ctl, data='', info=''):
        # cursor over grip: pause hide-check so user can grab it calmly
        timer_proc(TIMER_STOP, Hint.hide_check_timer, 250, tag='')

    @classmethod
    def grip_mouse_exit(cls, id_dlg, id_ctl, data='', info=''):
        # leaving the grip = leaving the form; same hidingDelay check
        cls.form_mouse_exit(id_dlg, id_ctl, data, info)

    @classmethod
    def set_max_lines(cls, nlines):
        global ED_MAX_LINES

        ED_MAX_LINES = nlines

    @classmethod
    def hide_check_timer(cls, tag='', info=''):
        """ The scheduled hide reaction (VSCode _reactToEditorMouseMoveRunner
        firing after hidingDelay). Runs only when armed: by show() (mouse
        never entered the hover yet), by form_mouse_exit (mouse just left),
        or by the previous keep decision (self-healing chain). """
        # NOTE: 'app_active' is deliberately NOT consulted here. It is a
        # plugin-tracked flag that only updates on on_app_activate/
        # deactivate; a missed activate (see lsp.on_app_activate) left it
        # stuck False and made EVERY check hide the hover an instant after
        # show - the exact 'shows then vanishes' bug. The real deactivate
        # EVENT already hides the hover directly; a stale flag must never
        # be allowed to hide it.

        if not cls.is_visible():
            # dialog closed already (autocompletion, Esc, app deactivate)
            timer_proc(TIMER_STOP, Hint.hide_check_timer, 250, tag='')
            return

        ### VSCode contentHoverController._reactToEditorMouseMove: hide
        ### ONLY when all of these are false:
        ###   - mouse is INSIDE the hover (sticky)
        ###   - mouse is GETTING CLOSER to the hover (isMouseGettingCloser)
        ###   - user is dragging the resize grip
        ###   - mouse button is held down (e.g. selecting hover text)
        left_button_down = 'L' in app_proc(PROC_GET_KEYSTATE, '')

        if is_mouse_in_form(cls.h):
            # mouse is inside: keep open. The chain keeps re-arming
            # (a slow loop; events may never fire on some CudaText builds,
            # so the chain itself must implement 'sticky'), and the
            # closest-baseline resets so a later exit is judged fresh.
            cls.closest_mouse_dist_sq = 0
            timer_proc(TIMER_STOP, Hint.hide_check_timer, 250, tag='')
            timer_proc(TIMER_START_ONE, Hint.hide_check_timer, HOVER_HIDING_DELAY_MS, tag='inside')
            return

        if cls.is_mouse_getting_closer() and not left_button_down and not cls.resizing:
            # VSCode _shouldRescheduleHoverComputation: mouse is still
            # heading toward the hover - keep it and grant ANOTHER full
            # hidingDelay grace period before judging again
            timer_proc(TIMER_STOP, Hint.hide_check_timer, 250, tag='')
            timer_proc(TIMER_START_ONE, Hint.hide_check_timer, HOVER_HIDING_DELAY_MS, tag='again')
            return

        timer_proc(TIMER_STOP, Hint.hide_check_timer, 250, tag='')
        cls.hide()
        ed.focus()

    @classmethod
    def hide(cls):
        if not cls.h:    return
        if cls.resizing:  return
        cls.current_caret = None
        dlg_proc(cls.h, DLG_HIDE)

    @classmethod
    def is_theme_changed(cls):
        old_name = cls.theme_name
        cls.theme_name = app_proc(PROC_THEME_UI_GET, '')
        return old_name != cls.theme_name

    @classmethod
    def is_visible(cls):
        if cls.h is None:
            return False
        return dlg_proc(cls.h, DLG_PROP_GET)['vis']

    @classmethod
    def is_under_cursor(cls):
        return cls.is_visible()  and  is_mouse_in_form(cls.h)

    @classmethod
    def unescape_bslash(cls, text):
        if cls.re_unescape_bslash is None:
            import re

            cls.re_unescape_bslash = re.compile(r'\\([^\\])')

        return cls.re_unescape_bslash.sub(r'\1', text)


class SignaturesDialog:
    
    themed = True
    color_font = 0
    color_bg = apx.html_color_to_int('ffffe1')
    color_dimmed = apx.html_color_to_int('909090')
    color_hilite = apx.html_color_to_int('0000FF')
    h = None
    memo: Editor = None
    spacing = 2
    param_pos = 0
    dim_unfocused_value = 0
    wrap_info_loaded = False
    
    @classmethod
    def move_window(cls):
        if cls.h and cls.memo:
            mon_x1, mon_y1, mon_x2, mon_y2 = app_proc(PROC_COORD_MONITOR,0)
            screen_w, screen_h = (mon_x2 - mon_x1, mon_y2 - mon_y1)

            dlg_proc(cls.h, DLG_CTL_PROP_SET, name='memo', prop={
                'w': screen_w, 'h': screen_h
            })

            # tooltip must have the same font_size / scale as editor
            font_prop = ed.get_prop(PROP_FONT, '')
            scale = ed.get_prop(PROP_SCALE_FONT, '')
            cls.memo.set_prop(PROP_FONT, font_prop)
            cls.memo.set_prop(PROP_SCALE_FONT, scale)

            wrapped_lines = 0
            while True:
                app_proc(PROC_IDLE, False)
                if cls.wrap_info_loaded:
                    wrap_info = cls.memo.get_wrapinfo()
                    wrapped_lines = max(1, len(wrap_info))
                    break 

            #max_line_len = 10
            # for first painting of tooltip [Linux qt5]
            max_line_len = cls.memo.get_line_len(0)
            for line in wrap_info:
                max_line_len = max(max_line_len, line['len'])

            cell_x, cell_y = cls.memo.get_prop(PROP_CELL_SIZE, 0)
            ed_cell_x, ed_cell_y = ed.get_prop(PROP_CELL_SIZE, 0)
            cell_x = max(cell_x, 7) # for first painting of tooltip [Linux qt5]
            cell_y = max(cell_y, 16)
            h = wrapped_lines * cell_y + (cls.spacing*4)
            w = max_line_len * cell_x + (cls.spacing*4)
            
            caret_x, caret_y = ed.get_carets()[0][:2]
            
            # caret x/y to screen x/y
            x, y = ed.convert(CONVERT_CARET_TO_PIXELS, caret_x, caret_y) or (0, 0)
            x, y = ed.convert(CONVERT_LOCAL_TO_SCREEN, x, y) or (0, 0)
            
            # offset x position in hope that parameter in tooltip will be close to caret pos
            #if cls.param_pos:
                #x = x - cls.param_pos*cell_x
            markers = cls.memo.attr(MARKERS_GET_DICT)
            for marker in markers:
                if marker['tag'] == 1:
                    xy = cls.memo.convert(CONVERT_CARET_TO_PIXELS, marker['x']+1, marker['y'])
                    if xy:
                        param_pos, _ = xy
                        param_len = marker['len']
                        x = x - (param_pos+(param_len*cell_x//2)) + cell_x
                        break
            
            # do not allow to move behind screen edges
            _y = y-cell_y*wrapped_lines-cls.spacing*6
            if _y >= 0:     y = _y
            else:           y = y+ed_cell_y+cls.spacing*2

            if x + w > mon_x1+screen_w:
                x = mon_x1+screen_w - w
            if x < mon_x1:   x = mon_x1
            if y < mon_y1:   y = mon_y1
            
            dlg_proc(cls.h, DLG_PROP_SET, prop={
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                'color': cls.color_bg,
                })
    
    @classmethod
    def set_text(cls, signatures):
        if cls.h is None:
            cls.h, cls.memo = cls.init_form()
            
        if cls.themed:
            colors = app_proc(PROC_THEME_UI_DICT_GET, '')
            cls.color_font = colors['ListFont']['color']
            cls.color_bg = colors['ListBg']['color']
            cls.color_hilite = colors['ListFontHotkey']['color']
            cls.color_dimmed = mix_colors(cls.color_font, cls.color_bg)

        cls.memo.set_prop(PROP_COLOR, (COLOR_ID_TextFont, cls.color_font))
        cls.memo.set_prop(PROP_COLOR, (COLOR_ID_TextBg, cls.color_bg))

        signatures, activeSignature, activeParameter = signatures
        if activeSignature is None or activeSignature >= len(signatures):
            activeSignature = 0
        
        cls.param_pos = 0
        cls.memo.set_prop(PROP_RO, False)
        cls.memo.set_text_all('')
        cls.memo.dim(DIM_DELETE_ALL)

        sig: lsp.SignatureInformation
        for i,sig in enumerate(signatures):
            cls.memo.set_text_line(-2, sig.label)
            if i != activeSignature:
                #cls.memo.attr(MARKERS_ADD, x=0, y=i, len=len(sig.label), color_font=cls.color_dimmed)
                cls.memo.dim(DIM_ADD, i, i, 150)
            
            if not sig.parameters:  continue
            
            if activeParameter is None or activeParameter >= len(sig.parameters):
                activeParameter = 0
            
            activeParameter = sig.active_parameter if sig.active_parameter is not None else activeParameter
            
            param = sig.parameters[activeParameter].label
            if isinstance(param, tuple):
                x1, x2 = param
                cls.memo.attr(MARKERS_ADD, x=x1, y=i, len=x2-x1, color_font=cls.color_hilite, tag=1)
                cls.param_pos = x1
            elif isinstance(param, str):
                # replace comma with special char (excluding ones inside [{()}] brackets)
                brackets = 0
                signature = sig.label
                signature = re.sub(r".*?\(","", signature, count=1) # remove method name and first bracket '('
                params_start = len(sig.label) - len(signature) # remember position where parameters start
                signature = re.sub(r"\)[^,)]*$","", signature, count=1) # remove last bracket ')' and return value
                char_list = list(signature)
                for j,c in enumerate(char_list):
                    if 0:pass
                    elif c in '[{(':    brackets += 1
                    elif c in ']})':    brackets -= 1
                    elif c == ',':
                        if brackets <= 0:   char_list[j]=chr(1)
                
                parts = re.split(r'\x01', ''.join(char_list))
                pos = params_start
                skipping = True
                skipped = -1
                for j,part in enumerate(parts):
                    param_name = re.split(':|=',part)[0]
                    param_name = param_name.strip().replace('*','')
                    first_real_param = sig.parameters[0].label.strip().replace('*','')
                    first_real_param = re.split(':|=',first_real_param)[0]
                    if skipping and param_name != first_real_param:
                        skipped += 1
                        pos += len(part)+1
                        continue # skip 'self' or 'cls', etc...
                    else:
                        skipping = False
                    if j-skipped == activeParameter+1:
                        cls.memo.attr(MARKERS_ADD, x=pos, y=i, len=len(part), color_font=cls.color_hilite, tag=1)
                        cls.param_pos = pos
                        break
                    pos += len(part)+1
        cls.memo.set_prop(PROP_LINE_TOP, 0)
        cls.memo.set_prop(PROP_SCROLL_HORZ_INFO, {'pos': 0})
        cls.memo.set_prop(PROP_RO, True)

    @classmethod
    def show(cls):
        cls.wrap_info_loaded = False
        if cls.h is None:
            cls.h, cls.memo = cls.init_form()
            
        if cls.is_visible():
            timer_proc(TIMER_STOP, cls.hide, 8000, tag='')
            timer_proc(TIMER_START_ONE, cls.hide, 8000, tag='')
            cls.wrap_info_loaded = True
            cls.move_window()
            return
        
        dlg_proc(cls.h, DLG_PROP_SET, prop={ 'taskbar': 2 })
        
        # workaround for `dim_unfocused` option
        # (save value to variable, set to 0, then restore from variable after ed.focus())
        if api_ver >= '1.0.429':
            cls.dim_unfocused_value = ed.get_prop(PROP_DIM_UNFOCUSED)
            #print('setting from ',cls.dim_unfocused_value, 'to 0')
            ed.set_prop(PROP_DIM_UNFOCUSED, 0)
        
        
        dlg_proc(cls.h, DLG_SHOW_NONMODAL)
        dlg_proc(cls.h, DLG_PROP_SET, prop={
                    'w': 0, 'h': 0 })
        
        # ed.focus() will be called inside timer (workaround for Linux)
        timer_proc(TIMER_START_ONE, cls.unfocus, 50, tag='')

        timer_proc(TIMER_STOP, cls.hide, 8000, tag='')
        timer_proc(TIMER_START_ONE, cls.hide, 8000, tag='')
        
        cls.move_window()
        
    @classmethod
    def init_form(cls):
        h=dlg_proc(0, DLG_CREATE)
        dlg_proc(h, DLG_PROP_SET, prop={
            'cap': 'Tooltip',
            'topmost': True,
            'border': DBORDER_NONE,
            'taskbar': 2,
        })
        cls.h = h
        
        _, font_size = ed.get_prop(PROP_FONT)
        font_scale = ed.get_prop(PROP_SCALE_FONT)
        
        idc=dlg_proc(h, DLG_CTL_ADD, 'editor');
        dlg_proc(cls.h, DLG_CTL_PROP_SET, index=idc, prop={
            'border': DBORDER_NONE,
            'name': 'memo',
            #'align': ALIGN_CLIENT,
            'font_size': font_size,
            'sp_a': cls.spacing
        })
        cls.memo = Editor(dlg_proc(h, DLG_CTL_HANDLE, index=idc))
        cls.memo.set_prop(PROP_SCALE_FONT, font_scale)
        cls.memo.set_prop(PROP_UNDO_LIMIT, 0)
        cls.memo.set_prop(PROP_LAST_LINE_ON_TOP, False)
        cls.memo.set_prop(PROP_GUTTER_NUM, False)
        cls.memo.set_prop(PROP_GUTTER_STATES, False)
        cls.memo.set_prop(PROP_GUTTER_FOLD, False)
        cls.memo.set_prop(PROP_GUTTER_BM, False)
        cls.memo.set_prop(PROP_MINIMAP, False)
        cls.memo.set_prop(PROP_MICROMAP, False)
        cls.memo.set_prop(PROP_SCROLLSTYLE_VERT, SCROLLSTYLE_HIDE)
        cls.memo.set_prop(PROP_SCROLLSTYLE_HORZ, SCROLLSTYLE_HIDE)
        cls.memo.set_prop(PROP_CARET_VIEW, (0, 0, False))
        cls.memo.set_prop(PROP_CARET_VIEW_RO, cls.memo.get_prop(PROP_CARET_VIEW))
        cls.memo.set_prop(PROP_WRAP, WRAP_ON_WINDOW)
        cls.memo.set_prop(PROP_HILITE_CUR_LINE, False)
        cls.memo.set_prop(PROP_THEMED, False)
        
        dlg_proc(h, DLG_SCALE)
        return h, cls.memo

    @classmethod
    def unfocus(cls, tag='', info=''):
        global app_active
        cls.wrap_info_loaded = True
        if app_active:
            ed.focus()
            #print('ed.focus in unfocus()')
        if api_ver >= '1.0.429':
            #print('restoring to',cls.dim_unfocused_value)
            ed.set_prop(PROP_DIM_UNFOCUSED, cls.dim_unfocused_value)
        
    @classmethod
    def hide(cls, tag='', info=''):
        if not cls.h:    return
        dlg_proc(cls.h, DLG_HIDE)

    @classmethod
    def is_visible(cls):
        if cls.h is None:
            return False
        return dlg_proc(cls.h, DLG_PROP_GET)['vis']

    @classmethod
    def on_theme_change(cls):
        cls.hide()
