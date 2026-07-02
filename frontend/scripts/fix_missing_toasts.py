import os
import re

base_paths = [
    '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/components',
    '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/pages'
]

def fix_missing_toasts(limit=10):
    fixed_count = 0
    for base_path in base_paths:
        for root, _, files in os.walk(base_path):
            for file in files:
                if fixed_count >= limit:
                    return
                if file.endswith('.jsx') or file.endswith('.js'):
                    filepath = os.path.join(root, file)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Find catch blocks that have console.error/warn but no toast or alert
                    # Also .catch(...) with console.warn/error
                    
                    catch_blocks = re.findall(r'(catch\s*\([^\)]*\)\s*\{)([^}]*)(\})', content)
                    catch_methods = re.findall(r'(\.catch\s*\([^\)]*\)\s*\{)([^}]*)(\})', content)
                    
                    modified = False
                    new_content = content
                    
                    for pre, block, post in (catch_blocks + catch_methods):
                        if ('console.error' in block or 'console.warn' in block) and ('toast' not in block and 'alert' not in block and 'return' not in block):
                            # Replace the block
                            original = pre + block + post
                            replacement = pre + block + "\n      toast.error('İşlem başarısız oldu');\n    " + post
                            new_content = new_content.replace(original, replacement, 1)
                            modified = True

                    if modified:
                        # Ensure toast is imported
                        if "import { toast }" not in new_content and "import {toast}" not in new_content:
                            new_content = re.sub(r'(import .*;\n)', r"\1import { toast } from 'sonner';\n", new_content, count=1)
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        print(f"Fixed missing toast in {file}")
                        fixed_count += 1

fix_missing_toasts(10)
