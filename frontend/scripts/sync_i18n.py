import json
import glob
import os

locales_dir = '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/locales'
master_file = os.path.join(locales_dir, 'tr.json')

with open(master_file, 'r', encoding='utf-8') as f:
    master_data = json.load(f)

def sync_dict(master, target):
    for key, value in master.items():
        if key not in target:
            # If the value is a string, copy it. If dict, copy it deeply.
            if isinstance(value, dict):
                target[key] = {}
                sync_dict(value, target[key])
            else:
                target[key] = value
        else:
            if isinstance(value, dict):
                if not isinstance(target[key], dict):
                    target[key] = {}
                sync_dict(value, target[key])
            else:
                # Target has the key and it's a leaf, keep target's value
                pass

for file in glob.glob(os.path.join(locales_dir, '*.json')):
    if file == master_file:
        continue
    
    with open(file, 'r', encoding='utf-8') as f:
        target_data = json.load(f)
        
    sync_dict(master_data, target_data)
    
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(target_data, f, indent=2, ensure_ascii=False)
        # Add a newline at the end
        f.write('\n')

print("Sync completed.")
