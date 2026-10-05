import re

with open('frontend/src/config/navItems.jsx', 'r') as f:
    content = f.read()

resolved = re.sub(
    r'<<<<<<< HEAD\n    key: "tenant_users",\n    label: "Otel Kullanıcıları",\n    path: "/admin/otel-kullanicilari",\n    tier: "basic",\n    group: "core",\n    navGroup: "admin",\n    navSection: "governance",\n    allowedRoles: \["admin", "super_admin"\],\n=======\n    key: "gdpr_compliance",\n    label: "KVKK ve Veri Koruma",\n    path: "/gdpr-compliance",\n    tier: "basic",\n    group: "admin",\n    navGroup: "admin",\n    navSection: "security_compliance",\n    allowedRoles: \["admin", "super_admin", "general_manager", "gdpr_officer"\],\n>>>>>>> 3db79e9ed \(fix: resolve zincir misafir, sadakat and acenta talepleri requirements\)',
    '    key: "gdpr_compliance",\n    label: "KVKK ve Veri Koruma",\n    path: "/gdpr-compliance",\n    tier: "basic",\n    group: "admin",\n    navGroup: "admin",\n    navSection: "security_compliance",\n    allowedRoles: ["admin", "super_admin", "general_manager", "gdpr_officer"],\n  },\n  {\n    key: "tenant_users",\n    label: "Otel Kullanıcıları",\n    path: "/admin/otel-kullanicilari",\n    tier: "basic",\n    group: "core",\n    navGroup: "admin",\n    navSection: "governance",\n    allowedRoles: ["admin", "super_admin"],',
    content
)

with open('frontend/src/config/navItems.jsx', 'w') as f:
    f.write(resolved)
