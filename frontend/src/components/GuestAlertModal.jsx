import { useEffect, useState } from "react";
import api from "@/api/axios";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { AlertTriangle, Crown, Repeat, Cake, Heart, ShieldAlert, Utensils, Bed, MapPin, FileText, Loader2 } from "lucide-react";
import { useTranslation } from 'react-i18next';

const LEVEL_STYLE = {
  danger: "border-red-300 bg-red-50 text-red-800",
  warning: "border-amber-300 bg-amber-50 text-amber-800",
  gold: "border-yellow-300 bg-yellow-50 text-yellow-900",
  info: "border-blue-300 bg-blue-50 text-blue-800",
};
const ICON_BY_TYPE = {
  vip: Crown, repeat: Repeat, blacklist: ShieldAlert, allergy: AlertTriangle,
  note: FileText, special_date: Cake,
};

export default function GuestAlertModal({ guestId, open, onClose, onConfirm, confirmLabel = "Devam Et" }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !guestId) return;
    setLoading(true);
    api.get(`/pms/guests/${guestId}/highlights`)
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [open, guestId]);

  if (!open) return null;
  const blacklisted = data?.blacklisted;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg" data-testid="guest-alert-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {blacklisted ? <ShieldAlert className="w-5 h-5 text-red-600" /> : <Crown className="w-5 h-5 text-yellow-600" />}
            {t('cm.components_GuestAlertModal.misafir_bilgileri')}
          </DialogTitle>
        </DialogHeader>

        {loading && (
          <div className="flex items-center justify-center py-8 text-gray-500">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> {t('cm.components_GuestAlertModal.yukleniyor')}
          </div>
        )}

        {!loading && data && (
          <div className="space-y-2 max-h-[60vh] overflow-y-auto">
            {data.alerts?.length === 0 && (
              <p className="text-sm text-gray-500">{t('cm.components_GuestAlertModal.bu_misafir_icin_ozel_bir_uyari_yok')}</p>
            )}
            {data.alerts?.map((a, i) => {
              const Icon = ICON_BY_TYPE[a.type] || AlertTriangle;
              return (
                <div key={i} className={`flex items-start gap-2 px-3 py-2 rounded-md border ${LEVEL_STYLE[a.level] || LEVEL_STYLE.info}`}>
                  <Icon className="w-4 h-4 mt-0.5 shrink-0" />
                  <span className="text-sm">{a.message}</span>
                </div>
              );
            })}

            {(data.dietary_restrictions || data.pillow_preference || data.room_preference) && (
              <div className="mt-3 border-t pt-3 space-y-1.5">
                <p className="text-xs uppercase text-gray-500 font-semibold tracking-wide">Tercihler</p>
                {data.dietary_restrictions && (
                  <div className="flex items-center gap-2 text-sm"><Utensils className="w-3.5 h-3.5 text-gray-500" /> {data.dietary_restrictions}</div>
                )}
                {data.pillow_preference && (
                  <div className="flex items-center gap-2 text-sm"><Bed className="w-3.5 h-3.5 text-gray-500" /> {data.pillow_preference}</div>
                )}
                {data.room_preference && (
                  <div className="flex items-center gap-2 text-sm"><MapPin className="w-3.5 h-3.5 text-gray-500" /> {data.room_preference}</div>
                )}
              </div>
            )}

            {(data.total_stays || data.last_visit_date) && (
              <div className="mt-3 border-t pt-3 text-sm text-gray-600 flex items-center gap-4">
                {data.total_stays > 0 && <span><Repeat className="inline w-3.5 h-3.5 mr-1" /> {t('cm.components_GuestAlertModal.toplam_ziyaret')} <b>{data.total_stays}</b></span>}
                {data.last_visit_date && <span><Heart className="inline w-3.5 h-3.5 mr-1" /> Son ziyaret: <b>{data.last_visit_date}</b></span>}
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="guest-alert-cancel">{t('cm.components_GuestAlertModal.vazgec')}</Button>
          {onConfirm && (
            <Button
              onClick={() => { onConfirm(); }}
              disabled={blacklisted}
              className={blacklisted ? "" : "bg-emerald-600 hover:bg-emerald-700"}
              data-testid="guest-alert-confirm"
            >
              {blacklisted ? "Kara Liste — İşlem Engellendi" : confirmLabel}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
