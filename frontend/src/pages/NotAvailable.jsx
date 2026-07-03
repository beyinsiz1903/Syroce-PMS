import React from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Lock, ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";

export default function NotAvailable({ user }) {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-80px)] bg-slate-50/50 p-6">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-sm border border-slate-200 p-8 text-center">
        <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-6">
          <Lock className="w-8 h-8 text-slate-400" />
        </div>
        
        <div className="space-y-3 mb-8">
          <h2 className="text-xl font-bold text-slate-800">
            {t("notAvailable.title", "Bu sayfa planınıza dahil değil")}
          </h2>
          <p className="text-sm text-slate-600">
            DEBUG: userRole={user?.role || 'undefined'} | userRoles={(user?.roles || []).join(',')}
          </p>
          <p className="text-sm text-slate-600">
            {t(
              "notAvailable.description",
              "Bu modüle erişmek için planınızı yükseltmeniz veya ilgili modülü etkinleştirmeniz gerekir."
            )}
          </p>
          <div className="flex gap-2 justify-center pt-2">
            <Button variant="outline" onClick={() => navigate(-1)}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              {t("common.back", "Geri")}
            </Button>
            <Button onClick={() => navigate("/app/dashboard")}>
              {t("notAvailable.toDashboard", "Panele Git")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
