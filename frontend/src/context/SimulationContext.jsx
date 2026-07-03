import React, { createContext, useContext, useState, useEffect } from 'react';
import { toast } from "sonner";
import { useLocation, useNavigate } from "react-router-dom";

const SimulationContext = createContext(null);

export function SimulationProvider({ children }) {
  const [activeScenario, setActiveScenario] = useState(null);
  const [mistakes, setMistakes] = useState(0);
  const [step, setStep] = useState(0);
  const location = useLocation();
  const navigate = useNavigate();

  // Yükleme sırasında localStorage'dan oku
  useEffect(() => {
    const saved = sessionStorage.getItem("simulation_active");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setActiveScenario(parsed.scenario);
        setMistakes(parsed.mistakes || 0);
        setStep(parsed.step || 0);
      } catch (e) {
        console.error(e);
      }
    }
  }, []);

  // Durum değiştiğinde kaydet
  useEffect(() => {
    if (activeScenario) {
      sessionStorage.setItem("simulation_active", JSON.stringify({
        scenario: activeScenario,
        mistakes,
        step
      }));
    } else {
      sessionStorage.removeItem("simulation_active");
    }
  }, [activeScenario, mistakes, step]);

  // Axios Interceptor'dan gelen eylemleri dinle
  useEffect(() => {
    const handleAction = (e) => {
      if (!activeScenario) return;
      const { method, url, data } = e.detail;
      
      const currentTask = activeScenario.tasks[step];
      if (!currentTask) return;

      // Sadece mutasyonları (POST, PUT, PATCH, DELETE) değerlendir, GET/OPTIONS'ları yoksay
      if (!['post', 'put', 'patch', 'delete'].includes(method?.toLowerCase())) return;

      // Eğer beklenen URL ile hiç ilgisi yoksa, yoksay (arka plan istekleri olabilir)
      if (currentTask.expected_url && !url.includes(currentTask.expected_url)) {
          // Ancak bu bir form gönderimiyse ve yanlış yere gittiyse hata sayılabilir.
          // Basitlik için şimdilik tamamen farklı URL'leri yoksayıyoruz.
          return;
      }
      
      let isMatch = true;
      let mismatchReason = "";

      if (currentTask.expected_data) {
        for (const [k, v] of Object.entries(currentTask.expected_data)) {
           // İç içe objeleri kontrol etmek yerine basit shallow string karşılaştırması
           const actualVal = data?.[k] !== undefined ? String(data[k]) : "";
           const expectedVal = String(v);
           
           if (actualVal.toLowerCase() !== expectedVal.toLowerCase()) {
              isMatch = false;
              mismatchReason = `'${k}' alanı beklenen değerle eşleşmiyor. (Beklenen: ${expectedVal})`;
              break;
           }
        }
      }

      if (isMatch) {
         reportSuccess("Adım başarıyla tamamlandı!");
      } else {
         reportMistake(mismatchReason || "Girdiğiniz veriler veya yaptığınız işlem görevle uyuşmuyor.");
      }
    };

    window.addEventListener('simulation_action', handleAction);
    return () => window.removeEventListener('simulation_action', handleAction);
  }, [activeScenario, step]);

  const startSimulation = (scenario) => {
    setActiveScenario(scenario);
    setMistakes(0);
    setStep(0);
    toast.success(`${scenario.title} simülasyonu başladı!`);
    
    // Doğru sayfaya yönlendir
    if (scenario.startPath) {
      navigate(scenario.startPath);
    } else {
      navigate("/app/dashboard"); // Default
    }
  };

  const endSimulation = () => {
    setActiveScenario(null);
    setMistakes(0);
    setStep(0);
    toast.info("Simülasyon sona erdi.");
    navigate("/app/academy/simulator");
  };

  const reportMistake = (reason) => {
    setMistakes(prev => prev + 1);
    toast.error(`Hatalı İşlem: ${reason}`, { duration: 4000 });
  };

  const reportSuccess = (message) => {
    toast.success(message, { duration: 4000 });
    
    // Basit mantık: Her başarıda 1 adım ileri git, adım sayısı bitince bitir.
    setStep(prev => {
      const next = prev + 1;
      if (activeScenario && next >= activeScenario.totalSteps) {
        // Simülasyon bitti
        setTimeout(() => {
           toast.success("Görev başarıyla tamamlandı!");
           endSimulation();
        }, 1500);
      }
      return next;
    });
  };

  return (
    <SimulationContext.Provider value={{
      activeScenario,
      mistakes,
      step,
      startSimulation,
      endSimulation,
      reportMistake,
      reportSuccess
    }}>
      {children}
    </SimulationContext.Provider>
  );
}

export function useSimulation() {
  return useContext(SimulationContext);
}
