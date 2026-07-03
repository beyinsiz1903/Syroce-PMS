import React from 'react';
import { useSimulation } from '@/context/SimulationContext';
import { Button } from '@/components/ui/button';
import { XCircle, AlertTriangle, CheckCircle } from 'lucide-react';

export default function SimulationOverlay() {
  const { activeScenario, mistakes, step, endSimulation } = useSimulation();

  if (!activeScenario) return null;

  return (
    <div className="fixed top-0 left-0 w-full z-[9999] pointer-events-none">
      <div className="bg-indigo-900 border-b-4 border-indigo-500 shadow-xl p-3 flex items-center justify-between pointer-events-auto">
        <div className="flex items-center gap-4 text-white">
          <div className="bg-indigo-600 p-2 rounded-full animate-pulse shadow-inner shadow-indigo-400">
            <AlertTriangle className="w-5 h-5 text-yellow-300" />
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold tracking-widest text-indigo-300">
              Sınav Modu Aktif — {activeScenario.title}
            </div>
            <div className="font-semibold text-sm leading-tight mt-1">
              Görev {step + 1}/{activeScenario.tasks?.length}: {activeScenario.tasks?.[step]?.instruction}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="bg-slate-900/50 backdrop-blur border border-slate-700 rounded-lg px-4 py-1.5 flex items-center gap-4 text-white">
            <div className="text-center">
              <div className="text-[10px] text-slate-400 font-medium">BAŞARI PUANI</div>
              <div className="font-bold text-emerald-400 text-lg leading-none">{Math.max(0, 100 - mistakes * 10)}</div>
            </div>
            <div className="w-px h-8 bg-slate-700" />
            <div className="text-center">
              <div className="text-[10px] text-slate-400 font-medium">HATALI TIKLAMA</div>
              <div className="font-bold text-rose-400 text-lg leading-none">{mistakes}</div>
            </div>
          </div>
          
          <Button variant="destructive" size="sm" onClick={endSimulation} className="shadow-lg">
            <XCircle className="w-4 h-4 mr-2" /> Sınavı Bitir
          </Button>
        </div>
      </div>
    </div>
  );
}
