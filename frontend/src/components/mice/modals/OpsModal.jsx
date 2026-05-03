import { Button } from '@/components/ui/button';
import { Modal } from '../_shared';

const OpsModal = ({ opsData, onClose }) => (
  <Modal title={`Günün Ops Sheet'i — ${opsData.date}`} onClose={onClose} wide>
    <div className="space-y-3 text-sm">
      {opsData.rows.length === 0 ? (
        <p className="text-center text-gray-500 p-4">Bu tarih için aktif etkinlik yok.</p>
      ) : (
        <table className="w-full text-xs border-collapse">
          <thead className="bg-slate-50"><tr>
            <th className="border p-1">Saat</th>
            <th className="border p-1 text-left">Etkinlik</th>
            <th className="border p-1 text-left">Müşteri</th>
            <th className="border p-1">Mekan</th>
            <th className="border p-1">Düzen / Pax</th>
            <th className="border p-1">Sorumlu</th>
            <th className="border p-1 text-left">Ajanda Özeti</th>
          </tr></thead>
          <tbody>
            {opsData.rows.map((r, i) => (
              <tr key={i}>
                <td className="border p-1 font-mono">
                  {r.starts_at?.slice(11, 16)}–{r.ends_at?.slice(11, 16)}
                </td>
                <td className="border p-1 font-semibold">{r.event_name}</td>
                <td className="border p-1">{r.client_name}</td>
                <td className="border p-1">{r.space_name}</td>
                <td className="border p-1 text-center">{r.setup_style} / {r.expected_pax}</td>
                <td className="border p-1">{r.organizer_user || '—'}</td>
                <td className="border p-1">
                  {r.agenda_summary?.length === 0 ? <span className="text-gray-400">—</span> : (
                    <ul className="text-[11px] space-y-0.5">
                      {r.agenda_summary.map((a, j) => (
                        <li key={j}>
                          <span className="font-mono">{a.starts_at?.slice(11, 16)}</span>
                          {' '}{a.title} <span className="text-gray-400">[{a.kind}]</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="text-right">
        <Button variant="outline" onClick={() => window.print()}>Yazdır</Button>
        <Button variant="ghost" onClick={onClose}>Kapat</Button>
      </div>
    </div>
  </Modal>
);

export default OpsModal;
