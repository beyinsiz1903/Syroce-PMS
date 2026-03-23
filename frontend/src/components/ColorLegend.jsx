import React from 'react';
import { Info } from 'lucide-react';

/**
 * Color Legend - Shows global color system meanings
 * Can be shown as tooltip or inline
 */
const ColorLegend = ({ inline = false, compact = false }) => {
  const colors = [
    { color: 'bg-green-500', name: 'Green', meaning: 'Available / Positive / Ready' },
    { color: 'bg-red-500', name: 'Red', meaning: 'Risk / Overdue / Critical / Dirty' },
    { color: 'bg-orange-500', name: 'Orange', meaning: 'Attention / Warning / Priority' },
    { color: 'bg-yellow-500', name: 'Yellow', meaning: 'Pending / In-Progress / Cleaning' },
    { color: 'bg-blue-500', name: 'Blue', meaning: 'Informational / Normal' },
    { color: 'bg-purple-500', name: 'Purple', meaning: 'Occupied / In-Use / VIP' }
  ];

  if (compact) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <Info className="w-3 h-3 text-gray-500" />
        {colors.slice(0, 3).map((item, idx) => (
          <span key={idx} className="flex items-center gap-1">
            <span className={`w-2 h-2 rounded-full ${item.color}`}></span>
            <span className="text-gray-600">{item.meaning.split('/')[0].trim()}</span>
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className={`${inline ? '' : 'p-4 bg-white rounded-lg shadow-sm border'}`}>
      <div className="flex items-center gap-2 mb-3">
        <Info className="w-4 h-4 text-blue-600" />
        <h4 className="font-semibold text-sm">Global Color System</h4>
      </div>
      <div className="space-y-2">
        {colors.map((item, idx) => (
          <div key={idx} className="flex items-center gap-3">
            <div className={`w-6 h-6 rounded ${item.color}`}></div>
            <div className="flex-1">
              <div className="font-medium text-sm">{item.name}</div>
              <div className="text-xs text-gray-600">{item.meaning}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 pt-3 border-t text-xs text-gray-500">
        These colors are used consistently across all modules: PMS, Housekeeping, Finance, etc.
      </div>
    </div>
  );
};

export default ColorLegend;
