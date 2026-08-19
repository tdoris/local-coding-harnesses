import json
import sys
import copy

def decode_pointer_part(part):
    """RFC 6901: '~1' decodes to '/', '~0' to '~'"""
    return part.replace('~1', '/').replace('~0', '~')

def parse_pointer(pointer):
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError("JSON Pointer must start with '/' or be empty")
    
    parts = []
    # The pointer is /part0/part1/...
    # Split by '/' and skip the first empty string from the leading '/'
    raw_parts = pointer[1:].split("/")
    for part in raw_parts:
        parts.append(decode_pointer_part(part))
    return parts

def get_target_and_parent(root, path_parts):
    """
    Navigates the root object according to path_parts.
    Returns (parent, key_or_index, target_node)
    where key_or_index is the last part of the path.
    """
    if not path_parts:
        return None, None, root

    current = root
    parent = None
    last_key = None
    
    for i, part in enumerate(path_parts):
        parent = current
        last_key = part
        
        if isinstance(current, list):
            if part == "-":
                # '-' is special for 'add' at the end.
                # If it's used in the middle of a path, it's an error.
                if i < len(path_parts) - 1:
                    raise ValueError("'-' is only valid as an add target or end of array index")
                # We'll handle '-' specifically in the operations.
                # For navigation, we'll treat it as the index equal to len(current).
                # This will be handled by the caller.
                break
            try:
                if not part.isdigit() or (len(part) > 1 and part[0] == '0'):
                    raise ValueError("Invalid array index")
                idx = int(part)
                if idx < 0 or idx >= len(current):
                    raise ValueError("Index out of range")
                current = current[idx]
            except (ValueError, IndexError):
                raise ValueError("Invalid array index")
        elif isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                raise ValueError("Path component not found")
        else:
            raise ValueError("Cannot traverse through non-container type")
            
    return parent, last_key, current

def apply_patch(doc, patch):
    if not isinstance(patch, list):
        raise ValueError("Patch must be an array")
    
    # Use a deep copy to ensure atomicity
    new_doc = copy.deepcopy(doc)
    
    for op_obj in patch:
        if not isinstance(op_obj, dict):
            raise ValueError("Operation must be an object")
        
        if 'op' not in op_obj or 'path' not in op_obj:
            raise ValueError("Operation must contain 'op' and 'path'")
        
        op = op_obj['op']
        path_str = op_obj['path']
        path_parts = parse_pointer(path_str)
        
        if op == 'add':
            if 'value' not in op_obj:
                raise ValueError("'add' requires '<0xA0>'value'")
            value = op_obj['value']
            
            if not path_parts:
                raise ValueError("Cannot add to the root")
            
            # Special case for adding to the root of an array or object is not really defined by RFC 6902,
            # but path_parts being empty means the target is the root itself.
            # However, the 'path' must be a JSON pointer.
            
            parent_parts = path_parts[:-1]
            if not parent_parts:
                parent = new_doc
                key_or_idx = path_parts[0]
            else:
                parent, _, _ = get_target_and_parent(new_doc, parent_parts)
                key_or_idx = path_parts[-1]
            
            if isinstance(parent, dict):
                parent[key_or_idx] = value
            elif isinstance(parent, list):
                if key_or_idx == "-":
                    parent.append(value)
                else:
                    try:
                        if not key_or_idx.isdigit() or (len(key_or_idx) > 1 and key_or_idx[0] == '0'):
                            raise ValueError("Invalid array index")
                        idx = int(key_or_idx)
                        if idx < 0 or idx > len(parent):
                            raise ValueError("Index out of range")
                        parent.insert(idx, value)
                    except (ValueError, IndexError):
                        raise ValueError("Invalid array index")
            else:
                raise ValueError("Parent is not a container")

        elif op == 'remove':
            if not path_parts:
                raise ValueError("Cannot remove the root")
            
            parent_parts = path_parts[:-1]
            if not parent_parts:
                parent = new_doc
                key_or_idx = path_parts[0]
            else:
                parent, _, _ = get_target_and_parent(new_doc, parent_parts)
                key_or_idx = path_parts[-1]
                
            if isinstance(parent, dict):
                if key_or_idx not in parent:
                    raise ValueError("Path component not found")
                del parent[key_or_idx]
            elif isinstance(parent, list):
                try:
                    if not key_or_idx.isdigit() or (len(key_or_idx) > 1 and key_or_idx[0] == '0'):
                        raise ValueError("Invalid array index")
                    idx = int(key_or_idx)
                    if idx < 0 or idx >= len(parent):
                        raise ValueError("Index out of range")
                    parent.pop(idx)
                except (ValueError, IndexError):
                    raise ValueError("Invalid array index")
            else:
                raise ValueError("Parent is not a container")

        elif op == 'replace':
            if 'value' not in op_obj:
                raise ValueError("'replace' requires 'value'")
            value = op_obj['value']
            
            if not path_parts:
                raise ValueError("Cannot replace the root")
            
            parent_parts = path_parts[:-1]
            if not parent_parts:
                parent = new_doc
                key_or_idx = path_parts[0]
            else:
                parent, _, _ = get_target_and_parent(new_doc, parent_parts)
                key_or_idx = path_parts[-1]
            
            if isinstance(parent, dict):
                if key_or_idx not in parent:
                    raise ValueError("Path component not found")
                parent[key_or_idx] = value
            elif isinstance(parent, list):
                try:
                    if not key_or_idx.isdigit() or (len(key_or_idx) > 1 and key_or_idx[0] == '0'):
                        raise ValueError("Invalid array index")
                    idx = int(key_or_idx)
                    if idx < 0 or idx >= len(parent):
                        raise ValueError("Index out of range")
                    parent[idx] = value
                except (ValueError, IndexError):
                    raise ValueError("Invalid array index")
            else:
                raise ValueError("Parent is not a container")

        elif op == 'move':
            if 'from' not in op_obj:
                raise ValueError("'move' requires 'from'")
            from_path_str = op_obj['from']
            from_path_parts = parse_pointer(from_path_str)
            
            # Check for moving into one's own child
            # If from_path_parts is a prefix of path_parts, and path_parts is longer.
            if len(from_path_parts) <= len(path_parts) and path_parts[:len(from_path_parts)] == from_path:
                # Wait, path_parts is the target path. If from_path is an ancestor of target path, 
                # then we are moving the ancestor into its own descendant.
                # This is only possible if from_path_parts is a prefix of path_parts.
                # But wait, it's more than that. We also need to check if the target node is 
                # an ancestor of the from node. 
                pass
            
            # Correct self-reference check:
            # If from_path_parts is a prefix of path_parts AND len(path_parts) > len(from_path_parts)
            # OR if path_parts is a prefix of from_path_parts AND len(from_path_parts) > len(path_parts)
            # (The second case is actually handled by the 'remove' logic if we implement it as remove then add)
            # But the requirement specifically says: "moving a location into one of its own children".
            # This means the 'from' node is an ancestor of the 'path' node.
            if len(from_path_parts) < len(path_parts) and path_parts[:len(from_path_parts)] == from_path_parts:
                raise ValueError("Moving a location into one of its 'own' children")
            
            # We'll implement move as remove then add.
            # To ensure atomicity, we'll handle it within the loop.
            # But we must be careful: if we use 'remove' and 'add' logic, we might violate 
            # the 'from' existence or 'path' existence if we're not careful.
            # Actually, we can just use the 'remove' and 'add' logic directly.
            
            # However, we need to capture the value first because 'remove' will change the document.
            # Let's find the value to move.
            if not from_path_str:
                raise ValueError("Cannot move the root")
            
            # We need to find the value at from_path_parts.
            # This is tricky because the document is changing.
            # But since we're doing it atomically on a copy, it's fine.
            
            # 1. Find the value to move.
            # We need to use the original doc or the current new_doc? 
            # The patch is applied to the document as it is after previous operations.
            # So we use new_doc.
            
            # Let's find the value at from_path.
            # We can't use get_target_and_parent directly because from_path might be an array index.
            # Let's reuse the logic.
            try:
                # We'll use a helper to get the value at path.
                val_to_move = None
                if not from_path_parts:
                    raise ValueError("Cannot move the root")
                
                # Find the value.
                # To avoid issues with 'remove' changing the structure, we find it first.
                # But we must ensure it still exists.
                
                # Let's use a simplified approach: 
                # 1. Check if 'from' exists.
                # 2. Check if 'path' is valid (if it's 'add', it's valid if parent exists).
                # 3. Get the value.
                # 4. Remove the 'from' node.
                # 5. Add the value to 'path'.
                
                # To find the value:
                temp_parent_parts = from_path_parts[:-1]
                if not temp_parent_parts:
                    temp_parent = new_doc
                    temp_key = from_path_parts[0]
                else:
                    temp_parent, _, _ = get_target_and_parent(new_doc, temp_parent_parts)
                    temp_key = from_path_parts[-1]
                
                if isinstance(temp_parent, dict):
                    if temp_key not in temp_parent:
                        raise ValueError("From path component not found")
                    val_to_move = temp_parent.pop(temp_key)
                elif isinstance(temp_parent, list):
                    try:
                        if not temp_key.isdigit() or (len(temp_key) > 1 and temp_key[0] == '0'):
                            raise ValueError("Invalid array index")
                        idx = int(temp_key)
                        if idx < 0 or idx >= len(temp_parent):
                            raise ValueError("Index out of range")
                        val_to_move = temp_parent.pop(idx)
                    except (ValueError, IndexError):
                        raise ValueError("Invalid array index")
                else:
                    raise ValueError("Parent of 'from' is not a container")
                
                # Now add the value to 'path'.
                # But wait, we already have the 'add' logic. 
                # We can just create a temporary 'add' operation object and call a helper.
                # However, we must use the updated new_doc.
                
                # Let's use a mini-add function.
                # (Implementation below)
                
                # ...
                pass
            except Exception as e:
                raise e

        elif op == 'copy':
            if 'from' not in op_obj:
                raise ValueError("'copy' requires 'from'")
            from_path_str = op_obj['from']
            from_path_parts = parse_pointer(from_path_str)
            
            if not from_path_parts:
                raise ValueError("Cannot copy the root")
            
            # 1. Find the value to copy.
            # 2. Add it to 'path'.
            
            # ... (implementation below)
            pass

        elif op == 'test':
            if 'value' not in op_obj:
                raise ValueError("'test' requires 'value'")
            test_value = op_obj['value']
            
            if not path_parts:
                raise ValueError("Cannot test the root")
            
            # Find the value at path.
            parent_parts = path_parts[:-1]
            if not parent_parts:
                parent = new_doc
                key_or_idx = path_parts[0]
            else:
                parent, _, _ = get_target_and_parent(new_doc, parent_parts)
                key_or_idx = path_parts[-1]
            
            if isinstance(parent, dict):
                if key_or_idx not in parent:
                    raise ValueError("Path component not found")
                actual_value = parent[key_or_idx]
            elif isinstance(parent, list):
                try:
                    if not key_or_idx.isdigit() or (len(key_or_idx) > 1 and key_or_idx[0] == '0'):
                        raise ValueError("Invalid array index")
                    idx = int(key_or_idx)
                    if idx < 0 or idx >= len(parent):
                        raise ValueError("Index out of range")
                    actual_value = parent[idx]
                except (ValueError, IndexError):
                    raise ValueError("Invalid array index")
            else:
                raise ValueError("Parent is not a container")
            
            # JSON equality check
            if not self_contained_json_equality(actual_value, test_value):
                raise ValueError("Test failed")

        elif op not in ['add', 'remove', 'replace', 'move', 'copy', 'test']:
            raise ValueError(f"Unknown operation: {op}")
        
        # To avoid code duplication, I'll move the logic for 'add' to a helper.
        # ...
        pass

    return new_doc

def self_contained_json_equality(a, b):
    # JSON equality: 
    # - Objects: irrespective of key order
    # - Arrays: in order
    # - Numbers: by numeric value (1 == 1.0)
    # - Strings/Booleans/Null: by exact type
    
    if type(a) is not type(b):
        # Special case for numbers: 1 == 1.0
        if isinstance(a, (int, float)) and isinstance(s, (int, float)): # typo: 's' should be 'b'
            pass
        # Let's do it properly.
        pass
    # ...
    return False # placeholder

# I will rewrite this one more time, properly.
