import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { XCircle, AlertTriangle, CheckCircle } from 'lucide-react';

/**
 * Cancellation Policy Display
 * Shows policy rules and fees for booking
 */
const CancellationPolicyDisplay = ({ booking }) => {
  const policy = booking?.cancellation_policy || {
    type: 'flexible',
    free_cancellation_until: 24,
    penalty_percentage: 50,
    no_show_penalty: 100
  };

  const getPolicyColor = (type) => {
    switch(type) {
      case 'flexible': return 'green';
      case 'moderate': return 'orange';
      case 'strict': return 'red';
      default: return 'gray';
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <XCircle className="w-5 h-5" />
            Cancellation Policy
          </span>
          <Badge className={`bg-${getPolicyColor(policy.type)}-500`}>
            {policy.type?.toUpperCase()}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-2">
          <div className="flex items-start gap-2">
            <CheckCircle className="w-4 h-4 text-green-600 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold">Free Cancellation</p>
              <p className="text-xs text-gray-600">
                Until {policy.free_cancellation_until} hours before check-in
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-orange-600 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold">Late Cancellation</p>
              <p className="text-xs text-gray-600">
                {policy.penalty_percentage}% penalty if cancelled within {policy.free_cancellation_until} hours
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2">
            <XCircle className="w-4 h-4 text-red-600 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold">No-Show</p>
              <p className="text-xs text-gray-600">
                {policy.no_show_penalty}% charge for no-show
              </p>
            </div>
          </div>
        </div>

        {booking?.ota_commission && (
          <div className="mt-4 pt-3 border-t">
            <div className="flex justify-between items-center text-sm">
              <span className="text-gray-600">OTA Commission:</span>
              <span className="font-bold text-orange-600">
                {booking.ota_commission}%
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Source: {booking.source || 'Direct'}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default CancellationPolicyDisplay;