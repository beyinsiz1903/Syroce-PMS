import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Brain, TrendingUp, MessageSquare, Sparkles, Clock, CheckCircle, XCircle } from 'lucide-react';

const AIActivityLog = () => {
  const [activities, setActivities] = useState([]);
  const [stats, setStats] = useState({ total: 0, successful: 0, failed: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadActivities();
  }, []);

  const loadActivities = async () => {
    try {
      const response = await axios.get('/ai/activity-log');
      setActivities(response.data.activities || []);
      setStats(response.data.stats || { total: 0, successful: 0, failed: 0 });
    } catch (error) {
      console.error('Failed to load AI activities:', error);
    } finally {
      setLoading(false);
    }
  };

  const getActivityIcon = (type) => {
    switch (type) {
      case 'upsell_prediction':
        return <TrendingUp className="w-5 h-5 text-green-500" />;
      case 'message_generation':
        return <MessageSquare className="w-5 h-5 text-blue-500" />;
      case 'demand_forecast':
        return <Brain className="w-5 h-5 text-purple-500" />;
      default:
        return <Sparkles className="w-5 h-5 text-yellow-500" />;
    }
  };

  const getStatusBadge = (status) => {
    if (status === 'success') {
      return (
        <Badge className="bg-green-100 text-green-700 hover:bg-green-100">
          <CheckCircle className="w-3 h-3 mr-1" />
          Success
        </Badge>
      );
    }
    return (
      <Badge className="bg-red-100 text-red-700 hover:bg-red-100">
        <XCircle className="w-3 h-3 mr-1" />
        Failed
      </Badge>
    );
  };

  const renderResult = (result) => {
    if (result == null) return null;
    if (typeof result === 'string' || typeof result === 'number' || typeof result === 'boolean') {
      return String(result);
    }
    try {
      return JSON.stringify(result);
    } catch (e) {
      return String(result);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
        <p className="mt-4 text-gray-600">Loading AI activity...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Total AI Operations</p>
                <p className="text-3xl font-bold">{stats.total}</p>
              </div>
              <Brain className="w-10 h-10 text-purple-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Successful</p>
                <p className="text-3xl font-bold text-green-600">{stats.successful}</p>
              </div>
              <CheckCircle className="w-10 h-10 text-green-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Success Rate</p>
                <p className="text-3xl font-bold text-blue-600">
                  {stats.total > 0 ? ((stats.successful / stats.total) * 100).toFixed(1) : 0}%
                </p>
              </div>
              <TrendingUp className="w-10 h-10 text-blue-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Activity Log */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="w-6 h-6" />
            AI Activity Log
          </CardTitle>
        </CardHeader>
        <CardContent>
          {activities.length === 0 ? (
            <div className="text-center py-12">
              <Brain className="w-16 h-16 mx-auto text-gray-400 mb-4" />
              <p className="text-gray-600">No AI activities recorded yet</p>
              <p className="text-sm text-gray-500 mt-2">AI operations will appear here once initiated</p>
            </div>
          ) : (
            <div className="space-y-3">
              {activities.map((activity) => (
                <div
                  key={activity.id}
                  className="flex items-start gap-4 p-4 border rounded-lg hover:bg-gray-50 transition"
                >
                  <div className="mt-1">{getActivityIcon(activity.type)}</div>
                  
                  <div className="flex-1">
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="font-semibold">{activity.title || activity.type.replace('_', ' ').toUpperCase()}</h4>
                        <p className="text-sm text-gray-600 mt-1">{activity.description}</p>
                      </div>
                      {getStatusBadge(activity.status)}
                    </div>
                    
                    {activity.result != null && (
                      <div className="mt-2 p-2 bg-blue-50 rounded text-sm">
                        <span className="font-semibold text-blue-700">Result:</span>
                        <span className="text-blue-600 ml-2">{renderResult(activity.result)}</span>
                      </div>
                    )}
                    
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(activity.timestamp).toLocaleString()}
                      </span>
                      {activity.execution_time && (
                        <span>Execution time: {activity.execution_time}ms</span>
                      )}
                      {activity.model && (
                        <span>Model: {activity.model}</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default AIActivityLog;