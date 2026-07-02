import os
import re

base_paths = [
    '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/components',
    '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/pages'
]

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if "localStorage.getItem('token')" not in content:
        return

    # 1. Remove the token assignment lines
    content = re.sub(r"^\s*(const|let|var)\s+token\s*=\s*localStorage\.getItem\(['\"]token['\"]\);\s*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"localStorage\.getItem\(['\"]token['\"]\)", "null", content) # just in case there are inline usages

    # 2. Remove the Authorization headers from axios/fetch calls
    # Usually it looks like:
    # headers: {
    #   'Authorization': `Bearer ${token}`
    # }
    # Or:
    # Authorization: `Bearer ${token}`
    
    content = re.sub(r"^\s*['\"]?Authorization['\"]?\s*:\s*`Bearer\s*\$\{?[a-zA-Z0-9_]*\}?`\s*,?\s*$", "", content, flags=re.MULTILINE)

    # 3. If there are empty headers blocks left, like headers: { }, remove them if possible, or just leave them.
    content = re.sub(r"headers\s*:\s*\{\s*\},?", "", content)
    
    # 4. For fetch calls without credentials: "include", we should add it if it's missing.
    # But this is risky with a simple regex. 
    # Let's just fix the axios ones first, and for fetch we can manually review or try to inject.
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Processed {filepath}")

for base_path in base_paths:
    for root, _, files in os.walk(base_path):
        for file in files:
            if file.endswith('.jsx') or file.endswith('.js'):
                process_file(os.path.join(root, file))
