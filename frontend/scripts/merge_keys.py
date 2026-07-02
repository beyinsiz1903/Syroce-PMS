import json
import os

locales_dir = '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/locales'
master_file = os.path.join(locales_dir, 'tr.json')
new_keys_file = '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/scripts/new_keys.json'

with open(new_keys_file, 'r', encoding='utf-8') as f:
    new_keys = json.load(f)

with open(master_file, 'r', encoding='utf-8') as f:
    master_data = json.load(f)

def set_nested(d, path_parts, value):
    for part in path_parts[:-1]:
        if part not in d:
            d[part] = {}
        d = d[part]
    d[path_parts[-1]] = value

for key, val in new_keys.items():
    parts = key.split('.')
    set_nested(master_data, parts, val)

with open(master_file, 'w', encoding='utf-8') as f:
    json.dump(master_data, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f"Merged {len(new_keys)} keys into {master_file}")
