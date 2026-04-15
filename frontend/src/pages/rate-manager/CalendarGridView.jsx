import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ChevronLeft, ChevronRight, BedDouble, Lock, Calendar, RefreshCw, Loader2 } from 'lucide-react';

export const CalendarGridView = ({
  filteredGrid, dates, roomTypes, ratePlans,
  gridRoomType, setGridRoomType, gridRatePlan, setGridRatePlan,
  startDate, setStartDate, endDate, setEndDate,
  shiftDates, fetchGrid, loading, formatDate, currency,
}) => (
  <Card>
    <CardHeader className="pb-3">
      <div className="flex items-center justify-between">
        <div>
          <CardTitle className="text-base">Mevcut Fiyat Takvimi</CardTitle>
          <CardDescription className="text-xs">
            Tarih bazinda mevcut fiyat, musaitlik ve kisitlamalari goruntuleyin
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={fetchGrid} disabled={loading}>
          <RefreshCw className="w-4 h-4 mr-1.5" /> Yenile
        </Button>
      </div>
    </CardHeader>
    <CardContent>
      {/* Grid Filters & Date Navigation */}
      <div className="flex items-center gap-3 flex-wrap mb-4">
        <Select value={gridRoomType} onValueChange={setGridRoomType}>
          <SelectTrigger data-testid="grid-room-type-filter" className="w-[180px] h-8 text-xs">
            <SelectValue placeholder="Oda Tipi" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tum Oda Tipleri</SelectItem>
            {roomTypes.map(rt => (
              <SelectItem key={rt.code} value={rt.code}>{rt.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={gridRatePlan} onValueChange={setGridRatePlan}>
          <SelectTrigger data-testid="grid-rate-plan-filter" className="w-[200px] h-8 text-xs">
            <SelectValue placeholder="Fiyat Plani" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tum Fiyat Planlari</SelectItem>
            {ratePlans.map(rp => (
              <SelectItem key={rp.code} value={rp.code}>{rp.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-1 ml-auto">
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => shiftDates(-7)} data-testid="prev-week-btn">
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs"
            onClick={() => {
              const t = new Date().toISOString().slice(0, 10);
              const e = new Date(); e.setDate(e.getDate() + 13);
              setStartDate(t); setEndDate(e.toISOString().slice(0, 10));
            }}
            data-testid="today-btn">
            <Calendar className="w-3 h-3 mr-1" /> Bugun
          </Button>
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => shiftDates(7)} data-testid="next-week-btn">
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Grid Table */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      ) : (
        <div className="overflow-x-auto border rounded-lg">
          <table className="w-full text-sm" data-testid="rate-grid-table">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="sticky left-0 z-10 bg-gray-50 px-3 py-2 text-left text-xs text-gray-500 font-medium min-w-[200px]">
                  Oda / Plan
                </th>
                {dates.map(d => {
                  const f = formatDate(d);
                  return (
                    <th key={d} className={`px-2 py-2 text-center text-xs font-medium min-w-[80px] ${f.isWeekend ? 'bg-amber-50 text-amber-700' : 'text-gray-500'}`}>
                      <div>{f.weekday}</div>
                      <div className="text-base font-bold text-gray-800">{f.day}</div>
                      <div className="text-[10px] opacity-70">{f.month}</div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {filteredGrid.map((row) => (
                <tr key={`${row.room_type_code}-${row.rate_plan_code}`} className="border-b hover:bg-gray-50/50">
                  <td className="sticky left-0 z-10 bg-white px-3 py-2 border-r">
                    <div className="flex items-center gap-2">
                      <BedDouble className="w-4 h-4 text-gray-400 flex-shrink-0" />
                      <div>
                        <div className="font-medium text-gray-800 text-xs">{row.room_type_name}</div>
                        <div className="text-[10px] text-gray-400 truncate max-w-[150px]">{row.rate_plan_name}</div>
                      </div>
                    </div>
                  </td>
                  {row.dates.map((cell) => {
                    const f = formatDate(cell.date);
                    return (
                      <td key={cell.date}
                        className={`px-1 py-1 text-center ${f.isWeekend ? 'bg-amber-50/40' : ''} ${cell.stop_sell ? 'bg-red-50' : ''}`}
                        data-testid={`cell-${row.room_type_code}-${row.rate_plan_code}-${cell.date}`}>
                        <div className="space-y-0.5">
                          {cell.rate != null ? (
                            <div className="text-xs font-semibold text-blue-700">{cell.rate} {currency}</div>
                          ) : (
                            <div className="text-xs text-gray-300">-</div>
                          )}
                          <div className="text-[10px] text-gray-400">
                            {cell.availability != null ? (
                              <span className={cell.availability === 0 ? 'text-red-500 font-semibold' : cell.availability <= 2 ? 'text-amber-500 font-medium' : ''}>
                                {cell.availability} oda
                              </span>
                            ) : ''}
                            {cell.sold > 0 && (
                              <span className="text-blue-500 ml-0.5">({cell.sold} satildi)</span>
                            )}
                          </div>
                          {cell.min_stay > 1 && (
                            <div className="text-[10px] text-amber-600">min {cell.min_stay}g</div>
                          )}
                          {cell.stop_sell && (
                            <Lock className="w-3 h-3 text-red-400 mx-auto" />
                          )}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
              {filteredGrid.length === 0 && (
                <tr>
                  <td colSpan={dates.length + 1} className="py-12 text-center text-gray-400">
                    Veri bulunamadı
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </CardContent>
  </Card>
);
