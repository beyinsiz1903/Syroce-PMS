import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import {
  Database, Columns, Filter, Play, Download, FileSpreadsheet, FileText,
  Plus, X, Trash2, Save, FolderOpen, Loader2, ChevronDown, ChevronUp,
  BarChart3, Table2, ArrowUpDown, Settings2, BookmarkPlus, Eye
} from 'lucide-react';

const API = "";

const DATE_PRESETS = [
  { id: 'today', label: 'Bugün', calc: () => { const d = new Date(); const s = d.toISOString().split('T')[0]; return { from: s, to: s }; } },
  { id: 'week', label: 'Bu Hafta', calc: () => { const d = new Date(); const s = new Date(d); s.setDate(d.getDate() - d.getDay() + 1); return { from: s.toISOString().split('T')[0], to: d.toISOString().split('T')[0] }; } },
  { id: 'month', label: 'Bu Ay', calc: () => { const d = new Date(); return { from: new Date(d.getFullYear(), d.getMonth(), 1).toISOString().split('T')[0], to: d.toISOString().split('T')[0] }; } },
  { id: 'last30', label: 'Son 30 Gün', calc: () => { const d = new Date(); const s = new Date(d); s.setDate(d.getDate() - 30); return { from: s.toISOString().split('T')[0], to: d.toISOString().split('T')[0] }; } },
  { id: 'last90', label: 'Son 90 Gün', calc: () => { const d = new Date(); const s = new Date(d); s.setDate(d.getDate() - 90); return { from: s.toISOString().split('T')[0], to: d.toISOString().split('T')[0] }; } },
  { id: 'quarter', label: 'Bu Çeyrek', calc: () => { const d = new Date(); const q = Math.floor(d.getMonth() / 3); return { from: new Date(d.getFullYear(), q * 3, 1).toISOString().split('T')[0], to: d.toISOString().split('T')[0] }; } },
  { id: 'ytd', label: 'Yıl Başından', calc: () => { const d = new Date(); return { from: new Date(d.getFullYear(), 0, 1).toISOString().split('T')[0], to: d.toISOString().split('T')[0] }; } },
];

const OPERATORS = [
  { value: 'eq', label: 'Eşit' },
  { value: 'ne', label: 'Eşit Değil' },
  { value: 'gt', label: 'Büyük' },
  { value: 'gte', label: 'Büyük veya Eşit' },
  { value: 'lt', label: 'Küçük' },
  { value: 'lte', label: 'Küçük veya Eşit' },
  { value: 'contains', label: 'İçerir' },
  { value: 'in', label: 'Listede' },
];

const formatCurrency = (v) => new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', minimumFractionDigits: 0 }).format(v || 0);

const ReportBuilder = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const token = localStorage.getItem('token');

  // Config state
  const [dataSources, setDataSources] = useState({});
  const [selectedSource, setSelectedSource] = useState('');
  const [selectedColumns, setSelectedColumns] = useState([]);
  const [filters, setFilters] = useState([]);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [datePreset, setDatePreset] = useState('');
  const [sortBy, setSortBy] = useState('');
  const [sortOrder, setSortOrder] = useState('desc');
  const [groupBy, setGroupBy] = useState('');
  const [limit, setLimit] = useState(500);

  // Results state
  const [reportData, setReportData] = useState(null);
  const [columnLabels, setColumnLabels] = useState({});
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  // Templates state
  const [templates, setTemplates] = useState([]);
  const [showTemplates, setShowTemplates] = useState(false);
  const [templateName, setTemplateName] = useState('');
  const [showSaveDialog, setShowSaveDialog] = useState(false);

  // UI state
  const [showFilters, setShowFilters] = useState(false);
  const [configLoading, setConfigLoading] = useState(true);

  // Fetch config on mount
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await fetch(`/api/reports/builder/config`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error(t('reportBuilder.configError'));
        const data = await res.json();
        setDataSources(data.data_sources || {});
      } catch (err) {
        toast.error(t('reportBuilder.configError'));
      } finally {
        setConfigLoading(false);
      }
    };
    fetchConfig();
    fetchTemplates();
  }, [token]);

  const fetchTemplates = async () => {
    try {
      const res = await fetch(`/api/reports/builder/templates`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setTemplates(data.templates || []);
      }
    } catch { /* silent */ }
  };

  const handleSourceChange = (source) => {
    setSelectedSource(source);
    setSelectedColumns([]);
    setFilters([]);
    setSortBy('');
    setGroupBy('');
    setReportData(null);
  };

  const toggleColumn = (col) => {
    setSelectedColumns(prev =>
      prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col]
    );
  };

  const selectAllColumns = () => {
    const src = dataSources[selectedSource];
    if (src) setSelectedColumns(Object.keys(src.columns));
  };

  const clearAllColumns = () => setSelectedColumns([]);

  const addFilter = () => {
    setFilters([...filters, { field: '', operator: 'eq', value: '' }]);
  };

  const updateFilter = (idx, key, val) => {
    setFilters(prev => prev.map((f, i) => i === idx ? { ...f, [key]: val } : f));
  };

  const removeFilter = (idx) => {
    setFilters(prev => prev.filter((_, i) => i !== idx));
  };

  const applyDatePreset = (presetId) => {
    setDatePreset(presetId);
    const preset = DATE_PRESETS.find(p => p.id === presetId);
    if (preset) {
      const { from, to } = preset.calc();
      setDateFrom(from);
      setDateTo(to);
    }
  };

  const buildConfig = () => ({
    data_source: selectedSource,
    columns: selectedColumns,
    filters: filters.filter(f => f.field && f.value !== ''),
    date_from: dateFrom || null,
    date_to: dateTo || null,
    sort_by: sortBy || null,
    sort_order: sortOrder,
    group_by: groupBy || null,
    limit,
  });

  const generateReport = async () => {
    if (!selectedSource) return toast.error(t('reportBuilder.selectSource'));
    if (selectedColumns.length === 0) return toast.error(t('reportBuilder.selectColumns'));

    setLoading(true);
    setReportData(null);
    try {
      const res = await fetch(`/api/reports/builder/generate`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(buildConfig()),
      });
      if (!res.ok) throw new Error(t('reportBuilder.generateError'));
      const result = await res.json();
      setReportData(result.data || []);
      setColumnLabels(result.column_labels || {});
      setSummary(result.summary || {});
      toast.success(`${result.total_count} ${t('reportBuilder.recordsFound')}`);
    } catch (err) {
      toast.error(err.message || 'Rapor oluşturulurken hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  const exportFile = async (format) => {
    if (!selectedSource || selectedColumns.length === 0) return;

    setExporting(true);
    try {
      const res = await fetch(`/api/reports/builder/export/${format}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(buildConfig()),
      });
      if (!res.ok) throw new Error(t('reportBuilder.exportFailed'));

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const ext = format === 'excel' ? 'xlsx' : 'pdf';
      a.download = `rapor_${selectedSource}_${new Date().toISOString().split('T')[0]}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      toast.success(t(format === 'excel' ? 'reportBuilder.excelDownloaded' : 'reportBuilder.pdfDownloaded'));
    } catch (err) {
      toast.error(err.message || 'Dışa aktarma hatası');
    } finally {
      setExporting(false);
    }
  };

  const saveTemplate = async () => {
    if (!templateName.trim()) return toast.error(t('reportBuilder.enterTemplateName'));
    if (!selectedSource || selectedColumns.length === 0) return toast.error(t('reportBuilder.selectColumns'));

    try {
      const res = await fetch(`/api/reports/builder/templates`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: templateName, config: buildConfig() }),
      });
      if (!res.ok) throw new Error('Şablon kaydedilemedi');
      toast.success(t('reportBuilder.templateSaved'));
      setShowSaveDialog(false);
      setTemplateName('');
      fetchTemplates();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const loadTemplate = (tpl) => {
    const c = tpl.config;
    setSelectedSource(c.data_source);
    setSelectedColumns(c.columns || []);
    setFilters(c.filters || []);
    setDateFrom(c.date_from || '');
    setDateTo(c.date_to || '');
    setSortBy(c.sort_by || '');
    setSortOrder(c.sort_order || 'desc');
    setGroupBy(c.group_by || '');
    setLimit(c.limit || 500);
    setShowTemplates(false);
    setReportData(null);
    toast.success(`"${tpl.name}" ${t('reportBuilder.templateLoaded')}`);
  };

  const deleteTemplate = async (id) => {
    try {
      await fetch(`/api/reports/builder/templates/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      fetchTemplates();
      toast.success(t('reportBuilder.templateDeleted'));
    } catch { toast.error(t('messages.error.deleteFailed')); }
  };

  const sourceColumns = dataSources[selectedSource]?.columns || {};

  if (configLoading) {
    return (
      <>
        <div className="flex items-center justify-center min-h-[60vh]">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        </div>
      </>
    );
  }

  return (
    <>
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6" data-testid="report-builder-page">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Settings2 className="w-7 h-7 text-blue-600" />
              {t('reportBuilder.title')}
            </h1>
            <p className="text-sm text-gray-500 mt-1">{t('reportBuilder.subtitle')}</p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowTemplates(!showTemplates)}
              data-testid="templates-toggle-btn"
            >
              <FolderOpen className="w-4 h-4 mr-1" />
              Şablonlar ({templates.length})
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowSaveDialog(true)}
              disabled={!selectedSource || selectedColumns.length === 0}
              data-testid="save-template-btn"
            >
              <BookmarkPlus className="w-4 h-4 mr-1" />
              Kaydet
            </Button>
          </div>
        </div>

        {/* Save Template Dialog */}
        {showSaveDialog && (
          <Card className="border-blue-200 bg-blue-50/30" data-testid="save-template-dialog">
            <CardContent className="pt-4 pb-3 flex items-end gap-3">
              <div className="flex-1">
                <Label className="text-xs text-gray-600">Şablon Adı</Label>
                <Input
                  value={templateName}
                  onChange={e => setTemplateName(e.target.value)}
                  placeholder="Aylık gelir raporu..."
                  className="mt-1 h-9"
                  data-testid="template-name-input"
                />
              </div>
              <Button size="sm" onClick={saveTemplate} data-testid="save-template-confirm-btn">
                <Save className="w-4 h-4 mr-1" />Kaydet
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowSaveDialog(false)}>
                <X className="w-4 h-4" />
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Templates Panel */}
        {showTemplates && templates.length > 0 && (
          <Card data-testid="templates-panel">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Kayıtlı Şablonlar</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                {templates.map(tpl => (
                  <div key={tpl.id} className="flex items-center gap-2 p-2.5 border rounded-lg hover:bg-gray-50 transition-colors">
                    <button
                      onClick={() => loadTemplate(tpl)}
                      className="flex-1 text-left"
                      data-testid={`template-load-${tpl.id}`}
                    >
                      <p className="text-sm font-medium text-gray-900">{tpl.name}</p>
                      <p className="text-xs text-gray-500">{tpl.config?.data_source} | {tpl.config?.columns?.length} sütun</p>
                    </button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-red-500 hover:text-red-700 h-7 w-7 p-0"
                      onClick={() => deleteTemplate(tpl.id)}
                      data-testid={`template-delete-${tpl.id}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step 1: Data Source */}
        <Card data-testid="step-data-source">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-600" />
              1. Veri Kaynağı
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
              {Object.entries(dataSources).map(([key, src]) => (
                <button
                  key={key}
                  onClick={() => handleSourceChange(key)}
                  className={`p-3 rounded-lg border text-left transition-all ${
                    selectedSource === key
                      ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-200'
                      : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                  }`}
                  data-testid={`source-${key}`}
                >
                  <p className="text-sm font-medium text-gray-900">{src.label}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{Object.keys(src.columns).length} alan</p>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Step 2: Columns */}
        {selectedSource && (
          <Card data-testid="step-columns">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Columns className="w-4 h-4 text-green-600" />
                  2. Sütunlar
                  {selectedColumns.length > 0 && (
                    <Badge variant="secondary" className="text-xs">{selectedColumns.length} seçili</Badge>
                  )}
                </CardTitle>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" className="text-xs h-7" onClick={selectAllColumns}>Tümünü Seç</Button>
                  <Button size="sm" variant="ghost" className="text-xs h-7" onClick={clearAllColumns}>{t("common.clear")}</Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1.5">
                {Object.entries(sourceColumns).map(([key, col]) => (
                  <button
                    key={key}
                    onClick={() => toggleColumn(key)}
                    className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-all ${
                      selectedColumns.includes(key)
                        ? 'bg-green-50 border border-green-300 text-green-800'
                        : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50'
                    }`}
                    data-testid={`col-${key}`}
                  >
                    <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center text-xs ${
                      selectedColumns.includes(key) ? 'bg-green-500 border-green-500 text-white' : 'border-gray-300'
                    }`}>
                      {selectedColumns.includes(key) && '✓'}
                    </div>
                    <span className="truncate">{col.label}</span>
                    <Badge variant="outline" className="text-[9px] ml-auto shrink-0 capitalize">{col.type}</Badge>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step 3: Date Range & Filters */}
        {selectedSource && selectedColumns.length > 0 && (
          <Card data-testid="step-filters">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Filter className="w-4 h-4 text-amber-600" />
                  3. Tarih Aralığı & Filtreler
                </CardTitle>
                <Button size="sm" variant="ghost" className="text-xs h-7" onClick={() => setShowFilters(!showFilters)}>
                  {showFilters ? <ChevronUp className="w-3 h-3 mr-1" /> : <ChevronDown className="w-3 h-3 mr-1" />}
                  {showFilters ? 'Gizle' : 'Gelişmiş'}
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Date Presets */}
              <div>
                <Label className="text-xs text-gray-500 mb-2 block">Hızlı Tarih Seçimi</Label>
                <div className="flex flex-wrap gap-1.5">
                  {DATE_PRESETS.map(p => (
                    <button
                      key={p.id}
                      onClick={() => applyDatePreset(p.id)}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                        datePreset === p.id
                          ? 'bg-amber-100 text-amber-800 border border-amber-300'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200 border border-transparent'
                      }`}
                      data-testid={`preset-${p.id}`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Custom Date Range */}
              <div className="grid grid-cols-2 gap-3 max-w-md">
                <div>
                  <Label className="text-xs text-gray-500">Başlangıç</Label>
                  <Input
                    type="date"
                    value={dateFrom}
                    onChange={e => { setDateFrom(e.target.value); setDatePreset(''); }}
                    className="mt-1 h-9"
                    data-testid="date-from-input"
                  />
                </div>
                <div>
                  <Label className="text-xs text-gray-500">Bitiş</Label>
                  <Input
                    type="date"
                    value={dateTo}
                    onChange={e => { setDateTo(e.target.value); setDatePreset(''); }}
                    className="mt-1 h-9"
                    data-testid="date-to-input"
                  />
                </div>
              </div>

              {/* Sort & Limit */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 max-w-2xl">
                <div>
                  <Label className="text-xs text-gray-500">Sıralama</Label>
                  <Select value={sortBy} onValueChange={setSortBy}>
                    <SelectTrigger className="mt-1 h-9" data-testid="sort-by-select">
                      <SelectValue placeholder="Seçiniz..." />
                    </SelectTrigger>
                    <SelectContent>
                      {selectedColumns.map(col => (
                        <SelectItem key={col} value={col}>{sourceColumns[col]?.label || col}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs text-gray-500">Yön</Label>
                  <Select value={sortOrder} onValueChange={setSortOrder}>
                    <SelectTrigger className="mt-1 h-9" data-testid="sort-order-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="desc">Azalan</SelectItem>
                      <SelectItem value="asc">Artan</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs text-gray-500">Limit</Label>
                  <Input
                    type="number"
                    value={limit}
                    onChange={e => setLimit(parseInt(e.target.value) || 500)}
                    className="mt-1 h-9"
                    min={1}
                    max={5000}
                    data-testid="limit-input"
                  />
                </div>
              </div>

              {/* Advanced Filters */}
              {showFilters && (
                <div className="space-y-3 pt-2 border-t">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-gray-500">Gelişmiş Filtreler</Label>
                    <Button size="sm" variant="outline" className="text-xs h-7" onClick={addFilter} data-testid="add-filter-btn">
                      <Plus className="w-3 h-3 mr-1" />Filtre Ekle
                    </Button>
                  </div>
                  {filters.map((f, i) => (
                    <div key={i} className="flex items-center gap-2 bg-gray-50 p-2.5 rounded-lg" data-testid={`filter-row-${i}`}>
                      <Select value={f.field} onValueChange={v => updateFilter(i, 'field', v)}>
                        <SelectTrigger className="h-8 text-xs flex-1">
                          <SelectValue placeholder="Alan..." />
                        </SelectTrigger>
                        <SelectContent>
                          {selectedColumns.map(col => (
                            <SelectItem key={col} value={col}>{sourceColumns[col]?.label || col}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Select value={f.operator} onValueChange={v => updateFilter(i, 'operator', v)}>
                        <SelectTrigger className="h-8 text-xs w-32">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {OPERATORS.map(op => (
                            <SelectItem key={op.value} value={op.value}>{op.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {sourceColumns[f.field]?.options ? (
                        <Select value={f.value} onValueChange={v => updateFilter(i, 'value', v)}>
                          <SelectTrigger className="h-8 text-xs flex-1">
                            <SelectValue placeholder="Değer..." />
                          </SelectTrigger>
                          <SelectContent>
                            {sourceColumns[f.field].options.map(opt => (
                              <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input
                          value={f.value}
                          onChange={e => updateFilter(i, 'value', e.target.value)}
                          placeholder="Değer..."
                          className="h-8 text-xs flex-1"
                        />
                      )}
                      <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-red-500" onClick={() => removeFilter(i)}>
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Generate Button */}
        {selectedSource && selectedColumns.length > 0 && (
          <div className="flex flex-wrap gap-2" data-testid="action-buttons">
            <Button
              onClick={generateReport}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700"
              data-testid="generate-report-btn"
            >
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
              Rapor Oluştur
            </Button>
            <Button
              variant="outline"
              onClick={() => exportFile('excel')}
              disabled={exporting || !selectedSource}
              className="border-green-300 text-green-700 hover:bg-green-50"
              data-testid="export-excel-btn"
            >
              {exporting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <FileSpreadsheet className="w-4 h-4 mr-2" />}
              Excel
            </Button>
            <Button
              variant="outline"
              onClick={() => exportFile('pdf')}
              disabled={exporting || !selectedSource}
              className="border-red-300 text-red-700 hover:bg-red-50"
              data-testid="export-pdf-btn"
            >
              {exporting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <FileText className="w-4 h-4 mr-2" />}
              PDF
            </Button>
          </div>
        )}

        {/* Results Table */}
        {reportData && (
          <Card data-testid="report-results">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Table2 className="w-4 h-4 text-indigo-600" />
                  Sonuçlar
                  <Badge variant="secondary" className="text-xs">{reportData.length} kayıt</Badge>
                </CardTitle>
                <div className="flex gap-1.5">
                  <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => exportFile('excel')}>
                    <FileSpreadsheet className="w-3 h-3 mr-1" />Excel
                  </Button>
                  <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => exportFile('pdf')}>
                    <FileText className="w-3 h-3 mr-1" />PDF
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {/* Summary Cards */}
              {Object.keys(summary).length > 0 && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  {Object.entries(summary).map(([col, stats]) => {
                    const colType = sourceColumns[col]?.type;
                    const fmt = colType === 'currency' ? formatCurrency : (v) => v?.toLocaleString('tr-TR');
                    return (
                      <div key={col} className="p-3 bg-gradient-to-br from-gray-50 to-gray-100 rounded-lg border" data-testid={`summary-${col}`}>
                        <p className="text-xs text-gray-500 font-medium">{columnLabels[col] || col}</p>
                        <p className="text-lg font-bold text-gray-900 mt-0.5">{fmt(stats.sum)}</p>
                        <div className="flex gap-3 mt-1 text-[10px] text-gray-400">
                          <span>Ort: {fmt(stats.avg)}</span>
                          <span>Min: {fmt(stats.min)}</span>
                          <span>Max: {fmt(stats.max)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Data Table */}
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm" data-testid="report-table">
                  <thead>
                    <tr className="bg-gray-50 border-b">
                      <th className="py-2.5 px-3 text-left text-xs font-semibold text-gray-500 w-10">#</th>
                      {selectedColumns.map(col => (
                        <th
                          key={col}
                          className="py-2.5 px-3 text-left text-xs font-semibold text-gray-600 cursor-pointer hover:text-blue-600"
                          onClick={() => { setSortBy(col); setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc'); }}
                        >
                          <span className="flex items-center gap-1">
                            {columnLabels[col] || sourceColumns[col]?.label || col}
                            {sortBy === col && <ArrowUpDown className="w-3 h-3 text-blue-500" />}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {reportData.slice(0, 100).map((row, i) => (
                      <tr key={i} className="border-b hover:bg-blue-50/30 transition-colors">
                        <td className="py-2 px-3 text-xs text-gray-400">{i + 1}</td>
                        {selectedColumns.map(col => {
                          const val = row[col];
                          const colType = sourceColumns[col]?.type;
                          let display;
                          if (colType === 'currency' && typeof val === 'number') display = formatCurrency(val);
                          else if (colType === 'boolean') display = val ? 'Evet' : 'Hayır';
                          else if (Array.isArray(val)) display = val.join(', ');
                          else display = val !== null && val !== undefined ? String(val) : '-';
                          return (
                            <td key={col} className="py-2 px-3 text-xs text-gray-700 max-w-[200px] truncate" title={String(display)}>
                              {colType === 'select' ? (
                                <Badge variant="outline" className="text-[10px] capitalize">{display}</Badge>
                              ) : display}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {reportData.length > 100 && (
                  <div className="p-3 text-center text-xs text-gray-400 bg-gray-50 border-t">
                    Toplam {reportData.length} kayıttan ilk 100 tanesi gösteriliyor. Tamamını görmek için Excel/PDF olarak dışa aktarın.
                  </div>
                )}
              </div>

              {reportData.length === 0 && (
                <div className="text-center py-12 text-gray-400">
                  <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
                  <p className="text-sm">Seçilen kriterlere uygun kayıt bulunamadı</p>
                  <p className="text-xs mt-1">Filtrelerinizi genişletmeyi veya tarih aralığını değiştirmeyi deneyin</p>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Empty State */}
        {!selectedSource && (
          <Card className="border-dashed border-2" data-testid="empty-state">
            <CardContent className="py-16">
              <div className="text-center">
                <Settings2 className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-gray-700 mb-2">Özel Rapor Oluşturun</h3>
                <p className="text-sm text-gray-500 max-w-md mx-auto">
                  Yukarıdan bir veri kaynağı seçerek başlayın. Sütunları, filtreleri ve tarih aralığını belirleyip
                  raporunuzu anında oluşturabilir, Excel veya PDF olarak indirebilirsiniz.
                </p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
};

export default ReportBuilder;
