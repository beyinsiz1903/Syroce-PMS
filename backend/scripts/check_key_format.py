import os


def check_key(name):
    val = os.environ.get(name)
    if not val:
        print(f"{name}: NOT SET")
        return

    length = len(val)
    stripped_length = len(val.strip())
    has_spaces = " " in val
    has_newlines = "\n" in val

    print(f"{name}: length={length}, stripped_length={stripped_length}, has_spaces={has_spaces}, has_newlines={has_newlines}")

    if length != stripped_length:
        print(f"  -> WARNING: {name} contains leading or trailing whitespace!")

check_key("CM_MASTER_KEY_CURRENT")
check_key("CM_MASTER_KEY_PREVIOUS")
