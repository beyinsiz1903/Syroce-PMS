/**
 * Misafir/rezervasyon/folyo ekranlarında telefon numarasının yanında gösterilen
 * tek-tıkla "Ara" düğmesi. Tıklayınca global Softphone'u tetikler (CustomEvent);
 * Softphone numarayı doldurur ve hazırsa çağrıyı başlatır, değilse aktivasyona
 * yönlendirir. Geçerli numara yoksa hiçbir şey render edilmez.
 */
import { Phone } from "lucide-react";

import { dialViaSoftphone, normalizeDialNumber } from "@/lib/softphone";

export default function CallButton({ number, className = "", label = "Ara" }) {
  const normalized = normalizeDialNumber(number);
  if (!normalized) return null;
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        dialViaSoftphone(normalized);
      }}
      className={`inline-flex items-center gap-1 rounded-md border border-gray-300 px-2 py-0.5 text-xs font-medium text-gray-700 hover:bg-gray-50 ${className}`}
      title={`Ara: ${normalized}`}
      aria-label={`Ara: ${normalized}`}
    >
      <Phone className="h-3 w-3" />
      {label}
    </button>
  );
}
