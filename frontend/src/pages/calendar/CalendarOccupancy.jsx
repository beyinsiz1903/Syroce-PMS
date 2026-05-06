import React from "react";
import { Button } from "@/components/ui/button";
import { isWeekend } from "./calendarHelpers";

const CalendarOccupancy = ({ dateRange, getOccupancyForDate, showDeluxePanel, onToggleDeluxe }) => {
  return (
    <div className="bg-white border rounded-lg p-4" data-testid="occupancy-chart">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-semibold text-gray-500 tracking-wider">Doluluk</div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            variant={showDeluxePanel ? "default" : "outline"}
            onClick={onToggleDeluxe}
            className="h-6 text-[10px] px-2"
          >
            Deluxe+
          </Button>
        </div>
      </div>
      <div className="relative" style={{ height: '80px' }}>
        {/* Percentage labels */}
        <div className="absolute top-0 left-0 right-0 flex" style={{ height: '20px' }}>
          {dateRange.map((date, idx) => {
            const occ = getOccupancyForDate(date);
            return (
              <div key={idx} className="flex-1 text-center">
                <span className={`text-[10px] font-bold ${occ >= 80 ? 'text-red-600' : occ >= 50 ? 'text-amber-600' : occ > 0 ? 'text-blue-600' : 'text-gray-400'}`}>
                  {occ > 0 ? occ : '0'}
                </span>
              </div>
            );
          })}
        </div>
        {/* SVG Line Chart */}
        <svg className="w-full" style={{ height: '60px', marginTop: '20px' }} viewBox={`0 0 ${dateRange.length * 100} 60`} preserveAspectRatio="none">
          <defs>
            <linearGradient id="occGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.05" />
            </linearGradient>
          </defs>
          {/* Area fill */}
          <path
            d={(() => {
              const points = dateRange.map((date, idx) => {
                const occ = getOccupancyForDate(date);
                const x = idx * 100 + 50;
                const y = 60 - (occ / 100) * 55;
                return { x, y };
              });
              if (points.length === 0) return '';
              let path = `M ${points[0].x} ${points[0].y}`;
              for (let i = 1; i < points.length; i++) {
                const cp1x = points[i-1].x + (points[i].x - points[i-1].x) / 3;
                const cp2x = points[i].x - (points[i].x - points[i-1].x) / 3;
                path += ` C ${cp1x} ${points[i-1].y} ${cp2x} ${points[i].y} ${points[i].x} ${points[i].y}`;
              }
              path += ` L ${points[points.length-1].x} 60 L ${points[0].x} 60 Z`;
              return path;
            })()}
            fill="url(#occGradient)"
          />
          {/* Line */}
          <path
            d={(() => {
              const points = dateRange.map((date, idx) => {
                const occ = getOccupancyForDate(date);
                const x = idx * 100 + 50;
                const y = 60 - (occ / 100) * 55;
                return { x, y };
              });
              if (points.length === 0) return '';
              let path = `M ${points[0].x} ${points[0].y}`;
              for (let i = 1; i < points.length; i++) {
                const cp1x = points[i-1].x + (points[i].x - points[i-1].x) / 3;
                const cp2x = points[i].x - (points[i].x - points[i-1].x) / 3;
                path += ` C ${cp1x} ${points[i-1].y} ${cp2x} ${points[i].y} ${points[i].x} ${points[i].y}`;
              }
              return path;
            })()}
            fill="none"
            stroke="#3b82f6"
            strokeWidth="2.5"
          />
        </svg>
      </div>
      <div className="text-left text-[10px] text-gray-400 font-medium mt-1">%</div>
    </div>
  );
};

export default CalendarOccupancy;
