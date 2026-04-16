import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { StatusBadge } from './StatusBadges';
import { AlertTriangle, UserCheck, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function DuplicateWarning({ open, onClose, duplicates, onForceCreate, onViewExisting }) {
  if (!duplicates || duplicates.length === 0) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-[var(--brand-warning)]">
            <AlertTriangle className="w-5 h-5" />
            Mükerrer Misafir Tespit Edildi
          </DialogTitle>
          <DialogDescription>
            Bu bilgilerle eşleşen {duplicates.length} mevcut misafir kaydı bulundu.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 max-h-60 overflow-y-auto">
          {duplicates.map((dup) => (
            <div key={dup.id} className="flex items-center gap-3 p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--secondary))]">
              <div className="w-10 h-10 rounded-full bg-[var(--brand-warning-soft)] flex items-center justify-center shrink-0">
                <UserCheck className="w-5 h-5 text-[var(--brand-warning)]" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{dup.first_name} {dup.last_name}</p>
                <p className="text-xs text-muted-foreground">
                  {dup.id_number || dup.document_number || '—'}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <StatusBadge status={dup.status} />
                  <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${
                    dup.match_confidence === 'high' 
                      ? 'bg-[var(--brand-danger-soft)] text-[var(--brand-danger)] border-[#FECDD3]'
                      : 'bg-[var(--brand-warning-soft)] text-[var(--brand-warning)] border-[#FED7AA]'
                  }`}>
                    {dup.match_type === 'id_number' ? 'Kimlik No Eşleşmesi' : 'Ad+Doğum Tarihi Eşleşmesi'}
                  </Badge>
                </div>
              </div>
              <Link to={`/guests/${dup.id}`} onClick={onClose}>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <ArrowRight className="w-4 h-4" />
                </Button>
              </Link>
            </div>
          ))}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button
            variant="outline"
            onClick={onClose}
            className="sm:flex-1"
          >
            İptal
          </Button>
          <Button
            onClick={() => {
              if (onViewExisting && duplicates.length > 0) {
                onViewExisting(duplicates[0].id);
              }
            }}
            variant="outline"
            className="sm:flex-1 border-[var(--brand-sky)] text-[var(--brand-sky)]"
          >
            Mevcut Kaydı Gör
          </Button>
          <Button
            onClick={onForceCreate}
            className="sm:flex-1 bg-[var(--brand-warning)] hover:bg-[#9A4408] text-white"
            data-testid="force-create-button"
          >
            Yine de Kaydet
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
