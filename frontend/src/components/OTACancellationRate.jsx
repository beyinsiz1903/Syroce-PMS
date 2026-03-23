import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { XCircle, AlertTriangle } from 'lucide-react';

const OTACancellationRate = () => {
  const channels = [
    { name: 'Booking.com', cancellations: 8, bookings: 120, rate: 6.7 },
    { name: 'Expedia', cancellations: 5, bookings: 80, rate: 6.3 },
    { name: 'Direct', cancellations: 2, bookings: 50, rate: 4.0 }
  ];

  return (
    <Card className="border-red-200">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <XCircle className="w-5 h-5 text-red-600" />
          OTA Cancellation Rate
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {channels.map((ch, idx) => (
            <div key={idx} className="flex justify-between items-center p-2 border-b">
              <span className="text-sm font-medium">{ch.name}</span>
              <div className="text-right">
                <span className={`font-bold ${
                  ch.rate > 6 ? 'text-red-600' : 'text-green-600'
                }`}>{ch.rate}%</span>
                <div className="text-xs text-gray-500">{ch.cancellations}/{ch.bookings}</div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default OTACancellationRate;