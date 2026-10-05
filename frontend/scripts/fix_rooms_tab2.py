with open("frontend/src/pages/settings/index.jsx", "r") as f:
    content = f.read()

content = content.replace(
    "{isSuperAdmin ? 'grid-cols-7' : isAdmin ? 'grid-cols-6' : 'grid-cols-5'}",
    "{isAdmin ? 'grid-cols-7' : 'grid-cols-5'}"
)

content = content.replace(
    "{isSuperAdmin && <TabsTrigger value=\"rooms\"",
    "{isAdmin && <TabsTrigger value=\"rooms\""
)

content = content.replace(
    "{isSuperAdmin && <SettingsRoomsTab",
    "{isAdmin && <SettingsRoomsTab"
)

with open("frontend/src/pages/settings/index.jsx", "w") as f:
    f.write(content)
print("done")
