import re

# Fix navItems.jsx
with open("frontend/src/config/navItems.jsx", "r") as f:
    nav_content = f.read()

# For key: "channel_connections", remove requireSuperAdmin: true
nav_content = re.sub(
    r'(key:\s*"channel_connections",.*?)(requireSuperAdmin:\s*true,\s*)',
    r'\1',
    nav_content,
    flags=re.DOTALL
)

with open("frontend/src/config/navItems.jsx", "w") as f:
    f.write(nav_content)

# Fix channelManager.js routes
with open("frontend/src/routes/sections/channelManager.js", "r") as f:
    routes_content = f.read()

routes_content = routes_content.replace(
    "...pa(HotelRunnerIntegration)",
    "...p(HotelRunnerIntegration)"
)
routes_content = routes_content.replace(
    "...pa(ExelyIntegration)",
    "...p(ExelyIntegration)"
)

with open("frontend/src/routes/sections/channelManager.js", "w") as f:
    f.write(routes_content)

print("done")
