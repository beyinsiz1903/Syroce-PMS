import re

with open('frontend/src/pages/GDPRCompliance.jsx', 'r') as f:
    content = f.read()

# Add import
if 'import { toast }' not in content:
    content = content.replace("import { useTranslation } from 'react-i18next';", "import { useTranslation } from 'react-i18next';\nimport { toast } from 'sonner';")

# Remove message state and div
content = re.sub(r"const \[message, setMessage\] = useState\(''\);\n\s*", "", content)
content = re.sub(r"\{message && <div.*?\{message\}</div>\}", "", content)
content = re.sub(r"setMessage\(''\);\n\s*", "", content)

# Replace setMessage with toast.success or toast.error
# We need to manually fix this based on success/error context.
content = content.replace("setMessage('Veri saklama politikası kaydedildi ve denetim kaydı oluşturuldu.');", "toast.success('Veri saklama politikası kaydedildi ve denetim kaydı oluşturuldu.');")
content = content.replace("setMessage(error.response?.data?.detail || 'Veri saklama politikası kaydedilemedi.');", "toast.error(error.response?.data?.detail || 'Veri saklama politikası kaydedilemedi.');")

content = content.replace("setMessage('Veri işleme sözleşmesi kaydedildi.');", "toast.success('Veri işleme sözleşmesi kaydedildi.');")
content = content.replace("setMessage(error.response?.data?.detail || 'Veri işleme sözleşmesi kaydedilemedi.');", "toast.error(error.response?.data?.detail || 'Veri işleme sözleşmesi kaydedilemedi.');")

content = content.replace("setMessage('Saklama politikası etkisi güvenli biçimde önizlendi; veri değiştirilmedi.');", "toast.success('Saklama politikası etkisi güvenli biçimde önizlendi; veri değiştirilmedi.');")
content = content.replace("setMessage(error.response?.data?.detail || 'Saklama politikası önizlenemedi.');", "toast.error(error.response?.data?.detail || 'Saklama politikası önizlenemedi.');")

with open('frontend/src/pages/GDPRCompliance.jsx', 'w') as f:
    f.write(content)

