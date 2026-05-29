import React from "react";
import { isToday, isWeekend, isPastDate } from "./calendarHelpers";

// Compact, grid-aligned occupancy band rendered on top of the calendar grid.
// Column model mirrors CalendarGrid exactly: a w-28 (112px) left label column
// followed by `daysToShow` day cells of `cellW` px each — so it lives inside
// the grid's horizontal scroll container and stays perfectly aligned with the
// date header and room rows. UI only: occupancy is computed frontend-side via
// the `getOccupancyForDate` prop (no new API). Degrades gracefully when there
// is no room/occupancy data.

const BAND_H = 52;        // total band height (compact)
const LABEL_H = 18;       // top strip reserved for % labels
const CHART_H = BAND_H - LABEL_H;

const clampPct = (v) => Math.max(0, Math.min(100, Math.round(Number(v) || 0)));

// Color scale per spec: low (<50) green, mid (50-79) amber, high (>=80) red.
// 0% is still "low" and stays green (the truly no-data case is handled
// separately as a graceful empty state below).
const levelLabelColor = (occ) =>
  occ >= 80 ? "text-red-600" : occ >= 50 ? "text-amber-600" : "text-emerald-600";

const levelDotColor = (occ) =>
  occ >= 80 ? "#dc2626" : occ >= 50 ? "#f59e0b" : "#10b981";

const OccupancyBand = ({ dateRange = [], daysToShow, cellW = 72, getOccupancyForDate, roomsCount = 0 }) => {
  if (typeof getOccupancyForDate !== "function" || dateRange.length === 0) {
    return null;
  }

  const days = typeof daysToShow === "number" ? daysToShow : dateRange.length;
  const chartW = days * cellW;

  // No rooms → graceful empty state (no chart, no crash).
  if (roomsCount <= 0) {
    return (
      <div className="flex bg-white border-b border-gray-200" data-testid="occupancy-band">
        <div className="w-28 flex-shrink-0 border-r border-gray-200 px-2 flex items-center" style={{ height: `${BAND_H}px` }}>
          <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">Doluluk</span>
        </div>
        <div className="flex items-center justify-center" style={{ width: `${chartW}px`, height: `${BAND_H}px` }}>
          <span className="text-[11px] text-gray-400">Doluluk verisi yok</span>
        </div>
      </div>
    );
  }

  const points = dateRange.map((date, idx) => {
    const occ = clampPct(getOccupancyForDate(date));
    const x = idx * cellW + cellW / 2;
    const y = CHART_H - (occ / 100) * (CHART_H - 6) - 3; // 3px padding top/bottom
    return { x, y, occ, date };
  });

  const buildPath = (close) => {
    if (points.length === 0) return "";
    let d = `M ${points[0].x} ${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
      const cp1x = points[i - 1].x + (points[i].x - points[i - 1].x) / 3;
      const cp2x = points[i].x - (points[i].x - points[i - 1].x) / 3;
      d += ` C ${cp1x} ${points[i - 1].y} ${cp2x} ${points[i].y} ${points[i].x} ${points[i].y}`;
    }
    if (close) {
      d += ` L ${points[points.length - 1].x} ${CHART_H} L ${points[0].x} ${CHART_H} Z`;
    }
    return d;
  };

  return (
    <div className="flex bg-white border-b border-gray-200 select-none" data-testid="occupancy-band">
      {/* Left label column — aligns with the grid's w-28 room-label column */}
      <div className="w-28 flex-shrink-0 border-r border-gray-200 px-2 flex flex-col justify-center" style={{ height: `${BAND_H}px` }}>
        <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 leading-tight">Doluluk</span>
        <span className="text-[9px] text-gray-400 leading-tight">% / gün</span>
      </div>

      {/* Day columns + chart overlay */}
      <div className="relative flex" style={{ width: `${chartW}px`, height: `${BAND_H}px` }}>
        {/* Chart overlay (lower region, below the % labels) */}
        <svg
          data-testid="occupancy-band-chart"
          className="absolute left-0 pointer-events-none"
          style={{ top: `${LABEL_H}px` }}
          width={chartW}
          height={CHART_H}
          viewBox={`0 0 ${chartW} ${CHART_H}`}
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id="occBandGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#6366f1" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#6366f1" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          <path d={buildPath(true)} fill="url(#occBandGradient)" />
          <path d={buildPath(false)} fill="none" stroke="#6366f1" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          {points.map((p, idx) => (
            <circle key={idx} cx={p.x} cy={p.y} r={2.5} fill={levelDotColor(p.occ)} stroke="#ffffff" strokeWidth="1" />
          ))}
        </svg>

        {/* Per-day cells with % labels (kept above the chart for alignment + a11y) */}
        {dateRange.map((date, idx) => {
          const occ = clampPct(getOccupancyForDate(date));
          const today = isToday(date);
          const weekend = isWeekend(date);
          const past = isPastDate(date);
          const cellBg = past ? "bg-gray-50/60" : today ? "bg-blue-50/50" : weekend ? "bg-amber-50/30" : "";
          const labelColor = levelLabelColor(occ);
          return (
            <div
              key={idx}
              data-testid="occupancy-band-day"
              className={`flex-shrink-0 flex items-start justify-center pt-1 border-r ${today ? "border-blue-200" : "border-gray-100"} ${cellBg}`}
              style={{ width: `${cellW}px`, height: `${BAND_H}px` }}
            >
              <span data-testid="occupancy-percent-label" className={`text-[10px] font-bold leading-none ${labelColor}`}>
                {occ}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default OccupancyBand;
