import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Clock, AlertCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const SLAConfigCard = ({ slaConfigs, delayedTasks }) => {
  const { t } = useTranslation();
  const getCategoryName = (category) => {
    const names = {
      'maintenance': 'Bakım',
      'housekeeping': 'Temizlik',
      'guest_request': 'Misafir Talepleri'
    };
    return names[category] || category;
  };

  const getPriorityColor = (priority) => {
    const colors = {
      'urgent': 'bg-red-500',
      'high': 'bg-amber-500',
      'normal': 'bg-blue-500',
      'low': 'bg-gray-500'
    };
    return colors[priority] || 'bg-gray-500';
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>SLA Hedefleri</span>
            {delayedTasks && delayedTasks.length > 0 && (
              <Badge className="bg-red-500">
                {delayedTasks.length} {t('cm.components_SLAConfigCard.gecikmis')}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {slaConfigs && slaConfigs.length > 0 ? (
              slaConfigs.map((config, idx) => (
                <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${getPriorityColor(config.priority)}`} />
                    <div>
                      <p className="font-medium text-sm">{getCategoryName(config.category)}</p>
                      <p className="text-xs text-gray-500 capitalize">{config.priority}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium">{config.response_time_minutes} dk → {config.resolution_time_minutes} dk</p>
                    <p className="text-xs text-gray-500">{t('cm.components_SLAConfigCard.yanit_cozum')}</p>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-4 text-gray-500 text-sm">
                <Clock className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                {t('cm.components_SLAConfigCard.varsayilan_sla_kullaniliyor')}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {delayedTasks && delayedTasks.length > 0 && (
        <Card className="border-red-200 bg-red-50">
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-red-800">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-5 h-5" />
                <span>Top {Math.min(10, delayedTasks.length)} {t('cm.components_SLAConfigCard.kritik_gorevler')}</span>
              </div>
              {delayedTasks.length > 10 && (
                <Badge variant="outline" className="bg-white text-red-600">
                  +{delayedTasks.length - 10} daha
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {delayedTasks
                .sort((a, b) => b.delay_minutes - a.delay_minutes)
                .slice(0, 10)
                .map((task, index) => (
                <div 
                  key={task.id} 
                  className={`p-3 bg-white rounded border ${
                    task.delay_minutes > 60 ? 'border-red-500' : 
                    task.delay_minutes > 30 ? 'border-amber-400' : 
                    'border-red-200'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className={`
                        w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold
                        ${task.delay_minutes > 60 ? 'bg-red-600 text-white' : 
                          task.delay_minutes > 30 ? 'bg-amber-500 text-white' : 
                          'bg-yellow-500 text-white'}
                      `}>
                        {index + 1}
                      </span>
                      <span className="font-medium text-sm">{t('cm.components_SLAConfigCard.oda')} {task.room_number}</span>
                    </div>
                    <Badge className={`text-xs ${
                      task.delay_minutes > 60 ? 'bg-red-600' : 
                      task.delay_minutes > 30 ? 'bg-amber-500' : 
                      'bg-yellow-500'
                    }`}>
                      {task.delay_minutes} dk gecikme
                    </Badge>
                  </div>
                  {task.guest_name && (
                    <p className="text-xs text-gray-600 ml-8">{task.guest_name}</p>
                  )}
                  <div className="flex items-center justify-between text-xs text-gray-500 mt-1 ml-8">
                    <span>SLA: {task.sla_minutes} dk</span>
                    <span>{t('cm.components_SLAConfigCard.gecen')} {task.elapsed_minutes} dk</span>
                    <span className="text-red-600 font-medium capitalize">{task.priority || 'normal'}</span>
                  </div>
                </div>
              ))}
            </div>
            {delayedTasks.length > 10 && (
              <div className="mt-3 text-center">
                <Button variant="outline" size="sm" className="text-xs">
                  {t('cm.components_SLAConfigCard.tumunu_gor')}{delayedTasks.length} {t('cm.components_SLAConfigCard.gorev')}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default SLAConfigCard;