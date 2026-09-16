with open("frontend/src/pages/reservation-detail/InfoTabs.jsx", "r") as f:
    content = f.read()

import re

# Insert adding state
new_state = """  const [editingId, setEditingId] = useState(null);
  const [addingGuest, setAddingGuest] = useState(false);
"""
content = re.sub(r"  const \[editingId, setEditingId\] = useState\(null\);\n", new_state, content)

# Insert Add Guest UI
add_guest_ui = """      {addingGuest && (
        <div className="border rounded-lg bg-gray-50 p-4 space-y-3 mb-4">
          <h4 className="text-sm font-semibold mb-2">Yeni Misafir Ekle</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div><Label className="text-xs">Ad Soyad</Label><Input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} className="h-8 text-sm" /></div>
            <div><Label className="text-xs">Uyruk</Label><Input value={form.nationality} onChange={e => setForm(p => ({ ...p, nationality: e.target.value }))} placeholder="TR" className="h-8 text-sm" /></div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div><Label className="text-xs">Kimlik Tipi</Label><Select value={form.id_type} onValueChange={v => setForm(p => ({ ...p, id_type: v }))}><SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Seçiniz" /></SelectTrigger><SelectContent className="z-[70]">{ID_TYPES.map(t => <SelectItem key={t.code} value={t.code}>{t.label}</SelectItem>)}</SelectContent></Select></div>
            <div><Label className="text-xs">Kimlik / Pasaport No</Label><Input value={form.id_number} onChange={e => setForm(p => ({ ...p, id_number: e.target.value }))} className="h-8 text-sm" /></div>
            <div><Label className="text-xs">Doğum Tarihi</Label><Input type="date" value={form.date_of_birth} onChange={e => setForm(p => ({ ...p, date_of_birth: e.target.value }))} className="h-8 text-sm" /></div>
          </div>
          <div className="flex gap-2 pt-1">
            <Button size="sm" onClick={async () => {
              setSaving(true);
              try {
                await axios.post(`/pms/reservations/${booking.id}/guests`, form);
                toast.success('İlave misafir eklendi');
                setAddingGuest(false);
                onRefresh?.();
              } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
              setSaving(false);
            }} disabled={saving} className="h-8">{saving ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Check className="w-3 h-3 mr-1" />} Ekle</Button>
            <Button size="sm" variant="outline" onClick={() => setAddingGuest(false)} className="h-8">İptal</Button>
          </div>
        </div>
      )}
      
      {!guests || guests.length === 0 ? <EmptyState icon={Users} text="Kayıtlı misafir bulunamadı" /> : guests.map((g, i) => {"""

content = content.replace("      {!guests || guests.length === 0 ? <EmptyState icon={Users} text=\"Kayıtlı misafir bulunamadı\" /> : guests.map((g, i) => {", add_guest_ui)

add_button = """  return <div data-testid="guests-tab" className="space-y-3">
      <div className="flex justify-end mb-2">
        <Button variant="outline" size="sm" onClick={() => { setForm({ name: '', nationality: '', id_type: 'tc_kimlik', id_number: '', date_of_birth: '' }); setAddingGuest(true); cancelEdit(); }}><UserPlus className="w-4 h-4 mr-2" /> Misafir Ekle</Button>
      </div>"""

content = content.replace("  return <div data-testid=\"guests-tab\" className=\"space-y-3\">", add_button)

# Also import UserPlus if missing
if "UserPlus" not in content:
    content = content.replace("import { Pencil, Check", "import { Pencil, Check, UserPlus")
    
with open("frontend/src/pages/reservation-detail/InfoTabs.jsx", "w") as f:
    f.write(content)
