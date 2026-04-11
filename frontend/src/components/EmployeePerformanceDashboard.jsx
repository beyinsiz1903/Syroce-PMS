import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Users, Clock, TrendingUp } from 'lucide-react';

const EmployeePerformanceDashboard = () => {
  const employees = [
    { name: 'Maria (HK)', rooms_cleaned: 12, avg_time: '18 min', score: 95 },
    { name: 'John (Engineering)', tasks_completed: 8, avg_time: '45 min', score: 92 },
    { name: 'Sarah (FD)', checkins: 15, avg_time: '3.5 min', score: 98 }
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="w-5 h-5" />
          Employee Performance
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {employees.map((emp, idx) => (
            <div key={idx} className="p-3 bg-gray-50 rounded flex justify-between items-center">
              <div>
                <div className="font-semibold">{emp.name}</div>
                <div className="text-xs text-gray-600">
                  <Clock className="w-3 h-3 inline mr-1" />
                  Avg: {emp.avg_time}
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-green-600">{emp.score}</div>
                <div className="text-xs text-gray-600">Score</div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default EmployeePerformanceDashboard;