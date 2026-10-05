with open("frontend/src/pages/settings/SettingsRoomsTab.jsx", "r") as f:
    content = f.read()

# Replace disabled={!isSuperAdmin} with nothing or disabled={false} (just remove the disabled prop if it relies on isSuperAdmin)
content = content.replace("disabled={!isSuperAdmin}", "")
# Remove titles that say 'Yalnızca süper-admin'
content = content.replace("title={!isSuperAdmin ? 'Yalnızca süper-admin' : undefined}", "")

with open("frontend/src/pages/settings/SettingsRoomsTab.jsx", "w") as f:
    f.write(content)
print("done SettingsRoomsTab")
