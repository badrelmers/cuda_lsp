    def do_complete(self, message_id, snippet_text, items):
        if '|' not in snippet_text:
            return
        items_msg_id, item_ind = snippet_text.split('|')
        if int(items_msg_id) != message_id:
            return

        item_ind = int(item_ind)
        
        if item_ind >= len(items): # fixes rare bug
            return
        
        item = items[item_ind]
            
        _carets = ed.get_carets()
        x0,y0, _x1,_y1 = _carets[0]

        lex = ed.get_prop(PROP_LEXER_FILE, '')
        
        x1 = x2 = x0
        y1 = y2 = y0
        word1 = word2 = ''
        if any(self.word):
            word1, word2 = self.word
            x1 = x0-len(word1)
            x2 = x0+len(word2)
        
        line_txt = ed.get_text_line(y0)
        
        # Check item kind - handle both int and enum
        item_kind = item.get('kind')
        if item_kind is not None:
            if isinstance(item_kind, int):
                # Convert int to enum for comparison
                try:
                    item_kind = lsp_types.CompletionItemKind(item_kind)
                except (ValueError, KeyError):
                    item_kind = None
        
        is_callable = item_kind in CALLABLE_COMPLETIONS if item_kind else False
        
        # Check insertTextFormat - handle both int and enum
        insert_format = item.get('insertTextFormat')
        if insert_format is not None:
            if isinstance(insert_format, int):
                # Compare as int
                is_snippet = insert_format == 2  # InsertTextFormat.Snippet = 2
            elif hasattr(insert_format, 'value'):
                # It's an enum, compare values
                is_snippet = insert_format.value == 2
            else:
                # Compare directly (might be enum)
                is_snippet = insert_format == lsp_types.InsertTextFormat.Snippet
        else:
            is_snippet = False

        cached_x = self.carets[0][0]
        cached_x_diff = x0-cached_x
        
        if item.get('textEdit') is not None:
            x1,y1,x2,y2 = EditorDoc.range2carets(item.get('textEdit')['range'])
            text = item.get('textEdit')['newText']
        elif item.get('insertText') is not None:
            text = item.get('insertText')
        else:
            text = item.get('label')
        
        # useful logging (when DEBUG_COMPLETION is enabled)
        if DEBUG_COMPLETION:
            if is_snippet:   print("SNIPPET", item)
            else:            print("PLAIN TEXT", item)
            # also print test template. can be handy to create new test.
            initial_text = line_txt[:x0]+'|'+line_txt[x0:]
            if cached_x != x0:
                initial_text = initial_text[:cached_x]+'|'+initial_text[cached_x:]
            leading_spaces = len(line_txt) - len(line_txt.lstrip(' '))
            initial_text = initial_text[leading_spaces:]
            test_str = "Test('{}', '{}', ({},{},{},{}), '{}', 'PASTE_RESULT_HERE', {}, {})".format(
                lex, initial_text, x1-leading_spaces, 0, x2-leading_spaces, 0, text, is_callable, is_snippet)
            print(test_str)
        
        edit = CompletionEdit((x1, y1, x2, y2), text, x0, y0, word1, word2, is_callable, is_snippet, cached_x) 
        CompletionMan.apply_completion_edit(edit)
        
        # additional edits
        if item.get('additionalTextEdits') is not None:
            for edit in item.get('additionalTextEdits'):
                EditorDoc.apply_edit(ed, edit)
        return True
