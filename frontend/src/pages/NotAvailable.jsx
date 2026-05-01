import React from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Lock, ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";

export default function NotAvailable() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-6">
      <Card className="max-w-md w-full">
        <CardContent className="p-8 text-center space-y-4">
          <div className="mx-auto w-16 h-16 rounded-full bg-amber-100 flex items-center justify-center">
            <Lock className="w-8 h-8 text-amber-600" />
          </div>
          <h2 className="text-xl font-semibold">
            {t("notAvailable.title", "Bu sayfa planınıza dahil değil")}
          </h2>
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
        </CardContent>
      </Card>
    </div>
  );
}
