import re

with open('frontend/src/pages/AfsadakatLauncher.jsx', 'r') as f:
    content = f.read()

# 1. Replace /loyalty/members/earn with /loyalty/earn
content = content.replace('await api.post("/loyalty/members/earn"', 'await api.post("/loyalty/earn"')

# 2. Add state for redeem dialog
content = content.replace(
    'const [selectedEarnGuest, setSelectedEarnGuest] = useState(null);',
    'const [selectedEarnGuest, setSelectedEarnGuest] = useState(null);\n  const [redeemDialogOpen, setRedeemDialogOpen] = useState(false);\n  const [redeemReward, setRedeemReward] = useState(null);\n  const [selectedRedeemGuest, setSelectedRedeemGuest] = useState(null);'
)

# 3. Modify redeem function
new_redeem_func = """  const openRedeemDialog = (reward) => {
    setRedeemReward(reward);
    setSelectedRedeemGuest(null);
    setRedeemDialogOpen(true);
  };

  const handleRedeem = async () => {
    if (!selectedRedeemGuest || !redeemReward) return toast.error("Misafir seçin");
    try {
      const gId = selectedRedeemGuest.id || selectedRedeemGuest.guest_id;
      const { data } = await api.post("/loyalty/redeem", { guest_id: gId, reward_id: redeemReward.id }, {
        headers: { 'Idempotency-Key': crypto.randomUUID() }
      });
      toast.success(data.message || "Ödül kullandırıldı");
      setRedeemDialogOpen(false);
      refreshLoyalty();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Başarısız");
    }
  };"""

content = re.sub(
    r'  const redeem = async \(reward_id\) => \{\n    const guest_id = window\.prompt\("Kullandırılacak Misafir ID\'sini girin:"\);\n    if \(!guest_id\) return;\n    try \{\n      const \{ data \} = await api\.post\("/loyalty/redeem", \{ guest_id, reward_id \}, \{\n        headers: \{ \'Idempotency-Key\': crypto\.randomUUID\(\) \}\n      \}\);\n      toast\.success\(data\.message || "Ödül kullandırıldı"\);\n      refreshLoyalty\(\);\n    \} catch \(err\) \{\n      toast\.error\(err\?\.response\?\.data\?\.detail \|\| "Başarısız"\);\n    \}\n  \};',
    new_redeem_func,
    content
)

# 4. Update the onClick for redeem button
content = content.replace(
    'onClick={() => redeem(r.id)}',
    'onClick={() => openRedeemDialog(r)}'
)

# 5. Add Dialog component to JSX (import Dialog if needed, but it seems layout doesn't use dialog, wait, let's see if Dialog is imported)
