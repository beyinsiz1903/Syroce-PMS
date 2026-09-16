with open('frontend/src/pages/AfsadakatLauncher.jsx', 'r') as f:
    content = f.read()

new_refresh = """  const refreshAll = async () => {
    setLoading(true);
    try {
      const r = await axios.get("/integrations/afsadakat/status");
      setStatus(r.data);
    } catch (e) {
      console.error("Af-sadakat status fetch failed", e);
    }
    
    try {
      await refreshLoyalty();
    } catch (e) {
      console.error("Local loyalty fetch failed", e);
    }
    setLoading(false);
  };"""

content = content.replace(
"""  const refreshAll = async () => {
    setLoading(true);
    try {
      const r = await axios.get("/integrations/afsadakat/status");
      setStatus(r.data);
      await refreshLoyalty();
    } catch (e) {
      toast.error("Durum alınamadı");
    }
    setLoading(false);
  };""", new_refresh)

with open('frontend/src/pages/AfsadakatLauncher.jsx', 'w') as f:
    f.write(content)
