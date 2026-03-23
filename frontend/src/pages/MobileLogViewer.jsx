import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, FileText, RefreshCw, AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MobileLogViewer = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState([]);
  const [logLevels, setLogLevels] = useState({});
  const [selectedLevel, setSelectedLevel] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadLogs();
  }, [selectedLevel]);

  const loadLogs = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (selectedLevel) params.append('level', selectedLevel);
      params.append('limit', '50');

      const res = await axios.get(`/system/logs?${params.toString()}`);
      setLogs(res.data.logs || []);
      setLogLevels(res.data.log_levels || {});
      setLoading(false);
      setRefreshing(false);
    } catch (error) {
      console.error('Failed to load logs:', error);
      toast.error('Loglar yüklenemedi');
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadLogs();
  };

  const getLogIcon = (level) => {
    switch(level) {
      case 'ERROR': return <AlertCircle className="w-4 h-4 text-red-600" />;
      case 'WARN': return <AlertTriangle className="w-4 h-4 text-orange-600" />;
      case 'INFO': return <Info className="w-4 h-4 text-blue-600" />;
      default: return <FileText className="w-4 h-4" />;
    }
  };

  const getLogColor = (level) => {
    switch(level) {
      case 'ERROR': return 'border-l-4 border-red-500 bg-red-50';
      case 'WARN': return 'border-l-4 border-orange-500 bg-orange-50';
      case 'INFO': return 'border-l-4 border-blue-500 bg-blue-50';
      default: return 'border-l-4 border-gray-300 bg-white';
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <RefreshCw className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-gray-800 to-gray-900 text-white p-4 sticky top-0 z-50 shadow-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/mobile')}
              className="text-white hover:bg-white/20 p-2"
            >
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-xl font-bold">Sistem Logları</h1>
              <p className="text-xs text-gray-300">Mobile {t('common.details')}</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleRefresh}
            disabled={refreshing}
            className="text-white hover:bg-white/20 p-2"
          >
            <RefreshCw className={`w-5 h-5 ${refreshing ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Level Filters */}
        <div className="flex gap-2 overflow-x-auto">
          <Button
            size="sm"
            variant={selectedLevel === null ? 'default' : 'outline'}
            onClick={() => setSelectedLevel(null)}
            className="whitespace-nowrap"
          >
            Tümü ({Object.values(logLevels).reduce((a, b) => a + b, 0)})
          </Button>
          <Button
            size="sm"
            onClick={() => setSelectedLevel('ERROR')}
            className={`whitespace-nowrap ${selectedLevel === 'ERROR' ? 'bg-red-600' : 'bg-red-500'} text-white`}
          >
            ERROR ({logLevels.ERROR || 0})
          </Button>
          <Button
            size="sm"
            onClick={() => setSelectedLevel('WARN')}
            className={`whitespace-nowrap ${selectedLevel === 'WARN' ? 'bg-orange-600' : 'bg-orange-500'} text-white`}
          >
            WARN ({logLevels.WARN || 0})
          </Button>
          <Button
            size="sm"
            onClick={() => setSelectedLevel('INFO')}
            className={`whitespace-nowrap ${selectedLevel === 'INFO' ? 'bg-blue-600' : 'bg-blue-500'} text-white`}
          >
            INFO ({logLevels.INFO || 0})
          </Button>
        </div>

        {/* Logs List */}
        <div className="space-y-2">
          {logs.length === 0 ? (
            <Card>
              <CardContent className="p-8 text-center">
                <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500">Log bulunamadı</p>
              </CardContent>
            </Card>
          ) : (
            logs.map(log => (
              <Card key={log.id} className={getLogColor(log.level)}>
                <CardContent className="p-3">
                  <div className="flex items-start gap-2">
                    <div className="pt-1">{getLogIcon(log.level)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <Badge className="text-xs">{log.level}</Badge>
                        <span className="text-xs text-gray-500">
                          {new Date(log.timestamp).toLocaleTimeString('tr-TR')}
                        </span>
                        <span className="text-xs text-gray-600 font-medium">{log.user}</span>
                      </div>
                      <div className="text-sm text-gray-800">{log.message}</div>
                      {log.action && (
                        <Badge variant="outline" className="text-xs mt-1">{log.action}</Badge>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default MobileLogViewer;