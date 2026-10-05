import re
import glob

def fix_file(path):
    with open(path, 'r') as f:
        content = f.read()

    if '{fmtTL' not in content and 'fmtTL(' not in content:
        return

    if 'fmtCurrency' not in content and 'fmtTL' in content:
        content = content.replace('fmtTL,', 'fmtTL, fmtCurrency,')

    # We need to inject `const currency = booking?.currency || "TL";`
    # Let's just find the `export function XXX({ booking... }) {`
    # and `export const XXX = ({ booking... }) => {`
    
    # Simple regex to find `{` after function declaration and add it there
    # But only if it's not already there
    if 'const currency = booking?.currency || "TL";' not in content:
        # Just inject it after any `const { booking` or `function .*({.*booking.*}) {`
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if re.search(r'function .*\{.*booking.*\}\) {', line) or \
               re.search(r'const .*= \(\{.*booking.*\}\) => \{', line) or \
               re.search(r'const \{.*booking.*\} =', line):
                if 'const currency = booking?.currency' not in content:
                    new_lines.append('  const currency = booking?.currency || "TL";')
        content = '\n'.join(new_lines)
        
    # Replacements
    content = re.sub(r'\{fmtTL\(([^)]+)\)\}\s*TL', r'{fmtCurrency(\1, currency)}', content)
    content = re.sub(r'\$\{fmtTL\(([^)]+)\)\}\s*TL', r'${fmtCurrency(\1, currency)}', content)
    content = re.sub(r'fmtTL\(([^)]+)\)\s*\+\s*[\'"] TL[\'"]', r'fmtCurrency(\1, currency)', content)
    content = re.sub(r'fmtTL\(([^)]+)\)\s*\} TL', r'fmtCurrency(\1, currency)}', content)

    # Some missed ones like `Fiyat: {fmtTL(room?.base_price)} TL/gece`
    # -> `Fiyat: {fmtCurrency(room?.base_price, currency)}/gece`
    content = re.sub(r'\{fmtTL\(([^)]+)\)\}\s*TL/gece', r'{fmtCurrency(\1, currency)}/gece', content)

    with open(path, 'w') as f:
        f.write(content)

for f in glob.glob('frontend/src/pages/reservation-detail/*.jsx'):
    fix_file(f)
