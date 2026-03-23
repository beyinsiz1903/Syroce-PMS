import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, FileText, Search, RefreshCw, Download, Filter, AlertCircle, AlertTriangle, Info, Bug } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const LogViewer = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState([]);
  const [logLevels, setLogLevels] = useState({});
  const [selectedLevel, setSelectedLevel] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadLogs();
  }, [selectedLevel]);

  const loadLogs = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (selectedLevel) params.append('level', selectedLevel);
      if (searchQuery) params.append('search', searchQuery);
      params.append('limit', '100');

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

  const handleSearch = () => {
    loadLogs();
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
      case 'DEBUG': return <Bug className="w-4 h-4 text-gray-600" />;
      default: return <FileText className="w-4 h-4" />;
    }
  };

  const getLogColor = (level) => {
    switch(level) {
      case 'ERROR': return 'bg-red-50 border-red-200';
      case 'WARN': return 'bg-orange-50 border-orange-200';
      case 'INFO': return 'bg-blue-50 border-blue-200';
      case 'DEBUG': return 'bg-gray-50 border-gray-200';
      default: return 'bg-white border-gray-200';
    }
  };

  const exportLogs = () => {
    const csvContent = logs.map(log => 
      `${log.timestamp},${log.level},${log.user},${log.action},"${log.message}"`
    ).join('\n');
    
    const blob = new Blob([`Timestamp,Level,User,Action,Message\n${csvContent}`], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `logs_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    toast.success('Loglar indirildi');
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
              onClick={() => navigate(-1)}
              className="text-white hover:bg-white/20 p-2"
            >
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-xl font-bold">Sistem Logları</h1>
              <p className="text-xs text-gray-300">Desktop Log Viewer</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={exportLogs}
              className="text-white hover:bg-white/20"
            >
              <Download className="w-4 h-4" />
            </Button>
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
      </div>

      <div className="p-4 space-y-4">
        {/* Filters */}
        <Card>
          <CardContent className="p-4">
            <div className="flex flex-col md:flex-row gap-3">
              <div className="flex-1 flex gap-2">
                <Input
                  placeholder="Log ara... (kullanıcı, aksiyon, mesaj)"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                />
                <Button onClick={handleSearch}>
                  <Search className="w-4 h-4" />
                </Button>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant={selectedLevel === null ? 'default' : 'outline'}
                  onClick={() => setSelectedLevel(null)}
                >
                  Tümü ({Object.values(logLevels).reduce((a, b) => a + b, 0)})
                </Button>
                <Button
                  size="sm"
                  variant={selectedLevel === 'ERROR' ? 'default' : 'outline'}
                  onClick={() => setSelectedLevel('ERROR')}
                  className="bg-red-500 hover:bg-red-600 text-white"
                >
                  ERROR ({logLevels.ERROR || 0})
                </Button>
                <Button
                  size="sm"
                  variant={selectedLevel === 'WARN' ? 'default' : 'outline'}
                  onClick={() => setSelectedLevel('WARN')}
                  className="bg-orange-500 hover:bg-orange-600 text-white"
                >
                  WARN ({logLevels.WARN || 0})
                </Button>
                <Button
                  size="sm"
                  variant={selectedLevel === 'INFO' ? 'default' : 'outline'}
                  onClick={() => setSelectedLevel('INFO')}
                  className="bg-blue-500 hover:bg-blue-600 text-white"
                >
                  INFO ({logLevels.INFO || 0})
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

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
              <Card key={log.id} className={`border ${getLogColor(log.level)}`}>
                <CardContent className="p-3">
                  <div className="flex items-start gap-3">
                    <div className="pt-1">{getLogIcon(log.level)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge className="text-xs">{log.level}</Badge>
                        <span className="text-xs text-gray-500">
                          {new Date(log.timestamp).toLocaleString('tr-TR')}
                        </span>
                        <span className="text-xs text-gray-600 font-medium">{log.user}</span>
                        {log.action && (
                          <Badge variant="outline" className="text-xs">{log.action}</Badge>
                        )}
                      </div>
                      <div className="text-sm text-gray-800 font-mono">{log.message}</div>
                      {log.details && Object.keys(log.details).length > 0 && (
                        <div className="mt-2 p-2 bg-gray-100 rounded text-xs font-mono overflow-x-auto">
                          {JSON.stringify(log.details, null, 2)}
                        </div>
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

export default LogViewer;