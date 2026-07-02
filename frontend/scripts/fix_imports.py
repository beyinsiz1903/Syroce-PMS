import os
import re

dirs = ['hr', 'settings', 'maintenance']
base_path = '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/pages'

for d in dirs:
    index_file = os.path.join(base_path, d, 'index.jsx')
    if not os.path.exists(index_file): continue
    
    with open(index_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract all imports
    imports = []
    for line in content.split('\n'):
        if line.startswith('import ') and not line.startswith('import { useTranslation }'):
            # Filter out the internal tab imports
            if not line.endswith("Tab';") and not line.endswith("Modal';"):
                imports.append(line)
    
    import_block = '\n'.join(imports) + '\n'
    
    # Find all generated files in the directory
    for file in os.listdir(os.path.join(base_path, d)):
        if file.endswith('.jsx') and file != 'index.jsx':
            filepath = os.path.join(base_path, d, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            if '// You may need to fix imports manually' in file_content:
                new_content = file_content.replace('// You may need to fix imports manually (Lucide icons, UI components)\n', import_block)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Fixed imports for {filepath}")

