import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Clock, TrendingDown } from 'lucide-react';

const HousekeepingTaskTiming = () => {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="w-5 h-5 text-blue-600" />
          Cleaning Duration Per Room
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm">Standard Room</span>
            <span className="font-bold">18 min avg</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm">Deluxe Room</span>
            <span className="font-bold">25 min avg</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm">Suite</span>
            <span className="font-bold">35 min avg</span>
          </div>
          <div className="mt-4 p-2 bg-green-50 rounded flex items-center gap-2 text-sm text-green-700">
            <TrendingDown className="w-4 h-4" />
            -2 min improvement this month
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default HousekeepingTaskTiming;