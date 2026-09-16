import re

with open("frontend/src/pages/ChannelConnections.jsx", "r") as f:
    content = f.read()

# Replace `if (!isSuperAdmin) {` with `if (!isAdmin) {`
content = content.replace("if (!isSuperAdmin) {", "if (!isAdmin) {")

# Also ensure isAdmin is defined if it wasn't
if "const isAdmin =" not in content:
    content = content.replace(
        "const isSuperAdmin = user?.role === 'super_admin' || (Array.isArray(user?.roles) && user.roles.includes('super_admin'));",
        "const isSuperAdmin = user?.role === 'super_admin' || (Array.isArray(user?.roles) && user.roles.includes('super_admin'));\n  const isAdmin = isSuperAdmin || user?.role === 'admin' || (Array.isArray(user?.roles) && user.roles.includes('admin'));"
    )
    content = content.replace(
        "const isSuperAdmin = user?.role === 'super_admin' || Array.isArray(user?.roles) && user.roles.includes('super_admin');",
        "const isSuperAdmin = user?.role === 'super_admin' || Array.isArray(user?.roles) && user.roles.includes('super_admin');\n  const isAdmin = isSuperAdmin || user?.role === 'admin' || Array.isArray(user?.roles) && user.roles.includes('admin');"
    )

with open("frontend/src/pages/ChannelConnections.jsx", "w") as f:
    f.write(content)
print("done")
