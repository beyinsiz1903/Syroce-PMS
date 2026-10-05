import re
with open("frontend/src/pages/reservation-detail/InfoTabs.jsx", "r") as f:
    content = f.read()

content = re.sub(r"import \{([^}]+)\} from 'lucide-react';", r"import {\1, UserPlus} from 'lucide-react';", content)

with open("frontend/src/pages/reservation-detail/InfoTabs.jsx", "w") as f:
    f.write(content)
