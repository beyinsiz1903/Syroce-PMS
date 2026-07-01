import React, { useEffect, useState } from "react";

import axios from "axios";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Calendar, Clock, RefreshCw, ListChecks } from "lucide-react";
import { useTranslation } from 'react-i18next';

const MaintenancePlans = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({
    asset_id: "",
    frequency_type: "months",
    frequency_value: 3,
    next_due_date: "",
    description: "",
    default_issue_type: "other",
    default_priority: "normal"
  });

  const loadData = async () => {
    try {
      setLoading(true);
      const res = await axios.get("/maintenance/plans");
      setItems(res.data.items || []);
    } catch (err) {
      console.error("Failed to load maintenance plans", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCreate = async () => {
    try {
      const payload = {
        ...form,
        // Backend expects datetime; basitçe gün sonu olarak set edelim
        next_due_date: new Date(form.next_due_date || new Date()).toISOString()
      };
      await axios.post("/maintenance/plans", payload);
      setDialogOpen(false);
      setForm({
        asset_id: "",
        frequency_type: "months",
        frequency_value: 3,
        next_due_date: "",
        description: "",
        default_issue_type: "other",
        default_priority: "normal"
      });
      await loadData();
    } catch (err) {
      console.error("Failed to create plan", err);
    }
  };

  const handleRunScheduler = async () => {
    try {
      await axios.post("/maintenance/plans/run-scheduler");
      await loadData();
    } catch (err) {
      console.error("Failed to run scheduler", err);
    }
  };

  return (
    <>
      <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <h1 className="text-xl md:text-2xl font-bold flex items-center gap-2">
              <ListChecks className="w-5 h-5 text-emerald-600" />
              Preventive {t('maintenance.plans')}
            </h1>
            <p className="text-xs md:text-sm text-gray-600">
              Asset bazlı periyodik bakım planlarınızı tanımlayın ve otomatik iş emirleri oluşturun.
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleRunScheduler}
              disabled={loading}
            >
              <Clock className="w-4 h-4 mr-1" />
              Run Scheduler
            </Button>
            <Button size="sm" onClick={() => setDialogOpen(true)}>
              Yeni Plan
            </Button>
          </div>
        </div>

        {/* List */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              Plans ({items.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="py-10 text-center text-gray-500 text-sm">{t("common.loading")}</div>
            ) : items.length === 0 ? (
              <div className="py-10 text-center text-gray-500 text-sm">Tanımlı bakım planı bulunmuyor.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs md:text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-600">
                      <th className="py-2 pr-3">Asset ID</th>
                      <th className="py-2 pr-3">Frequency</th>
                      <th className="py-2 pr-3">Next Due</th>
                      <th className="py-2 pr-3">Issue Type</th>
                      <th className="py-2 pr-3">Priority</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((p) => (
                      <tr key={p.id} className="border-b last:border-0 hover:bg-gray-50">
                        <td className="py-2 pr-3 text-[11px] font-mono">{p.asset_id || '-'}</td>
                        <td className="py-2 pr-3 text-[11px] text-gray-600">
                          {p.frequency_value} {p.frequency_type}
                        </td>
                        <td className="py-2 pr-3 text-[11px] text-gray-600">
                          {p.next_due_date ? new Date(p.next_due_date).toLocaleDateString("tr-TR") : '-'}
                        </td>
                        <td className="py-2 pr-3 text-[11px] text-gray-600">{p.default_issue_type}</td>
                        <td className="py-2 pr-3 text-[11px] text-gray-600">{p.default_priority}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* New Plan Dialog */}
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Yeni Preventive Plan</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 mt-2">
              <div>
                <div className="text-xs text-gray-600 mb-1">Asset ID</div>
                <Input
                  value={form.asset_id}
                  onChange={(e) => setForm((p) => ({ ...p, asset_id: e.target.value }))}
                  placeholder="İlgili asset id (şimdilik manuel)"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-gray-600 mb-1">Frequency Type</div>
                  <Select
                    value={form.frequency_type}
                    onValueChange={(v) => setForm((p) => ({ ...p, frequency_type: v }))}
                  >
                    <SelectTrigger className="h-9 text-sm">
                      <SelectValue placeholder="Type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="days">Days</SelectItem>
                      <SelectItem value="weeks">Weeks</SelectItem>
                      <SelectItem value="months">Months</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <div className="text-xs text-gray-600 mb-1">Frequency Value</div>
                  <Input
                    type="number"
                    value={form.frequency_value}
                    onChange={(e) => setForm((p) => ({ ...p, frequency_value: parseInt(e.target.value || '0', 10) }))}
                  />
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-600 mb-1">Next Due Date</div>
                <Input
                  type="date"
                  value={form.next_due_date}
                  onChange={(e) => setForm((p) => ({ ...p, next_due_date: e.target.value }))}
                />
              </div>
              <div>
                <div className="text-xs text-gray-600 mb-1">Description</div>
                <Input
                  value={form.description}
                  onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-gray-600 mb-1">Issue Type</div>
                  <Input
                    value={form.default_issue_type}
                    onChange={(e) => setForm((p) => ({ ...p, default_issue_type: e.target.value }))}
                  />
                </div>
                <div>
                  <div className="text-xs text-gray-600 mb-1">Priority</div>
                  <Select
                    value={form.default_priority}
                    onValueChange={(v) => setForm((p) => ({ ...p, default_priority: v }))}
                  >
                    <SelectTrigger className="h-9 text-sm">
                      <SelectValue placeholder={t("common.priority")} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="normal">Normal</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                      <SelectItem value="urgent">Urgent</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button size="sm" onClick={handleCreate}>
                Kaydet
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
};

export default MaintenancePlans;
