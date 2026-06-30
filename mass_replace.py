import os
import re

directories_to_scan = [
    'backend', 'frontend', 'mobile', 'scripts', 'docs', '.github', 'extension'
]

files_to_scan = [
    '.gitignore', '.trivyignore', '.gitconfig', 'README.md', 'package.json'
]

replacements = [
    (r'https://secure-key-registry\.preview\.emergentagent\.com', 'https://test-api.syroce.local'),
    (r'secure-key-registry\.preview\.emergentagent\.com', 'test-api.syroce.local'),
    (r'emergentagent\.com', 'test-api.syroce.local'),
    (r'https://emergent-yeni-uygulama-1\.replit\.app', 'https://pms.syroce.com'),
    (r'https://emergent-yeni-uygulama-1-syroce\.replit\.app', 'https://www.pms.syroce.com'),
    (r'emergent-yeni-uygulama-1\.replit\.app', 'pms.syroce.com'),
    (r'emergent-yeni-uygulama-1-syroce\.replit\.app', 'www.pms.syroce.com'),
    (r'emergent-yeni-uygulama', 'syroce-pms'),
    (r'emergent\.sh', 'syroce.com'),
    (r'emergent-agent-e1', 'syroce-dev'),
    (r'REPLIT_DEV_DOMAIN_HTTPS', 'CLOUD_DEV_DOMAIN_HTTPS'),
    (r'REPLIT_DEV_DOMAIN', 'CLOUD_DEV_DOMAIN'),
    (r'REPLIT_DEPLOYMENT', 'CLOUD_DEPLOYMENT'),
    (r'REPL_ID', 'CLOUD_INSTANCE_ID'),
    (r'Replit autoscale', 'Cloud autoscale'),
    (r'Replit deployment', 'DigitalOcean deployment'),
    (r'Replit ortamı', 'DigitalOcean ortamı'),
    (r'Replit workspace', 'Cloud workspace'),
    (r'Replit', 'DigitalOcean'),
    (r'replit\.app', 'syroce.com'),
    (r'replit\.dev', 'syroce.local')
]

def process_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        return # Skip binary files
    
    new_content = content
    for pattern, repl in replacements:
        new_content = re.sub(pattern, repl, new_content)
    
    # Also handle lowercase case-insensitive replit mentions safely (ignoring exact matches replaced above)
    new_content = re.sub(r'\breplit\b', 'digitalocean', new_content, flags=re.IGNORECASE)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated: {filepath}")

def main():
    for f in files_to_scan:
        if os.path.exists(f):
            process_file(f)
            
    for d in directories_to_scan:
        if not os.path.exists(d): continue
        for root, dirs, files in os.walk(d):
            if 'node_modules' in dirs: dirs.remove('node_modules')
            if '.venv' in dirs: dirs.remove('.venv')
            if '__pycache__' in dirs: dirs.remove('__pycache__')
            if 'build' in dirs: dirs.remove('build')
            for name in files:
                filepath = os.path.join(root, name)
                if not filepath.endswith(('.pyc', '.pyo', '.so', '.dll', '.class')):
                    process_file(filepath)

if __name__ == '__main__':
    main()
