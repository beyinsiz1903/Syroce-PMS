import React from 'react';
import { useSimulation } from '@/context/SimulationContext';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { XCircle, CheckCircle, AlertTriangle } from 'lucide-react';

export default function SimulationOverlay() {
  const { activeScenario, step, mistakes, endSimulation } = useSimulation();

  if (!activeScenario) return null;

  const currentTask = activeScenario.tasks[step];
  const isFinished = step >= activeScenario.totalSteps;

  return (
    <div className="fixed bottom-6 right-6 w-96 z-50 animate-in slide-in-from-bottom-5 pointer-events-none">
      <Card className="p-4 shadow-2xl border-indigo-200 border-2 bg-white/95 backdrop-blur relative overflow-hidden pointer-events-auto">
        {/* Progress Background Hint */}
        <div 
           className="absolute top-0 left-0 h-1 bg-indigo-500 transition-all duration-500"
           style={{ width: `${((step + (isFinished ? 1 : 0)) / activeScenario.totalSteps) * 100}%` }}
        />

        <div className="flex justify-between items-start mb-3 border-b pb-2 pt-1">
          <div>
            <h3 className="font-bold text-indigo-900 text-sm uppercase tracking-wider">{activeScenario.department} MİSYONU</h3>
            <p className="text-xs text-slate-500 font-medium">{activeScenario.title}</p>
          </div>
          <Button variant="ghost" size="sm" className="h-6 px-2 text-red-500 hover:text-red-700 hover:bg-red-50 transition-colors" onClick={endSimulation}>
            <XCircle className="w-4 h-4 mr-1" /> Çıkış
          </Button>
        </div>
        
        {!isFinished ? (
          <>
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-slate-500">Adım {step + 1} / {activeScenario.totalSteps}</span>
                {mistakes > 0 && (
                  <span className="text-xs text-amber-600 flex items-center font-medium">
                    <AlertTriangle className="w-3 h-3 mr-1" /> {mistakes} Hata
                  </span>
                )}
              </div>
            </div>
            
            <div className="bg-indigo-50 p-3 rounded-md border border-indigo-100 shadow-inner">
              <p className="text-sm font-medium text-indigo-900 leading-relaxed">
                {currentTask?.instruction}
              </p>
            </div>
          </>
        ) : (
          <div className="text-center py-4">
            <CheckCircle className="w-12 h-12 text-emerald-500 mx-auto mb-2 animate-bounce" />
            <h4 className="font-bold text-slate-800 text-lg">Görev Tamamlandı!</h4>
            <div className="flex items-center justify-center gap-2 mt-2 mb-4">
               <span className="text-sm font-medium text-slate-600 bg-slate-100 px-2 py-1 rounded">Toplam Hata: {mistakes}</span>
               <span className="text-sm font-medium text-slate-600 bg-indigo-100 text-indigo-700 px-2 py-1 rounded">
                 Skor: {Math.max(0, 100 - (mistakes * 10))} / 100
               </span>
            </div>
            <Button className="w-full bg-indigo-600 hover:bg-indigo-700 shadow-md" onClick={endSimulation}>
              Simülasyonu Bitir
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
