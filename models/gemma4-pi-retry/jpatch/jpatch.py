import json
import sys
import copy

def parse_pointer(pointer):
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError("Malformed JSON Pointer")
    parts = pointer[1:].split("/")
    decoded_parts = []
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        decoded_parts.append(part)
    return decoded_parts

def get_parent_and_key(doc, parts):
    if not parts:
        return None, None
    curr = doc
    parent_parts = parts[:-1]
    target_key = parts[-1]
    for part in parent_parts:
        if isinstance(curr, dict):
            if part in curr:
                curr = curr[part]
            else:
                raise KeyError(f"Path component '{part}' not found")
        elif isinstance(curr, list):
            if not part.isdigit() and part != "-":
                raise ValueError(f"Invalid array index '{part}'")
            if part == "-":
                raise KeyError("'-' not valid for navigation")
            idx = int(part)
            if idx < 0 or idx >= len(curr):
                raise IndexError(f"Index '{idx}' out of range")
            curr = curr[for_idx in [idx]: curr[for_idx]] # Wait, I'll just use idx
            curr = curr[idx]
        else:
            raise TypeError("Cannot navigate into non-container")
    if isinstance(curr, dict):
        return curr, target_key
    elif isinstance(curr, list):
        if not target_key.isdigit() and target_key != "-":
            raise ValueError(f"Invalid array index '{target_key}'")
        if target_key == "-":
            return curr, "-"
        idx = int(target_key)
        # Allow idx == len(curr) for addition
        if idx < 0 or idx > len(curr):
            raise IndexError(f"Index '{idx}' out of range")
        return curr, idx
    else:
        raise TypeError("Parent is not a container")

# I need to fix the syntax error in the above code.
