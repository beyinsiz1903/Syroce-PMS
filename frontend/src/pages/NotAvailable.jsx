import React from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from 'react-i18next';

export default function NotAvailable() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="min-h-[60vh] flex items-center justify-center px-4">
      <div className="w-full max-w-lg rounded-2xl border bg-white p-6 shadow-sm">
        <div className="text-sm font-medium text-gray-500">PMS Lite</div>
        <h1 className="mt-1 text-xl font-semibold text-gray-900">
          {t('notAvailable.title')}
        </h1>
        <p className="mt-2 text-sm text-gray-600">
          {t('notAvailable.description')}
        </p>

        <div className="mt-5 flex gap-2">
          <button
            className="rounded-xl bg-gray-900 px-4 py-2 text-sm font-medium text-white"
            onClick={() => navigate("/app/dashboard")}
          >
            {t('notAvailable.backToDashboard')}
          </button>
          <button
            className="rounded-xl border px-4 py-2 text-sm font-medium text-gray-900"
            onClick={() => navigate(-1)}
          >
            {t('common.back')}
          </button>
        </div>
      </div>
    </div>
  );
}
