import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TrendingUp, TrendingDown } from 'lucide-react';

const MetricDetailModal = ({ isOpen, onClose, metric }) => {
  if (!metric) return null;

  const getTrendIcon = (value) => {
    if (value > 0) return <TrendingUp className="w-4 h-4 text-green-600" />;
    if (value < 0) return <TrendingDown className="w-4 h-4 text-red-600" />;
    return null;
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-2xl flex items-center gap-2">
            {metric.icon && <metric.icon className="w-6 h-6" />}
            {metric.title}
          </DialogTitle>
          <DialogDescription>{metric.description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Current Value */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Current Value</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold text-blue-600">{metric.value}</div>
              {metric.trend !== undefined && (
                <div className="flex items-center gap-2 mt-2">
                  {getTrendIcon(metric.trend)}
                  <span className={`text-sm ${metric.trend > 0 ? 'text-green-600' : metric.trend < 0 ? 'text-red-600' : 'text-gray-600'}`}>
                    {Math.abs(metric.trend)}% vs yesterday
                  </span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Breakdown */}
          {metric.breakdown && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-600">Breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {Object.entries(metric.breakdown).map(([key, value]) => (
                    <div key={key} className="flex justify-between items-center py-2 border-b last:border-0">
                      <span className="text-gray-700 capitalize">{key.replace(/_/g, ' ')}</span>
                      <span className="font-semibold">{value}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Historical Comparison */}
          {metric.historical && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-600">Historical Comparison</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <div className="text-xs text-gray-500">Yesterday</div>
                    <div className="text-lg font-semibold">{metric.historical.yesterday}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500">Last Week</div>
                    <div className="text-lg font-semibold">{metric.historical.lastWeek}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500">Last Month</div>
                    <div className="text-lg font-semibold">{metric.historical.lastMonth}</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Actions */}
          {metric.actions && metric.actions.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-600">Quick Actions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {metric.actions.map((action, idx) => (
                    <button
                      key={idx}
                      onClick={action.onClick}
                      className="w-full text-left px-4 py-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors"
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default MetricDetailModal;
