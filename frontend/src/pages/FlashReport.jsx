import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Home, Zap } from 'lucide-react';
import FlashReportContent from '@/components/pms/FlashReportContent';
import { useTranslation } from 'react-i18next';

const FlashReport = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="p-6 max-w-7xl mx-auto" data-testid="page-flash-report">
      <div className="flex items-center gap-3 mb-6">
        <Button
          variant="outline"
          size="icon"
          onClick={() => navigate('/')}
          className="hover:bg-blue-50"
          aria-label="Ana sayfa"
        >
          <Home className="w-5 h-5" />
        </Button>
        <div>
          <h1 className="text-3xl font-bold text-gray-900 mb-1 flex items-center gap-2">
            <Zap className="w-7 h-7 text-amber-500" />
            Flash Report
          </h1>
          <p className="text-gray-600 text-sm">{t('cm.pages_FlashReport.gunluk_performans_ozeti_yonetici_raporu')}</p>
        </div>
      </div>

      <FlashReportContent showDatePicker />
    </div>
  );
};

export default FlashReport;
