import json
import sys
import copy

def decode_pointer(pointer):
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError("JSON Pointer must start with '/' or be empty")
    parts = pointer[1:].split("/")
    decoded_parts = []
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        decoded_parts.append(part)
    return decoded_parts

def get_at_path(doc, path_parts):
    current = doc
    for part in path_parts:
        if isinstance(current, list):
            if not part.isdigit() or (len(part) > 1 and part[0] == '0'):
                raise ValueError("Invalid array index")
            idx = int(part)
            if idx >= len(current):
                raise ValueError("Index out of range")
            current = current[idx]
        elif isinstance(current, dict):
            if part not in current:
                raise ValueError("Path does not resolve")
            current = current[part]
        else:
            raise ValueError("Path does not resolve")
    return current

def get_parent_and_key(doc, path_parts):
    if not path_parts:
        return None, None
    parent_parts = path_parts[:-1]
    key_or_index = path_parts[-1]
    parent = get_at_path(doc, parent_parts)
    return parent, key_or_index

def add_to_path(doc, path_parts, value):
    if not path_parts:
        raise ValueError("Cannot add to the root")
    parent, key_or_index = get_parent_and_key(doc, path_parts)
    if isinstance(parent, list):
        if key_or_index == "-":
            parent.append(value)
        elif key_or_index.isdigit() or (key_or_index != "" and key_or_index.isdigit()):
            if len(key_or_index) > 1 and key_or_index[0] == '0':
                raise ValueError("Invalid array index")
            idx = int(key_or_index)
            if idx == len(parent):
                parent.append(value)
            elif idx < len(parent):
                parent.insert(idx, value)
            else:
                raise ValueError("Index out of range")
        else:
            raise ValueError("Invalid array index")
    elif isinstance(parent, dict):
        if key_or_index in parent:
            # If it exists, we replace it to preserve order or just overwrite
            # However, the spec says add can replace.
            # To preserve order in dict, we should update the existing key.
            parent[key_or_index] = value
        else:
            parent[key_or_index] = value
    else:
        raise ValueError("Target is not a container")

def remove_from_path(doc, path_parts):
    if not path_parts:
        raise ValueError("Cannot remove the root")
    parent, key_or_index = get_parent_and_key(doc, path_parts)
    if isinstance(parent, list):
        if not key_or_index.isdigit() or (len(key_or_index) > 1 and key_or_index[0] == '0'):
            raise ValueError("Invalid array index")
        idx = int(key_or_index)
        if idx >= len(parent):
            raise ValueError("Index out of a range")
        return parent.pop(idx)
    elif isinstance(parent, dict):
        if key_or_index not in parent:
            raise ValueError("Path does not resolve")
        return parent.pop(key_or_index)
    else:
        raise ValueError("Target is not a container")

def apply_patch(doc, patch):
    if not isinstance(patch, list):
        raise ValueError("Patch must be an array")
    
    new_doc = copy.deepcopy(doc)
    
    for op_obj in patch:
        if not isinstance(op_obj, dict):
            raise ValueError("Operation must be an object")
        if "op" not in op_obj or "path" not in op_obj:
            raise ValueError("Operation missing 'op' or 'path'")
        
        op = op_obj["op"]
        path_str = op_obj["path"]
        path_parts = decode_pointer(path_str)
        
        if op == "add":
            if "value" not in op_obj:
                raise ValueError("Operation 'add' missing 'value'")
            add_to_path(new_doc, path_parts, op_obj["value"])
        elif op == "remove":
            remove_from_path(new_doc, path_parts)
        elif op == "replace":
            if "value" not in op_obj:
                raise ValueError("Operation 'replace' missing 'value'")
            if isinstance(parent, dict):
                # To preserve order, we must update the existing key
                # but replace_at_path is not implemented.
                # Let's use a simpler approach: we already have remove and add.
                # But remove/add might change order if not careful.
                # Actually, for dicts, parent[key] = value is enough to preserve order in Python 3.7+
                pass
            remove_from_path(new_doc, path_parts)
            add_to_path(new_doc, path_parts, op_obj["value"])
        elif op == "move":
            if "from" not in op_obj:
                raise ValueError("Operation 'move' missing 'from'")
            from_path_str = op_obj["from"]
            from_path_parts = decode_pointer(from_path_str)
            value = get_at_path(new_doc, from_path_parts)
            remove_from_path(new_doc, from_path_parts)
            add_to_path(new_doc, path_parts, value)
        elif op == "copy":
            if "from" not in op_obj:
                raise ValueError("Operation 'copy' missing 'from'")
            from_path_str = op_obj["from"]
            from_path_parts = decode_pointer(from_path_str)
            value = get_at_path(new_doc, from_path_parts)
            add_to_path(new_doc, path_parts, value)
        elif op == "test":
            if "value" not in op_obj:
                raise ValueError("Operation 'test' missing 'value'")
            actual_value = get_at_path(new_doc, path_parts)
            if actual_value != op_obj["value"]:
                raise ValueError("Test failed")
        else:
            raise ValueError(f"Unknown operation: {op}")
            
    return new_doc

def main():
    if len(sys.argv) != 3:
        print("Usage: jpatch.py <doc.json> <patch.json>", file=sys.stderr)
        sys.exit(1)
        
    doc_path = sys.argv[1]
    patch_path = sys.argv[2]
    
    try:
        with open(doc_path, 'r') as f:
            doc = json.load(f)
        with open(patch_path, 'r') as f:
            patch = json.load(f)
            
        result = apply_patch(doc, patch)
        print(json.dumps(result, sort_keys=False))
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
