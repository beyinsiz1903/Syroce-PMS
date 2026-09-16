import re

with open("frontend/src/pages/settings/index.jsx", "r") as f:
    content = f.read()

# Fix grid-cols logic:
# If both B2B and Rooms are shown to admin, the count changes.
# Before: isSuperAdmin ? 'grid-cols-7' : isAdmin ? 'grid-cols-6' : 'grid-cols-5'
# Now: isAdmin ? 'grid-cols-7' : 'grid-cols-5'
content = re.sub(
    r"isSuperAdmin \? 'grid-cols-7' : isAdmin \? 'grid-cols-6' : 'grid-cols-5'",
    r"isAdmin ? 'grid-cols-7' : 'grid-cols-5'",
    content
)

# Fix TabsTrigger condition
content = re.sub(
    r"\{isSuperAdmin && <TabsTrigger value=\"rooms\"",
    r"{isAdmin && <TabsTrigger value=\"rooms\"",
    content
)

# Fix SettingsRoomsTab condition
content = re.sub(
    r"\{isSuperAdmin && <SettingsRoomsTab(.*?)isSuperAdmin=\{isSuperAdmin\}(.*?)\}",
    r"{isAdmin && <SettingsRoomsTab\1isSuperAdmin={isAdmin}\2}",
    content
)
# Wait, the regex might be tricky if it's multiline or has spaces. Let's just use string replace.
