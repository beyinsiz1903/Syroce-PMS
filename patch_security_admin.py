import re

with open('frontend/src/routes/sections/securityAdmin.js', 'r') as f:
    content = f.read()

resolved = re.sub(
    r'<<<<<<< HEAD\n    { path: "/gdpr-compliance", ...p\(GDPRCompliance\), wrapLayout: true },\n    { path: "/encryption-management", ...pa\(EncryptionManagementPage\), wrapLayout: true, layoutModule: "encryption_management" },\n=======\n    { path: "/gdpr-compliance", ...moduleRoute\(GDPRCompliance, null, {}, { allowedRoles: \["admin", "super_admin", "general_manager", "gdpr_officer"\] }\), wrapLayout: true },\n    { path: "/encryption-management", ...p\(EncryptionManagementPage\), wrapLayout: true, layoutModule: "encryption_management" },\n>>>>>>> 3db79e9ed \(fix: resolve zincir misafir, sadakat and acenta talepleri requirements\)',
    '    { path: "/gdpr-compliance", ...moduleRoute(GDPRCompliance, null, {}, { allowedRoles: ["admin", "super_admin", "general_manager", "gdpr_officer"] }), wrapLayout: true },\n    { path: "/encryption-management", ...pa(EncryptionManagementPage), wrapLayout: true, layoutModule: "encryption_management" },',
    content
)

with open('frontend/src/routes/sections/securityAdmin.js', 'w') as f:
    f.write(resolved)
