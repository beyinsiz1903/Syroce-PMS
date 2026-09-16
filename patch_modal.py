import re

with open("frontend/src/pages/ReservationDetailModal.jsx", "r") as f:
    content = f.read()

# Fix 1: action helper
new_action = """  const action = async (url, body = {}, msg = 'İşlem tamamlandı', operation = null) => {
    try {
      await axios.post(`${API}${url}`, body);
      if (msg) toast.success(msg);
      if (operation) await finishOperation(operation);
      else await loadData();
    }"""
content = re.sub(r"  const action = async[\s\S]*?toast\.success\(msg\);\n      if \(operation\) await finishOperation\(operation\);\n      else await loadData\(\);\n    \}", new_action, content)

# Fix 2: Remove Giriş yapıldı toast
content = content.replace("toast.success('Giriş yapıldı');", "")

# Fix 3: Remove Erken giriş yapıldı msg
content = content.replace("'Erken giriş yapıldı')", "null)")

with open("frontend/src/pages/ReservationDetailModal.jsx", "w") as f:
    f.write(content)
