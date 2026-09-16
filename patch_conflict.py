import re

with open("frontend/src/components/pms/KBSNotification.jsx", "r") as f:
    content = f.read()

# Replace the entire conflict block with my HEAD version
new_effect = """  useEffect(() => {
    let mounted = true;
    const fetchKbsGuests = async () => {
      try {
        const res = await axios.get('/kbs/guests', { params: { limit: 200 } });
        if (!mounted) return;
        const enriched = res.data.guests || [];
        const pending = enriched.map(b => ({
          id: b.id,
          guest_id: b.guest_id || b.guestId || b.id,
          guest_name: b.guest_name || b.guestName || tk('unknown'),
          room_number: b.room_number || b.roomNumber || '-',
          check_in: b.check_in || b.checkIn,
          check_out: b.check_out || b.checkOut,
          nationality: b.guest_nationality || b.nationality || 'TC',
          id_type: b.id_type || 'tc_kimlik',
          id_number: b.id_number || '',
          birth_date: b.birth_date || '',
          kbs_status: b.kbs_status || 'pending',
          kbs_sent_at: b.kbs_sent_at || null,
        }));
        setPendingGuests(pending.filter(p => p.kbs_status === 'pending'));
        setSentHistory(pending.filter(p => p.kbs_status !== 'pending'));
      } catch (err) {
        console.error('KBS misafir listesi cekilemedi', err);
      }
    };
    fetchKbsGuests();
    return () => { mounted = false; };
  }, [bookings]); // update when bookings array reference changes"""

content = re.sub(r"<<<<<<< HEAD\n.*?=======\n.*?\n>>>>>>> origin/main", new_effect, content, flags=re.DOTALL)

with open("frontend/src/components/pms/KBSNotification.jsx", "w") as f:
    f.write(content)
