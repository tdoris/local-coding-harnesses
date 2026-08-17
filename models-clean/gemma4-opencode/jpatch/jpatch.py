import json
import sys
import copy

def decode_pointer(path):
    """Decodes a JSON Pointer into a list of path components."""
    if path == "":
        return []
    # Split by '/', but handle the leading '/'
    parts = path.split("/")
    if path.startswith("/"):
        parts = parts[1:]
    # Handle ~1 and ~0 escaping
    return [p.replace("~1", "/").replace("~0", "~") for p in parts]

def get_node_at_path(doc, path_parts):
    """Navigates to the node at the specified path components."""
    current = doc
    for part in path_parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                raise KeyError(f"Path component '{part}' not found in dict")
        elif isinstance(current, list):
            try:
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    raise IndexError(f"Index {idx} out of range")
            except ValueError:
                raise KeyError(f"Invalid list index '{part}'")
        else:
            raise KeyError(f"Cannot traverse into non-container type at '{part}'")
    return current

def get_parent_and_key(doc, path_parts):
    """Returns the parent container, the key/index, and the parent path parts."""
    if not path_parts:
        return None, None, None
    
    parent_parts = path_parts[:-1]
    last_part = path_parts[-1]
    
    if not parent_parts:
        parent = doc
    else:
        parent = get_node_at_path(doc, parent_parts)
    
    return parent, last_part, parent_parts

def apply_patch(doc, patch):
    """Applies a JSON Patch (RFC 6902) to a JSON document."""
    new_doc = copy.deepcopy(doc)
    
    for op_data in patch:
        op = op_data.get("op")
        path = op_data.get("path", "")
        path_parts = decode_pointer(path)
        
        if op == "test":
            expected_value = op_data.get("value")
            actual_value = get_node_at_path(new_doc, path_parts)
            if actual_value != expected_value:
                raise ValueError(f"Test failed: expected {expected_value}, got {actual_value}")
        
        elif op == "remove":
            if not path_parts:
                raise ValueError("Cannot remove the whole document")
            parent, key, _ = get_parent_and_key(new_doc, path_parts)
            if isinstance(parent, dict):
                if key in parent:
                    del parent[key]
                else:
                    raise KeyError(f"Key '{key}' not found")
            elif isinstance(parent, list):
                try:
                    idx = int(key)
                    parent.pop(idx)
                except (ValueError, IndexError):
                    raise KeyError(f"Invalid or out-of-range index '{key}'")
            else:
                raise KeyError("Cannot remove from non-container")
                
        elif op == "add":
            value = op_data.get("value")
            if not path_parts:
                new_doc = value
            else:
                parent, key, _ = get_parent_and_key(new_doc, path_parts)
                if isinstance(parent, dict):
                    parent[key] = value
                elif isinstance(parent, list):
                    try:
                        if key == "-":
                            parent.append(value)
                        else:
                            idx = int(key)
                            parent.insert(idx, value)
                    except (ValueError, IndexError):
                        raise KeyError(f"Invalid or out-of-range index '{key}'")
                else:
                    raise KeyError("Cannot add to non-container")
                    
        elif op == "replace":
            if not path_parts:
                raise ValueError("Cannot replace the whole document")
            value = op_data.get("value")
            parent, key, _ = get_parent_and_key(new_doc, path_parts)
            if isinstance(parent, dict):
                parent[key] = value
            elif isinstance(parent, list):
                try:
                    idx = int(key)
                    parent[idx] = value
                except (ValueError, IndexError):
                    raise KeyError(f"Invalid or out-of-range index '{key}'")
            else:
                raise KeyError("Cannot replace in non-container")
                
        elif op == "move":
            from_path = op_data.get("from", "")
            from_parts = decode_pointer(from_path)
            
            # RFC 6902: move is equivalent to copy followed by remove.
            # 1. Copy the value from 'from' to 'path'
            value = get_node_at_path(new_doc, from_parts)
            
            # 2. Perform 'add' at 'path'
            dest_path_parts = decode_pointer(path)
            if not dest_path_parts:
                new_doc = value
            else:
                parent, key, _ = get_parent_and_key(new_doc, dest_path_parts)
                if isinstance(parent, dict):
                    parent[key] = value
                elif isinstance(parent, list):
                    try:
                        if key == "-":
                            parent.append(value)
                        else:
                            idx = int(key)
                            parent.insert(idx, value)
                    except (ValueError, IndexError):
                        raise KeyError(f"Invalid or out-of-range index '{key}'")
                else:
                    raise KeyError("Cannot add to non-container")
            
            # 3. Perform 'remove' from 'from_path'
            if not from_parts:
                raise ValueError("Cannot move the whole document")
            parent_f, key_f, _ = get_parent_and_key(new_doc, from_parts)
            if isinstance(parent_f, dict):
                if key_f in parent_f:
                    del parent_f[key_f]
                else:
                    raise KeyError(f"Key '{key_f}' not found")
            elif isinstance(parent_f, list):
                try:
                    idx_f = int(key_f)
                    parent_f.pop(idx_f)
                except (ValueError, IndexError):
                    raise KeyError(f"Invalid or out-of-range index '{key_f}'")
            else:
                raise KeyError("Cannot remove from non-container")

        elif op == "copy":
            from_path = op_data.get("from", "")
            from_parts = decode_pointer(from_path)
            value = get_node_at_path(new_doc, from_parts)
            
            dest_path_parts = decode_pointer(path)
            if not dest_path_parts:
                new_doc = value
            else:
                parent, key, _ = get_parent_and_key(new_doc, dest_path_parts)
                if isinstance(parent, dict):
                    parent[key] = value
                elif isinstance(parent, list):
                    try:
                        if key == "-":
                            parent.append(value)
                        else:
                            idx = int(key)
                            parent.insert(idx, value)
                    except (ValueError, IndexError):
                        raise KeyError(f"Invalid or out-of-range index '{key}'")
                else:
                    raise KeyError("Cannot add to non-container")
        else:
            raise ValueError(f"Unknown operation: {op}")
            
    return new_doc

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <doc.json> <patch.json>", file=sys.stderr)
        sys.exit(1)
    
    doc_path = sys.argv[1]
    patch_path = sys.argv[2]
    
    try:
        with open(doc_path, 'r') as f:
            doc = json.load(f)
        with open(patch_path, 'r') as f:
            patch = json.load(f)
            
        result = apply_patch(doc, patch)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
