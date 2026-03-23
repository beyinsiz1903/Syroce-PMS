import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Users, Trophy, TrendingUp } from 'lucide-react';

const TeamPerformance = () => {
  const [performance, setPerformance] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPerformance();
  }, []);

  const loadPerformance = async () => {
    try {
      const response = await axios.get('/gm/team-performance');
      setPerformance(response.data);
    } catch (error) {
      console.error('Failed to load performance:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !performance) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  const departments = performance.departments;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-lg">
          <span className="flex items-center">
            <Users className="w-5 h-5 mr-2" />
            Takım Performansı
          </span>
          <Badge className="bg-blue-500">
            Genel: {performance.overall_performance}%
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {Object.values(departments).map((dept) => (
            <div key={dept.department} className="border-l-4 border-blue-500 pl-3 py-2 bg-gray-50 rounded-r-lg">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <div className="font-bold text-sm">{dept.department}</div>
                  <div className="text-xs text-gray-500">{dept.staff_count} personel</div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-bold text-blue-600">{dept.avg_performance_score}%</div>
                  <div className="text-xs text-gray-500">⭐ {dept.guest_satisfaction}</div>
                </div>
              </div>

              {/* Progress Bar */}
              <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
                <div
                  className="bg-blue-500 h-2 rounded-full transition-all"
                  style={{ width: `${dept.avg_performance_score}%` }}
                />
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-600">
                  {dept.tasks_completed} görev tamamlandı
                </span>
                <div className="flex items-center text-green-600">
                  <Trophy className="w-3 h-3 mr-1" />
                  {dept.top_performer.name} ({dept.top_performer.score}%)
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default TeamPerformance;
