import os
import re

base_paths = [
    '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/components',
    '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/pages'
]

def find_missing_toasts():
    found_files = []
    for base_path in base_paths:
        for root, _, files in os.walk(base_path):
            for file in files:
                if file.endswith('.jsx') or file.endswith('.js'):
                    filepath = os.path.join(root, file)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Find catch blocks that have console.error/warn but no toast or alert
                    # Also .catch(...) with console.warn
                    
                    catch_blocks = re.findall(r'catch\s*\([^\)]*\)\s*\{([^}]*)\}', content)
                    catch_methods = re.findall(r'\.catch\s*\([^\)]*\)\s*\{([^}]*)\}', content)
                    
                    for block in (catch_blocks + catch_methods):
                        if ('console.error' in block or 'console.warn' in block) and ('toast' not in block and 'alert' not in block):
                            found_files.append(filepath)
                            break
    return found_files

files = find_missing_toasts()
for f in files:
    print(f)
