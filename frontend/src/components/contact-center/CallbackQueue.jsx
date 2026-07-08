import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Phone, CheckCircle, UserPlus, RefreshCw } from 'lucide-react';

export default function CallbackQueue({ onDial }) {
  const [callbacks, setCallbacks] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchCallbacks = async () => {
    setLoading(true);
    try {
      const res = await axios.get("/contact-center/callbacks");
      setCallbacks(res.data.callbacks || []);
    } catch (err) {
      console.error("Failed to fetch callbacks:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCallbacks();
  }, []);

  const assignCallback = async (id) => {
    try {
      await axios.post(`/contact-center/callbacks/${id}/assign`);
      fetchCallbacks();
    } catch (err) {
      console.error("Failed to assign callback:", err);
    }
  };

  const completeCallback = async (id, result) => {
    try {
      await axios.post(`/contact-center/callbacks/${id}/complete?result=${result}`);
      fetchCallbacks();
    } catch (err) {
      console.error("Failed to complete callback:", err);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400">Geri Arama Talepleri</h4>
        <button onClick={fetchCallbacks} disabled={loading} className="text-gray-400 hover:text-gray-600">
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {callbacks.length === 0 ? (
        <p className="text-xs text-gray-500 italic text-center py-4">Bekleyen geri arama talebi bulunmamaktadır.</p>
      ) : (
        <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
          {callbacks.map((cb) => (
            <div key={cb.id} className="p-2.5 rounded-md border border-gray-100 bg-gray-50 flex flex-col gap-1.5 text-[11px]">
              <div className="flex justify-between items-start">
                <span className="font-semibold text-gray-800">{cb.phone}</span>
                <span className={`px-1 py-0.5 rounded text-[9px] font-bold ${
                  cb.priority === 'high' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'
                }`}>
                  {cb.priority === 'high' ? 'VIP' : 'Normal'}
                </span>
              </div>
              <div className="text-gray-400 text-[10px]">
                Kaçırılma: {cb.abandoned_at ? new Date(cb.abandoned_at).toLocaleTimeString("tr-TR", { hour: '2-digit', minute: '2-digit' }) : "Bilinmiyor"}
              </div>
              
              <div className="flex gap-1.5 mt-1">
                {cb.status === 'pending' && (
                  <button
                    onClick={() => assignCallback(cb.id)}
                    className="flex-1 py-1 rounded bg-indigo-50 text-indigo-700 hover:bg-indigo-100 font-medium flex items-center justify-center gap-1"
                  >
                    <UserPlus className="w-3 h-3" /> Ata
                  </button>
                )}
                <button
                  onClick={() => onDial(cb.phone, cb.id)}
                  className="flex-1 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700 font-medium flex items-center justify-center gap-1"
                >
                  <Phone className="w-3 h-3" /> Geri Ara
                </button>
                <button
                  onClick={() => completeCallback(cb.id, "solved")}
                  className="px-1.5 py-1 rounded bg-gray-200 text-gray-700 hover:bg-gray-300 font-medium"
                  title="Tamamlandı Olarak İşaretle"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
