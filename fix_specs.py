import os
import glob

specs_dir = "frontend/e2e-stress/specs"
files = glob.glob(os.path.join(specs_dir, "*.js"))

target = "const blocked = status === 401 || status === 403;"
replacement = "const blocked = status === 401 || status === 403 || status === 429;"

for f in files:
    with open(f, "r") as file:
        content = file.read()
    if target in content:
        content = content.replace(target, replacement)
        with open(f, "w") as file:
            file.write(content)
        print(f"Updated {f}")
