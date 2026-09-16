import re

with open('frontend/src/config/navItems.jsx', 'r') as f:
    content = f.read()

replacements = {
    # id_photo_admin -> operations / guest_requests
    r'(key:\s*"id_photo_admin"[\s\S]*?)navGroup:\s*"system",\s*navSection:\s*"compliance",':
    r'\1navGroup: "operations",\n    navSection: "guest_requests",',
    
    # urgent_permission_admin -> admin / governance
    r'(key:\s*"urgent_permission_admin"[\s\S]*?)navGroup:\s*"system",\s*navSection:\s*"compliance",':
    r'\1navGroup: "admin",\n    navSection: "governance",',
    
    # early_late_pricing -> settings
    r'(key:\s*"early_late_pricing"[\s\S]*?)navGroup:\s*"system",\s*navSection:\s*"distribution",':
    r'\1navGroup: null,',
    
    # help_center -> null
    r'(key:\s*"help_center"[\s\S]*?)navGroup:\s*"system",\s*navSection:\s*"setup",':
    r'\1navGroup: null,',
    
    # academy -> null
    r'(key:\s*"academy"[\s\S]*?)navGroup:\s*"system",\s*navSection:\s*"setup",':
    r'\1navGroup: null,',
    
    # ai_zeka -> guest / marketing
    r'(key:\s*"ai_zeka"[\s\S]*?)navGroup:\s*"system",\s*navSection:\s*"growth",':
    r'\1navGroup: "guest",\n    navSection: "marketing",',
    
    # mailing -> guest / marketing
    r'(key:\s*"mailing"[\s\S]*?)navGroup:\s*"system",\s*navSection:\s*"growth",':
    r'\1navGroup: "guest",\n    navSection: "marketing",',
    
    # onboarding_wizard -> null
    r'(key:\s*"onboarding_wizard"[\s\S]*?)navGroup:\s*"system",\s*navSection:\s*"setup",':
    r'\1navGroup: null,',
    
    # module_store -> null
    r'(key:\s*"module_store"[\s\S]*?)navGroup:\s*"system",\s*navSection:\s*"setup",':
    r'\1navGroup: null,',
    
    # pci_compliance -> admin / governance
    r'(key:\s*"pci_compliance"[\s\S]*?)navGroup:\s*"system",\s*navSection:\s*"compliance",':
    r'\1navGroup: "admin",\n    navSection: "governance",',
    
    # xchange -> admin / platform
    r'(key:\s*"xchange"[\s\S]*?)navGroup:\s*"system",\s*navSection:\s*"integrations",':
    r'\1navGroup: "admin",\n    navSection: "platform",',
    
    # go_live_readiness -> null
    r'(key:\s*"go_live_readiness"[\s\S]*?)navGroup:\s*"system",':
    r'\1navGroup: null,',
}

new_content = content
for pattern, repl in replacements.items():
    new_content = re.sub(pattern, repl, new_content)

if new_content != content:
    with open('frontend/src/config/navItems.jsx', 'w') as f:
        f.write(new_content)
    print("Replacements applied successfully.")
else:
    print("No changes made.")

