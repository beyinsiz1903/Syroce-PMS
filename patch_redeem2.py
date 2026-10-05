with open('frontend/src/pages/AfsadakatLauncher.jsx', 'r') as f:
    content = f.read()

dialog_import = "import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';\n"
if "DialogContent" not in content:
    content = content.replace("import { Button } from '@/components/ui/button';", "import { Button } from '@/components/ui/button';\n" + dialog_import)

dialog_jsx = """
      {/* Redeem Dialog */}
      <Dialog open={redeemDialogOpen} onOpenChange={setRedeemDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ödül Kullandır: {redeemReward?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <p className="text-sm text-gray-500">Ödül bedeli: {redeemReward?.points_cost} Puan</p>
            <GuestSearchAutocomplete 
              selectedGuest={selectedRedeemGuest} 
              onSelect={setSelectedRedeemGuest} 
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRedeemDialogOpen(false)}>İptal</Button>
            <Button onClick={handleRedeem} disabled={!selectedRedeemGuest}>Kullandır</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
"""

content = content.replace("    </div>\n  );\n};", dialog_jsx)

with open('frontend/src/pages/AfsadakatLauncher.jsx', 'w') as f:
    f.write(content)
