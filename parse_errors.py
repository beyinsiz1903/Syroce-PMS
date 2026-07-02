import re

log_file = "/Users/syroce/.gemini/antigravity/brain/7d088073-f87e-40c6-a7d6-845fb4faf735/.system_generated/tasks/task-15738.log"

with open(log_file, "r") as f:
    lines = f.readlines()

fails = []
in_error = False
current_error = []
current_test = ""

for line in lines:
    if line.startswith("  ") and line.strip().endswith(" failed"):
        break
    
    if "  " + u'\u2716' in line or ("  " in line and " › " in line and (" failed" in line or " [stress] " in line) and not (" ✓ " in line or " - " in line or line.strip().endswith("passed"))):
        if not in_error and "Error:" not in line:
            current_test = line.strip()
            
    if "Error: " in line:
        if not in_error:
            in_error = True
            current_error.append(current_test)
        current_error.append(line.strip())
    elif in_error:
        if line.strip() == "" and len(current_error) > 2:
            pass 
        if "attachment #" in line or "Usage:" in line or "Error Context:" in line:
            fails.append("\n".join(current_error))
            in_error = False
            current_error = []
        else:
            if len(current_error) < 10:
                current_error.append(line.strip())

with open("fails_summary.md", "w") as f:
    f.write("# Stress Test Failures\n\n")
    for i, err in enumerate(fails):
        f.write(f"### ERROR {i+1}\n```\n{err}\n```\n\n")

