import re

with open("frontend/src/components/pms/BulkRoomsDialog.jsx", "r") as f:
    content = f.read()

# Replace:
# const isSuperAdmin = user?.role === 'super_admin' || (Array.isArray(user?.roles) && user.roles.includes('super_admin'));
# With:
# const isAdmin = user?.role === 'admin' || (Array.isArray(user?.roles) && user.roles.includes('admin')) || user?.role === 'super_admin' || (Array.isArray(user?.roles) && user.roles.includes('super_admin'));
content = content.replace(
    "const isSuperAdmin = user?.role === 'super_admin' || (Array.isArray(user?.roles) && user.roles.includes('super_admin'));",
    "const isAdmin = user?.role === 'super_admin' || (Array.isArray(user?.roles) && user.roles.includes('super_admin')) || user?.role === 'admin' || (Array.isArray(user?.roles) && user.roles.includes('admin'));"
)

# Replace all occurrences of !isSuperAdmin with !isAdmin
content = content.replace("!isSuperAdmin", "!isAdmin")

# Remove "yalnızca süper-admin" messages
content = content.replace(
    "Oda oluşturma yetkisi yalnızca süper-admin kullanıcılara aittir.",
    "Oda oluşturma yetkisi yöneticilere aittir."
)
content = content.replace(
    "Toplu oda oluşturma işlemi yalnızca süper-admin kullanıcılar tarafından yapılabilir.",
    "Toplu oda oluşturma işlemi yönetici yetkisi gerektirir."
)

with open("frontend/src/components/pms/BulkRoomsDialog.jsx", "w") as f:
    f.write(content)

print("done")
