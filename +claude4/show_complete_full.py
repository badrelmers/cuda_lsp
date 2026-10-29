    def show_complete(self, message_id, items):
        
        if not items:
            msg_status(f'{LOG_NAME}: {self.lang_str}: Completion - no info')
            return
        
        word1 = ''
        if any(self.word):
            word1, _ = self.word
            
        _colors = app_proc(PROC_THEME_UI_DICT_GET, '')
        c1 = appx.int_to_html_color(_colors['ListFontHilite']['color'])
        c2 = appx.int_to_html_color(_colors['ListCompleteParams']['color'])
        c3 = appx.int_to_html_color(_colors['ButtonFontDisabled']['color']) # color for deprecated items

        def is_deprecated(item):
            # LSP 'tags': Tag.Deprecated is 1 per LSP spec
            tags = item.get('tags')
            if isinstance(tags, (list, tuple)) and 1 in tags:
                return True
            # LSP 'deprecated' boolean: item['deprecated'] == True
            if item.get('deprecated'):
                return True
            return False

        def add_html_tags(item, filter_text):
            text = item['label']
            item_kind = item['kind']
            deprecated = is_deprecated(item)
            if api_ver < '1.0.433':    return text
            
            if deprecated:
                # Apply strikethrough and grey color for deprecated items
                text = '<font color="{}"><s>{}</s></font>'.format(c3, text)
                return '<html>'+text

            #if item_kind in CALLABLE_COMPLETIONS:   text = '<u>'+text+'</u>'
            pos_bracket = text.find('(')
            prefix_len = pos_bracket if pos_bracket >= 0 else len(text)
            
            highlight_ranges = []
            if filter_text:
                prefix = text[:prefix_len]
                # Check for plain substring match first
                pos = prefix.find(filter_text)
                if pos == -1:
                    pos = prefix.lower().find(filter_text.lower())
                
                if pos != -1:
                    # If plain match, highlight the whole block
                    highlight_ranges.append((pos, pos + len(filter_text)))
                else:
                    # If no plain match, check for stored fuzzy match positions
                    fuzzy_positions = item.get('_cudalsp_fuzzy')
                    if fuzzy_positions:
                        # Highlight individual fuzzy characters
                        highlight_ranges.extend((p, p+1) for p in fuzzy_positions)
            
            # Use a set for efficient O(1) lookups in the loop
            highlight_positions = set()
            for start, end in highlight_ranges:
                for idx in range(start, min(end, len(text))):
                    highlight_positions.add(idx)

            # Build the HTML string in a single pass
            html_parts = []
            current_color = None

            def set_color(color):
                """Optimized helper to avoid redundant <font> tags."""
                nonlocal current_color
                if current_color == color:
                    return
                if current_color is not None:
                    html_parts.append('</font>')
                if color is not None:
                    html_parts.append('<font color="{}">'.format(color))
                current_color = color

            for idx, ch in enumerate(text):
                if pos_bracket != -1 and idx >= pos_bracket:
                    # Parameter color (c2)
                    color = c2
                elif idx in highlight_positions:
                    # Match color (c1)
                    color = c1
                else:
                    # Default color
                    color = None
                
                set_color(color)
                html_parts.append(ch)

            set_color(None) # Close any remaining font tag
            
            # Clean up the stored fuzzy data
            item.pop('_cudalsp_fuzzy', None)
            return '<html>'+''.join(html_parts)
        
        def short_version(s):
            s = s.replace('function', 'func')
            s = s.replace('variable', 'var')
            s = s.replace('constant', 'const')
            s = s.replace('typeparameter', 'typepar')
            s = s.replace('reference', 'ref')
            s = s.replace('keyword', 'keyw')
            s = s.replace('interface', 'intf')
            s = s.replace('property', 'prop')
            return s
        
        words = []
        for i, item in enumerate(items):
            # Handle both dict and lsp_types.CompletionItemKind for 'kind'
            item_kind = item.get('kind')
            if item_kind is not None:
                # Convert to name string
                if hasattr(item_kind, 'name'):
                    # It's an enum
                    kind_name = item_kind.name.lower()
                elif isinstance(item_kind, int):
                    # It's an integer, convert to enum then get name
                    try:
                        kind_name = lsp_types.CompletionItemKind(item_kind).name.lower()
                    except (ValueError, KeyError):
                        kind_name = ''
                else:
                    kind_name = ''
            else:
                kind_name = ''
            
            word_entry = '{}\t{}\t{}|{}'.format(
                add_html_tags(item, word1),
                short_version(kind_name),
                message_id,
                i
            )
            words.append(word_entry)
        
        sel = get_first(i for i, item in enumerate(items) if item.get('preselect') is True)
        sel = sel or 0
        
        ed.complete_alt('\n'.join(words), SNIP_ID, len_chars=0, selected=sel)
