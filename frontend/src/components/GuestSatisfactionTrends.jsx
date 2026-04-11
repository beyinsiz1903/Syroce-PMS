import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TrendingUp, ThumbsUp } from 'lucide-react';

const GuestSatisfactionTrends = () => {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ThumbsUp className="w-5 h-5 text-green-600" />
          Guest Satisfaction (NPS)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 bg-green-50 rounded text-center">
            <div className="text-3xl font-bold text-green-700">8.5</div>
            <div className="text-xs text-gray-600">Last 7 Days</div>
          </div>
          <div className="p-4 bg-blue-50 rounded text-center">
            <div className="text-3xl font-bold text-blue-700">8.2</div>
            <div className="text-xs text-gray-600">Last 30 Days</div>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-2 text-sm text-green-700">
          <TrendingUp className="w-4 h-4" />
          +0.3 improvement this week
        </div>
      </CardContent>
    </Card>
  );
};

export default GuestSatisfactionTrends;