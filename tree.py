
from cudatext import *

from .book import EditorDoc

from lsprotocol import types as lsp

SymbolKind = lsp.SymbolKind
DocumentSymbol = lsp.DocumentSymbol
SymbolInformation = lsp.SymbolInformation


KEY_TREE_TYPES_SHOW = 'tree_types_show'
CFG_DEFAULT = 'namespace,class,method,constructor,interface,function,struct'
# all
#CFG_DEFAULT = 'file,module,namespace,package,class,method,property,field,constructor,enum,interface,function,variable,constant,string,number,boolean,array,object,key,null,enummember,struct,event,operator,typeparameter'


tree_icons = {
    'folder':  0,
    'parts1':  1,
    'parts2':  2,
    'parts3':  3,
    'box':     4,
    'func':    5,
    'arrow1':  6,
    'arrow2':  7,
}
KIND_2_TREE_IC = {
    SymbolKind.File:            tree_icons['box'],
    SymbolKind.Module:          tree_icons['box'],
    SymbolKind.Namespace:       tree_icons['box'],
    SymbolKind.Package:         tree_icons['box'],

    SymbolKind.Class:           tree_icons['folder'],
    SymbolKind.Enum:            tree_icons['folder'],
    SymbolKind.Struct:          tree_icons['folder'],

    SymbolKind.Method:          tree_icons['func'],
    SymbolKind.Constructor:     tree_icons['func'],
    SymbolKind.Interface:       tree_icons['func'],
    SymbolKind.Function:        tree_icons['func'],

    SymbolKind.Property:        tree_icons['parts1'],
    SymbolKind.Field:           tree_icons['parts1'],
    SymbolKind.Variable:        tree_icons['parts1'],
    SymbolKind.Constant:        tree_icons['parts1'],
    SymbolKind.String:          tree_icons['parts1'],
    SymbolKind.Number:          tree_icons['parts1'],
    SymbolKind.Boolean:         tree_icons['parts1'],
    SymbolKind.Array:           tree_icons['parts1'],
    SymbolKind.Object:          tree_icons['parts1'],
    SymbolKind.Key:             tree_icons['parts1'],
    SymbolKind.Null:            tree_icons['parts1'],
    SymbolKind.EnumMember:      tree_icons['parts1'],
    SymbolKind.Event:           tree_icons['parts1'],
    SymbolKind.Operator:        tree_icons['parts1'],
    SymbolKind.TypeParameter:   tree_icons['parts1'],
}



def is_child(item, p_item):
    """ only checks range's end - ok for sorted
    """
    item_start = item.location.range.start
    parent_end = p_item.location.range.end

    return item_start.line < parent_end.line  or  \
                item_start.line == parent_end.line  and  item_start.character <  parent_end.character


class TreeMan:
    def __init__(self, cfg):
        # set if SymbolKind's to display in tree
        self.kinds_show = self._load_cfg(cfg)


    def fill_tree(self, items):
        # empty or not hierarchical type
        if not items:
            return

        elif isinstance(items[0], DocumentSymbol):
            self._fill_from_tree(items)

        elif isinstance(items[0], SymbolInformation):
            self._fill_from_list(items)


    def _fill_from_tree(self, items):

        def fill_tree_item(item, parent_id=0): #SKIP
            if not item.kind  or not  item.kind in self.kinds_show:
                return

            # add tree item
            item_id = self.add_tree_item(h_tree,  item.name,  parent_id=parent_id, kind=item.kind,
                                                                                    range_=item.range)

            # process children
            if item.children:
                for chitem in item.children:
                    fill_tree_item(chitem, parent_id=item_id)


        ed.set_prop(PROP_CODETREE, False)

        h_tree = app_proc(PROC_GET_CODETREE, "")
        tree_proc(h_tree, TREE_ITEM_DELETE, id_item=0) # clear tree

        for item in items:
            fill_tree_item(item)

    def _fill_from_list(self, items):
        ed.set_prop(PROP_CODETREE, False)

        h_tree = app_proc(PROC_GET_CODETREE, "")
        tree_proc(h_tree, TREE_ITEM_DELETE, id_item=0) # clear tree

        # remove hidden symbol kinds
        items = [item for item in items  if item.kind in self.kinds_show]
        # sort by start pos
        items.sort(key=lambda item: (item.location.range.start.line,
                                        item.location.range.start.character))

        # fill tree
        _parents = []
        _ids = {}   # id(item) -> tree item_id
        for item in items:
            # find parent in stack
            while _parents:
                p_item = _parents[-1]
                if is_child(item, p_item):  # not parent (sibling), pop, try next
                    parent_id = _ids[id(p_item)]
                    break
                else:
                    _parents.pop()
            else:
                parent_id = 0

            # add tree item
            item_id = self.add_tree_item(h_tree,  item.name,  kind=item.kind,  parent_id=parent_id,
                                                                            range_=item.location.range)

            _parents.append(item)
            _ids[id(item)] = item_id

    def _load_cfg(self, cfg):
        cfg = cfg.get(KEY_TREE_TYPES_SHOW)  or  CFG_DEFAULT

        _name_kind_map = {kind.name.lower():kind  for kind in SymbolKind}
        _types_show = (type_.strip().lower()  for type_ in cfg.lower().split(',')  if type_.strip())
        return set( _name_kind_map.get(type_)  for type_ in _types_show
                                                                if type_ in _name_kind_map)


    @classmethod
    def add_tree_item(cls, h_tree, caption, parent_id, kind, range_):

        # tree item caption
        item_id = tree_proc(h_tree, TREE_ITEM_ADD, id_item=parent_id, index=-1, text=caption)

        _range = EditorDoc.range2carets(range_)
        tree_proc(h_tree, TREE_ITEM_SET_RANGE, id_item=item_id, text=_range)

        _ic_ind = KIND_2_TREE_IC[kind]
        tree_proc(h_tree, TREE_ITEM_SET_ICON, id_item=item_id, image_index=_ic_ind)

        return item_id
