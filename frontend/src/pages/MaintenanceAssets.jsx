import React, { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import axios from "axios";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Building2, Plus, Database, RefreshCw } from "lucide-react";
import { useTranslation } from 'react-i18next';

const MaintenanceAssets = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [assetType, setAssetType] = useState("all");
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({
    name: "",
    asset_type: "hvac",
    room_number: "",
    location: "",
    manufacturer: "",
    model: "",
    serial_number: ""
  });

  const loadData = async () => {
    try {
      setLoading(true);
      const params = {};
      if (assetType && assetType !== "all") params.asset_type = assetType;
      const res = await axios.get("/maintenance/assets", { params });
      setItems(res.data.items || []);
    } catch (err) {
      console.error("Failed to load maintenance assets", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCreate = async () => {
    try {
      const payload = { ...form };
      const res = await axios.post("/maintenance/assets", payload);
      setDialogOpen(false);
      setForm({
        name: "",
        asset_type: "hvac",
        room_number: "",
        location: "",
        manufacturer: "",
        model: "",
        serial_number: ""
      });
      await loadData();
    } catch (err) {
      console.error("Failed to create asset", err);
    }
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="maintenance">
      <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <h1 className="text-xl md:text-2xl font-bold flex items-center gap-2">
              <Database className="w-5 h-5 text-blue-600" />
              Maintenance Assets
            </h1>
            <p className="text-xs md:text-sm text-gray-600">
              Oteldeki HVAC, elektrik, sıhhi tesisat ve oda ekipmanlarını varlık bazında yönetin.
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={loadData}
              disabled={loading}
            >
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
              Yenile
            </Button>
            <Button size="sm" onClick={() => setDialogOpen(true)}>
              <Plus className="w-4 h-4 mr-1" />
              Yeni Asset
            </Button>
          </div>
        </div>

        {/* Filters */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Building2 className="w-4 h-4" />
              Filtreler
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
            <div>
              <div className="text-xs text-gray-600 mb-1">Asset Type</div>
              <Select value={assetType} onValueChange={setAssetType}>
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue placeholder="Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="hvac">HVAC</SelectItem>
                  <SelectItem value="plumbing">Plumbing</SelectItem>
                  <SelectItem value="electrical">Electrical</SelectItem>
                  <SelectItem value="elevator">Elevator</SelectItem>
                  <SelectItem value="room_fixture">Room Fixture</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* List */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Database className="w-4 h-4" />
              Assets ({items.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="py-10 text-center text-gray-500 text-sm">
                Yükleniyor...
              </div>
            ) : items.length === 0 ? (
              <div className="py-10 text-center text-gray-500 text-sm">
                Kayıtlı asset bulunmuyor.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs md:text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-600">
                      <th className="py-2 pr-3">Ad</th>
                      <th className="py-2 pr-3">Tip</th>
                      <th className="py-2 pr-3">Oda</th>
                      <th className="py-2 pr-3">Lokasyon</th>
                      <th className="py-2 pr-3">Model</th>
                      <th className="py-2 pr-3">Seri No</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((a) => (
                      <tr key={a.id} className="border-b last:border-0 hover:bg-gray-50">
                        <td className="py-2 pr-3">{a.name}</td>
                        <td className="py-2 pr-3 text-[11px] text-gray-600">{a.asset_type}</td>
                        <td className="py-2 pr-3 text-[11px] text-gray-600">{a.room_number || '-'}</td>
                        <td className="py-2 pr-3 text-[11px] text-gray-600">{a.location || '-'}</td>
                        <td className="py-2 pr-3 text-[11px] text-gray-600">{a.model || '-'}</td>
                        <td className="py-2 pr-3 text-[11px] text-gray-600">{a.serial_number || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* New Asset Dialog */}
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Yeni Asset Oluştur</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 mt-2">
              <div>
                <div className="text-xs text-gray-600 mb-1">Ad</div>
                <Input
                  value={form.name}
                  onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder="Örn. Bathroom Fan 305"
                />
              </div>
              <div>
                <div className="text-xs text-gray-600 mb-1">Type</div>
                <Select
                  value={form.asset_type}
                  onValueChange={(v) => setForm((p) => ({ ...p, asset_type: v }))}
                >
                  <SelectTrigger className="h-9 text-sm">
                    <SelectValue placeholder="Type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="hvac">HVAC</SelectItem>
                    <SelectItem value="plumbing">Plumbing</SelectItem>
                    <SelectItem value="electrical">Electrical</SelectItem>
                    <SelectItem value="elevator">Elevator</SelectItem>
                    <SelectItem value="room_fixture">Room Fixture</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-gray-600 mb-1">Room Number</div>
                  <Input
                    value={form.room_number}
                    onChange={(e) => setForm((p) => ({ ...p, room_number: e.target.value }))}
                    placeholder="305"
                  />
                </div>
                <div>
                  <div className="text-xs text-gray-600 mb-1">Lokasyon</div>
                  <Input
                    value={form.location}
                    onChange={(e) => setForm((p) => ({ ...p, location: e.target.value }))}
                    placeholder="Roof, Boiler Room, Lobby..."
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-gray-600 mb-1">Manufacturer</div>
                  <Input
                    value={form.manufacturer}
                    onChange={(e) => setForm((p) => ({ ...p, manufacturer: e.target.value }))}
                  />
                </div>
                <div>
                  <div className="text-xs text-gray-600 mb-1">Model</div>
                  <Input
                    value={form.model}
                    onChange={(e) => setForm((p) => ({ ...p, model: e.target.value }))}
                  />
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-600 mb-1">Serial Number</div>
                <Input
                  value={form.serial_number}
                  onChange={(e) => setForm((p) => ({ ...p, serial_number: e.target.value }))}
                />
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
    </Layout>
  );
};

export default MaintenanceAssets;
