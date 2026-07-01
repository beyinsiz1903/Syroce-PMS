import React, { useCallback, useEffect, useRef, useState } from "react";

// Bottom timeline scrubber: drag the pill to move the visible date window.
// UI-only navigation helper — it just calls onChange(newDate) which feeds the
// existing setCurrentDate. No business-logic or API impact.

const DAY_MS = 24 * 60 * 60 * 1000;
const PAST_DAYS = 30;   // span starts 30 days before today
const FUTURE_DAYS = 365; // span ends 365 days after today

const startOfDay = (d) => {
  const nd = new Date(d);
  nd.setHours(0, 0, 0, 0);
  return nd;
};

const CalendarDateScrubber = ({ currentDate, daysToShow = 14, onChange, businessDate }) => {
  const trackRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const grabDxRef = useRef(0);

  const today = startOfDay(new Date());
  const spanStart = startOfDay(new Date(today.getTime() - PAST_DAYS * DAY_MS));
  const spanEnd = startOfDay(new Date(today.getTime() + FUTURE_DAYS * DAY_MS));
  // Inclusive day count so the final day (spanEnd) is reachable.
  const totalDays = Math.round((spanEnd - spanStart) / DAY_MS) + 1;
  const windowDays = Math.max(1, daysToShow);
  const maxStartOffset = Math.max(1, totalDays - windowDays);

  const cur = startOfDay(currentDate || today);
  const curOffset = Math.min(maxStartOffset, Math.max(0, Math.round((cur - spanStart) / DAY_MS)));

  const widthPct = Math.min(100, (windowDays / totalDays) * 100);
  const leftPct = (curOffset / maxStartOffset) * (100 - widthPct);
  const todayPct = (PAST_DAYS / totalDays) * 100;

  const offsetToDate = (offset) => startOfDay(new Date(spanStart.getTime() + offset * DAY_MS));

  const applyFromClientX = useCallback(
    (clientX, grabDx) => {
      const track = trackRef.current;
      if (!track) return;
      const rect = track.getBoundingClientRect();
      const thumbW = (widthPct / 100) * rect.width;
      const available = Math.max(1, rect.width - thumbW);
      const desiredLeft = clientX - rect.left - grabDx;
      const ratio = Math.min(1, Math.max(0, desiredLeft / available));
      const newOffset = Math.round(ratio * maxStartOffset);
      const newDate = offsetToDate(newOffset);
      if (typeof onChange === "function" && newOffset !== curOffset) {
        onChange(newDate);
      }
    },
    [widthPct, maxStartOffset, curOffset, onChange] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const onThumbPointerDown = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const thumbRect = e.currentTarget.getBoundingClientRect();
    grabDxRef.current = e.clientX - thumbRect.left;
    setDragging(true);
  };

  const onTrackPointerDown = (e) => {
    // Click on the track (not the thumb) → jump, centering the thumb on cursor.
    const track = trackRef.current;
    if (!track) return;
    const rect = track.getBoundingClientRect();
    const thumbW = (widthPct / 100) * rect.width;
    grabDxRef.current = thumbW / 2;
    setDragging(true);
    applyFromClientX(e.clientX, thumbW / 2);
  };

  useEffect(() => {
    if (!dragging) return;
    const handleMove = (e) => {
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      applyFromClientX(clientX, grabDxRef.current);
    };
    const handleUp = () => setDragging(false);
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    window.addEventListener("pointercancel", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
      window.removeEventListener("pointercancel", handleUp);
    };
  }, [dragging, applyFromClientX]);

  // Month tick labels across the span.
  const monthTicks = [];
  const tick = new Date(spanStart.getFullYear(), spanStart.getMonth(), 1);
  while (tick <= spanEnd) {
    const pct = ((startOfDay(tick) - spanStart) / DAY_MS / totalDays) * 100;
    if (pct >= 0 && pct <= 100) {
      monthTicks.push({
        pct,
        label: tick.toLocaleDateString("tr-TR", { month: "short" }),
        isYearStart: tick.getMonth() === 0,
        year: tick.getFullYear(),
      });
    }
    tick.setMonth(tick.getMonth() + 1);
  }

  const windowStartLabel = cur.toLocaleDateString("tr-TR", { day: "2-digit", month: "short" });
  const windowEndLabel = offsetToDate(curOffset + windowDays - 1).toLocaleDateString("tr-TR", {
    day: "2-digit",
    month: "short",
  });

  const bizPct =
    businessDate != null
      ? ((startOfDay(new Date(businessDate)) - spanStart) / DAY_MS / totalDays) * 100
      : null;

  return (
    <div
      className="flex-none bg-white border rounded-lg px-3 py-2 select-none"
      data-testid="calendar-date-scrubber"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
          Zaman çizelgesi
        </span>
        <span className="text-[11px] font-medium text-gray-700" data-testid="scrubber-range-label">
          {windowStartLabel} – {windowEndLabel}
        </span>
      </div>

      <div
        ref={trackRef}
        onPointerDown={onTrackPointerDown}
        className="relative h-7 rounded-md bg-gradient-to-r from-gray-100 via-gray-50 to-gray-100 dark:bg-none dark:bg-muted border border-gray-200 cursor-pointer overflow-hidden"
        data-testid="scrubber-track"
        role="slider"
        aria-label="Tarih zaman çizelgesi"
        aria-valuemin={0}
        aria-valuemax={maxStartOffset}
        aria-valuenow={curOffset}
      >
        {/* Month ticks */}
        {monthTicks.map((m, idx) => (
          <div
            key={idx}
            className="absolute top-0 bottom-0 flex flex-col items-start pointer-events-none"
            style={{ left: `${m.pct}%` }}
          >
            <div className={`w-px h-full ${m.isYearStart ? "bg-gray-300" : "bg-gray-200"}`} />
            <span className="absolute top-0.5 left-1 text-[8px] text-gray-400 whitespace-nowrap">
              {m.isYearStart ? `${m.label} ${m.year}` : m.label}
            </span>
          </div>
        ))}

        {/* Today marker */}
        <div
          className="absolute top-0 bottom-0 w-px bg-blue-400 pointer-events-none"
          style={{ left: `${todayPct}%` }}
          data-testid="scrubber-today-marker"
        />

        {/* Business-date marker (if available and different) */}
        {bizPct != null && Math.abs(bizPct - todayPct) > 0.2 && (
          <div
            className="absolute top-0 bottom-0 w-px bg-amber-400 pointer-events-none"
            style={{ left: `${Math.min(100, Math.max(0, bizPct))}%` }}
          />
        )}

        {/* Draggable window thumb */}
        <div
          onPointerDown={onThumbPointerDown}
          className={`absolute top-0.5 bottom-0.5 rounded bg-blue-500/85 border border-blue-600 shadow-sm cursor-grab active:cursor-grabbing flex items-center justify-center ${
            dragging ? "ring-2 ring-blue-300" : ""
          }`}
          style={{ left: `${leftPct}%`, width: `${Math.max(2, widthPct)}%` }}
          data-testid="scrubber-thumb"
        >
          <div className="flex gap-0.5 pointer-events-none">
            <span className="w-0.5 h-3 bg-white/70 rounded-full" />
            <span className="w-0.5 h-3 bg-white/70 rounded-full" />
          </div>
        </div>
      </div>
    </div>
  );
};

export default CalendarDateScrubber;
