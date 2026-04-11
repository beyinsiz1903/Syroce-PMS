import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Shield, CheckCircle, XCircle } from 'lucide-react';

const SecurityLogs = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadLogs();
  }, []);

  const loadLogs = async () => {
    try {
      const response = await axios.get('/security/login-logs?limit=20');
      setLogs(response.data.logs);
    } catch (error) {
      console.error('Failed to load security logs:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center text-lg">
          <Shield className="w-5 h-5 mr-2" />
          Güvenlik Logları
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {logs.map((log, index) => (
            <div key={index} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg text-xs">
              <div className="flex items-center space-x-2 flex-1">
                {log.success ? (
                  <CheckCircle className="w-4 h-4 text-green-500" />
                ) : (
                  <XCircle className="w-4 h-4 text-red-500" />
                )}
                <div>
                  <div className="font-medium">{log.email}</div>
                  <div className="text-gray-500">{log.ip_address}</div>
                </div>
              </div>
              <div className="text-right">
                <Badge className={log.success ? 'bg-green-500' : 'bg-red-500'}>
                  {log.success ? 'Başarılı' : 'Başarısız'}
                </Badge>
                <div className="text-gray-500 mt-1">
                  {new Date(log.timestamp).toLocaleTimeString('tr-TR')}
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default SecurityLogs;
