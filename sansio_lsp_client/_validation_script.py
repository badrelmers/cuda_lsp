"""
LSP Server Validation Test Script
Run this in CudaText console to test each LSP feature systematically.
"""

def test_lsp_server(lang_name):
    """
    Test basic LSP functionality for a given language server.
    
    Usage:
        test_lsp_server('Python')
        test_lsp_server('JavaScript')
        test_lsp_server('C++')
    """
    import cuda_lsp
    
    cmd = cuda_lsp.Command
    if not hasattr(cmd, '_langs'):
        print("ERROR: LSP plugin not initialized")
        return
    
    # Find language ID
    langid = None
    lang = None
    for lid, l in cmd._langs.items():
        if lang_name.lower() in l.lang_str.lower():
            langid = lid
            lang = l
            break
    
    if not lang:
        print(f"ERROR: No LSP server found for {lang_name}")
        print(f"Available: {list(cmd._langs.keys())}")
        return
    
    print(f"\n{'='*60}")
    print(f"Testing LSP Server: {lang.lang_str}")
    print(f"Language ID: {langid}")
    print(f"State: {lang.client_state_str}")
    print(f"{'='*60}\n")
    
    # Test 1: Check if initialized
    if not lang.client.is_initialized:
        print("❌ FAIL: Server not initialized")
        return
    print("✓ Server initialized")
    
    # Test 2: Check capabilities
    if hasattr(lang, 'scfg') and lang.scfg:
        print(f"✓ Server has {len(lang.scfg.capabs)} registered capabilities")
        
        # List key capabilities
        methods = set(cap.method for cap in lang.scfg.capabs if cap.method)
        key_methods = [
            'textDocument/completion',
            'textDocument/hover',
            'textDocument/definition',
            'textDocument/publishDiagnostics'
        ]
        for method in key_methods:
            if method in methods:
                print(f"  ✓ {method}")
            else:
                print(f"  ✗ {method} (not supported)")
    else:
        print("❌ No server capabilities registered")
    
    # Test 3: Check if document is open
    from cudatext import ed
    doc = cmd.book.get_doc(ed)
    
    if not doc:
        print("⚠ No document open for this editor")
    elif doc.lang != lang:
        print(f"⚠ Document is using different server: {doc.lang}")
    else:
        print(f"✓ Document open: {doc.uri}")
    
    # Test 4: Recent messages
    if hasattr(lang, '_dbg_msgs') and lang._dbg_msgs:
        print(f"\n✓ Received {len(lang._dbg_msgs)} messages from server")
        print("  Recent messages:")
        for msg in lang._dbg_msgs[-5:]:
            msg_type = type(msg).__name__
            print(f"    - {msg_type}")
    else:
        print("\n⚠ No debug messages (set DEBUG_MESSAGES=True to enable)")
    
    # Test 5: Check for errors
    if hasattr(lang, '_dbg_msgs'):
        from cuda_lsp.sansio_lsp_client.events import ResponseError
        errors = [msg for msg in lang._dbg_msgs if isinstance(msg, ResponseError)]
        if errors:
            print(f"\n❌ Found {len(errors)} errors:")
            for err in errors[-3:]:
                print(f"    Code {err.code}: {err.message}")
        else:
            print("\n✓ No response errors")
    
    print(f"\n{'='*60}\n")


def test_all_servers():
    """Test all active LSP servers."""
    import cuda_lsp
    
    cmd = cuda_lsp.Command
    if not hasattr(cmd, '_langs') or not cmd._langs:
        print("ERROR: No LSP servers running")
        return
    
    print(f"\nFound {len(cmd._langs)} language server(s)\n")
    
    # Get unique server names
    servers = set(lang.lang_str for lang in cmd._langs.values())
    
    for server_name in servers:
        test_lsp_server(server_name)


def debug_last_message(lang_name=None):
    """Show detailed info about the last LSP message."""
    import cuda_lsp
    import pprint
    
    cmd = cuda_lsp.Command
    if not hasattr(cmd, '_langs'):
        print("ERROR: LSP plugin not initialized")
        return
    
    # Find language
    lang = None
    if lang_name:
        for lid, l in cmd._langs.items():
            if lang_name.lower() in l.lang_str.lower():
                lang = l
                break
    else:
        # Use first available
        lang = next(iter(cmd._langs.values()), None)
    
    if not lang:
        print("ERROR: No LSP server found")
        return
    
    if not hasattr(lang, '_dbg_msgs') or not lang._dbg_msgs:
        print("No messages available. Set DEBUG_MESSAGES=True in language.py")
        return
    
    msg = lang._dbg_msgs[-1]
    print(f"\nLast message type: {type(msg).__name__}")
    print(f"\nMessage details:")
    print("="*60)
    
    try:
        if hasattr(msg, '__dict__'):
            for key, value in msg.__dict__.items():
                if not key.startswith('_'):
                    print(f"{key}:")
                    if isinstance(value, (list, dict)) and value:
                        pprint.pprint(value, indent=2, width=70, depth=2)
                    else:
                        print(f"  {value}")
        else:
            pprint.pprint(msg, width=70, depth=3)
    except Exception as e:
        print(f"Error displaying message: {e}")
        print(str(msg)[:500])


def check_parsing():
    """Check if parsing helpers are working."""
    print("Checking parsing helpers...")
    
    try:
        from cuda_lsp.lsp_modules.sansio_lsp_client._parse_helpers import (
            parse_position, parse_range, parse_location
        )
        print("✓ Parse helpers imported successfully")
        
        # Test parse_position
        pos_dict = {'line': 10, 'character': 5}
        pos = parse_position(pos_dict)
        assert pos.line == 10 and pos.character == 5
        print("✓ parse_position works")
        
        # Test parse_range
        range_dict = {
            'start': {'line': 0, 'character': 0},
            'end': {'line': 1, 'character': 10}
        }
        rng = parse_range(range_dict)
        assert rng.start.line == 0
        print("✓ parse_range works")
        
        print("\n✓ All parsing helpers working correctly")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure _parse_helpers.py is in sansio_lsp_client directory")
    except Exception as e:
        print(f"❌ Parse test failed: {e}")


# Quick test commands
print("""
LSP Validation Commands:
------------------------
test_all_servers()              - Test all running servers
test_lsp_server('Python')       - Test specific server
debug_last_message()            - Show last message details
debug_last_message('Python')    - Show last message for specific server
check_parsing()                 - Verify parsing helpers work

Example:
>>> test_all_servers()
>>> test_lsp_server('C++')
>>> debug_last_message('Python')
""")
