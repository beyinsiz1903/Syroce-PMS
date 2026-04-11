import React from 'react';
import { DollarSign, TrendingUp, Tag } from 'lucide-react';

/**
 * Rate Tooltip - Shows ADR, BAR, and Rate Code on hover
 * Used in calendar cells and booking bars for revenue meetings
 */
const RateTooltip = ({ adr, bar, rateCode, date, visible }) => {
  if (!visible) return null;

  return (
    <div className="absolute z-50 bg-gray-900 text-white text-xs rounded-lg shadow-2xl p-3 min-w-[180px] pointer-events-none transform -translate-x-1/2 left-1/2 bottom-full mb-2">
      {/* Arrow */}
      <div className="absolute top-full left-1/2 transform -translate-x-1/2 -mt-1">
        <div className="w-2 h-2 bg-gray-900 rotate-45"></div>
      </div>

      {/* Date */}
      {date && (
        <div className="font-semibold mb-2 pb-2 border-b border-gray-700">
          {new Date(date).toLocaleDateString('en-US', { 
            weekday: 'short', 
            month: 'short', 
            day: 'numeric' 
          })}
        </div>
      )}

      {/* ADR (Average Daily Rate) */}
      <div className="flex items-center justify-between mb-1.5">
        <span className="flex items-center gap-1 text-gray-400">
          <DollarSign className="w-3 h-3" />
          ADR:
        </span>
        <span className="font-bold text-green-400">
          ${adr ? adr.toFixed(2) : 'N/A'}
        </span>
      </div>

      {/* BAR (Best Available Rate) */}
      <div className="flex items-center justify-between mb-1.5">
        <span className="flex items-center gap-1 text-gray-400">
          <TrendingUp className="w-3 h-3" />
          BAR:
        </span>
        <span className="font-bold text-blue-400">
          ${bar ? bar.toFixed(2) : 'N/A'}
        </span>
      </div>

      {/* Rate Code */}
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1 text-gray-400">
          <Tag className="w-3 h-3" />
          Rate Code:
        </span>
        <span className="font-semibold text-yellow-400 uppercase">
          {rateCode || 'STANDARD'}
        </span>
      </div>

      {/* Revenue Insight */}
      {adr && bar && (
        <div className="mt-2 pt-2 border-t border-gray-700 text-[10px] text-gray-400">
          {adr > bar ? (
            <span className="text-green-400">↑ Above BAR (+${(adr - bar).toFixed(2)})</span>
          ) : adr < bar ? (
            <span className="text-red-400">↓ Below BAR (-${(bar - adr).toFixed(2)})</span>
          ) : (
            <span className="text-blue-400">= At BAR</span>
          )}
        </div>
      )}
    </div>
  );
};

export default RateTooltip;
