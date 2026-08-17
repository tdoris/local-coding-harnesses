import json
import sys

def decode_pointer(path):
    if not path:
        return []
    parts = []
    for part in path.split('/')[1:]:
        parts.append(part.replace('~1', '/').replace('~0', '~'))
    return parts

def get_value_at_path(doc, path_parts):
    curr = doc
    for part in path_parts:
        try:
            if isinstance(curr, list):
                idx = int(part)
                curr = curr[idx]
            elif isinstance(curr, dict):
                curr = curr[part]
            else:
                raise ValueError("Not a container")
        except (IndexError, KeyError, ValueError, TypeError):
            raise ValueError(f"Path not found: {path_parts}")
    return curr

def get_parent_and_key(doc, path_parts):
    if not path_parts:
        return None, None, None # Root is special
    
    curr = doc
    parent_path = []
    for i in range(len(path_parts) - 1):
        part = path_parts[i]
        try:
            if isinstance(curr, list):
                idx = int(part)
                curr = curr[idx]
            elif isinstance(curr, dict):
                curr = curr[part]
            else:
                raise ValueError("Not a container")
            parent_path.append(part)
        except (IndexError, KeyError, ValueError, TypeError):
            raise ValueError(format_path_error(path_parts))
            
    last_part = path_parts[-1]
    
    # Determine if the last part is an index or a key
    key = last_part
    if isinstance(curr, list):
        try:
            key = int(last_part)
        except ValueError:
            raise ValueError("Invalid array index")
            
    return curr, parent_path, key

def format_path_error(path_parts):
    return f"Path error at: {'/' + '/'.join(path_parts).replace('/', '~1').replace('~', '~0')}"

def apply_patch(doc, patch):
    # Work on a copy to ensure atomicity
    import copy
    new_doc = copy.deepcopy(doc)
    
    for op_data in patch:
        if not isinstance(op_data, dict) or 'op' not in op_data:
            raise ValueError("Invalid patch operation")
        
        op = op_data['op']
        path_str = op_data.get('path', '')
        path_parts = decode_pointer(path_str)
        
        if op == 'test':
            val = get_value_at_path(new_doc, path_parts)
            if val != op_data['value']:
                raise ValueError(f"Test failed at {path_str}")
        
        elif op == 'remove':
            parent, parent_parts, key = get_parent_and_key(new_or_root_logic(new_doc, path_parts)) # Wait, I need a better way
            # Let's refine the logic.
            pass
    # ... (Rest of implementation)
