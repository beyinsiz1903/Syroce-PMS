import React, { useEffect, useState } from "react";

import axios from "axios";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Building2, Wrench, Filter, RefreshCw, AlertTriangle, CheckCircle, Camera, Image, Video } from "lucide-react";
import { PageHeader } from '@/components/ui/page-header';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import useMediaCapture from "@/hooks/useMediaCapture";
import { toast } from "sonner";
import { useTranslation } from 'react-i18next';

const MaintenanceWorkOrders = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("open");
  const [priority, setPriority] = useState("all");
  const [loading, setLoading] = useState(true);
  const [mediaModalOpen, setMediaModalOpen] = useState(false);
  const [selectedWorkOrder, setSelectedWorkOrder] = useState(null);
  const [mediaList, setMediaList] = useState([]);
  const [mediaLoading, setMediaLoading] = useState(false);
  const [mediaType, setMediaType] = useState("photo");
  const [includeBeforeAfter, setIncludeBeforeAfter] = useState(true);
  const { uploadMedia, uploading } = useMediaCapture();

  const loadData = async () => {
    try {
      setLoading(true);
      const params = {};
      if (status && status !== "all") params.status = status;
      if (priority && priority !== "all") params.priority = priority;
      const res = await axios.get("/maintenance/work-orders", { params });
      setItems(res.data.items || []);
    } catch (err) {
      console.error("Failed to load maintenance work orders", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  const handleUpdateStatus = async (id, newStatus) => {
    try {
      await axios.patch(`/maintenance/work-orders/${id}`, { status: newStatus });
      await loadData();
    } catch (err) {
      console.error("Failed to update work order", err);
    }
  };

  const openMediaModal = async (workOrder) => {
    setSelectedWorkOrder(workOrder);
    setMediaModalOpen(true);
    await fetchMedia(workOrder.id);
  };

  const fetchMedia = async (workOrderId) => {
    setMediaLoading(true);
    try {
      const res = await axios.get("/media/list", {
        params: {
          module: "maintenance",
          entity_id: workOrderId
        }
      });
      setMediaList(res.data.items || []);
    } catch (error) {
      console.error("Failed to fetch media", error);
      toast.error("Fotoğraflar yüklenemedi");
    } finally {
      setMediaLoading(false);
    }
  };

  const handleMediaCapture = async (file) => {
    if (!file || !selectedWorkOrder) return;

    try {
      const metadata = {
        work_order_id: selectedWorkOrder.id,
        room_id: selectedWorkOrder.room_id,
        room_number: selectedWorkOrder.room_number,
        issue_type: selectedWorkOrder.issue_type,
        status: selectedWorkOrder.status,
        photo_type: includeBeforeAfter ? (selectedWorkOrder.status === "completed" ? "after" : "before") : "general",
        captured_at: new Date().toISOString()
      };

      const result = await uploadMedia({
        file,
        module: "maintenance",
        entityId: selectedWorkOrder.id,
        mediaType,
        qaRequired: true,
        metadata
      });

      if (result.offlineQueued) {
        toast.message("📶 Medya sıraya alındı", {
          description: "Bağlantı sağlandığında otomatik yüklenecek."
        });
      } else {
        toast.success("✓ Medya yüklendi");
        await fetchMedia(selectedWorkOrder.id);
      }
    } catch (error) {
      console.error("Media upload failed", error);
      toast.error("Medya yüklenemedi");
    }
  };

  const renderMediaList = () => {
    if (mediaLoading) {
      return (
        <div className="text-sm text-gray-500 flex items-center gap-2">
          <RefreshCw className="w-4 h-4 animate-spin" />
          Fotoğraflar yükleniyor...
        </div>
      );
    }

    if (!mediaList.length) {
      return <p className="text-sm text-gray-500">Bu iş emri için kayıtlı medya yok.</p>;
    }

    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-96 overflow-y-auto">
        {mediaList.map((media) => (
          <Card key={media.id} className="border">
            <CardContent className="p-3 space-y-2">
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>{media.media_type}</span>
                <span>{new Date(media.created_at).toLocaleString("tr-TR")}</span>
              </div>
              {media.media_type === "photo" ? (
                <img
                  src={media.storage_url}
                  alt={media.metadata?.photo_type || "maintenance-photo"}
                  className="w-full h-40 object-cover rounded"
                />
              ) : (
                <video controls className="w-full rounded">
                  <source src={media.storage_url} type={media.content_type || "video/mp4"} />
                </video>
              )}
              {media.metadata?.notes && (
                <p className="text-xs text-gray-600">{media.metadata.notes}</p>
              )}
              <div className="text-xs text-gray-500">
                QA: {media.qa_status || "-"}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  };

  const fileInputId = "maintenance-media-input";

  const renderStatusBadge = (value) => {
    const v = value || "open";
    let color = "bg-gray-100 text-gray-700";
    if (v === "open") color = "bg-red-100 text-red-700";
    else if (v === "in_progress") color = "bg-yellow-100 text-yellow-700";
    else if (v === "completed") color = "bg-green-100 text-green-700";
    else if (v === "cancelled") color = "bg-gray-200 text-gray-700";
    return <Badge className={color}>{v}</Badge>;
  };

  const renderPriorityBadge = (value) => {
    const v = value || "normal";
    let color = "bg-gray-100 text-gray-700";
    if (v === "urgent") color = "bg-red-600 text-white";
    else if (v === "high") color = "bg-red-100 text-red-700";
    else if (v === "normal") color = "bg-blue-100 text-blue-700";
    else if (v === "low") color = "bg-gray-100 text-gray-700";
    return <Badge className={color}>{v}</Badge>;
  };

  return (
    <>
      <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-4">
        {/* Header */}
        <PageHeader
          icon={Wrench}
          title={t('maintenance.workOrders')}
          subtitle="Kat Hizmetleri, Ön Büro veya sensörler tarafından oluşturulan tüm bakım iş emirlerini takip edin."
          actions={
            <Button size="sm" variant="outline" onClick={loadData} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
          }
        />

        {/* Filters */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Filter className="w-4 h-4" />
              Filtreler
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
            <div>
              <div className="text-xs text-gray-600 mb-1">Durum</div>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue placeholder={t("common.status")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("common.all")}</SelectItem>
                  <SelectItem value="open">Open</SelectItem>
                  <SelectItem value="in_progress">In Progress</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <div className="text-xs text-gray-600 mb-1">Öncelik</div>
              <Select value={priority} onValueChange={setPriority}>
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue placeholder={t("common.priority")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("common.all")}</SelectItem>
                  <SelectItem value="urgent">Urgent</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="normal">Normal</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex justify-end">
              <Button size="sm" onClick={loadData} disabled={loading}>
                Uygula
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* List */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Building2 className="w-4 h-4" />
              Work Orders ({items.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="py-10 text-center text-gray-500 text-sm flex items-center justify-center gap-2">
                <RefreshCw className="w-5 h-5 animate-spin" />
                Yükleniyor...
              </div>
            ) : items.length === 0 ? (
              <div className="py-10 text-center text-gray-500 text-sm">
                Kayıtlı bakım iş emri bulunmuyor.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs md:text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-600">
                      <th className="py-2 pr-3">Oda</th>
                      <th className="py-2 pr-3">Issue</th>
                      <th className="py-2 pr-3">Kaynak</th>
                      <th className="py-2 pr-3">Raporlayan</th>
                      <th className="py-2 pr-3 text-right">Öncelik</th>
                      <th className="py-2 pr-3 text-right">Durum</th>
                      <th className="py-2 pr-3 text-right">İşlem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((wo) => {
                      const created = wo.created_at ? new Date(wo.created_at).toLocaleString("tr-TR") : "";
                      return (
                        <tr key={wo.id} className="border-b last:border-0 hover:bg-gray-50">
                          <td className="py-2 pr-3 whitespace-nowrap">
                            <div className="font-medium text-gray-900">Room {wo.room_number || "-"}</div>
                            <div className="text-[11px] text-gray-500">{created}</div>
                          </td>
                          <td className="py-2 pr-3 whitespace-nowrap">
                            <div className="text-[11px] font-semibold text-gray-800">{wo.issue_type}</div>
                            <div className="text-[11px] text-gray-500 max-w-xs truncate" title={wo.description || ""}>
                              {wo.description || "-"}
                            </div>
                          </td>
                          <td className="py-2 pr-3 text-[11px] text-gray-600">
                            {wo.source || "-"}
                          </td>
                          <td className="py-2 pr-3 text-[11px] text-gray-600">
                            {wo.reported_by_role || "-"}
                          </td>
                          <td className="py-2 pr-3 text-right">
                            {renderPriorityBadge(wo.priority)}
                          </td>
                          <td className="py-2 pr-3 text-right">
                            {renderStatusBadge(wo.status)}
                          </td>
                          <td className="py-2 pr-3 text-right">
                            {wo.status !== "completed" ? (
                              <div className="inline-flex gap-1">
                                <Button
                                  size="xs"
                                  variant="outline"
                                  onClick={() => handleUpdateStatus(wo.id, "in_progress")}
                                >
                                  <AlertTriangle className="w-3 h-3 mr-1" />
                                  Start
                                </Button>
                                <Button
                                  size="xs"
                                  variant="outline"
                                  className="border-green-300 text-green-700"
                                  onClick={() => handleUpdateStatus(wo.id, "completed")}
                                >
                                  <CheckCircle className="w-3 h-3 mr-1" />
                                  Done
                                </Button>
                              </div>
                            ) : (
                              <span className="text-[11px] text-gray-400">Closed</span>
                            )}
                            <div className="mt-2">
                              <Button
                                size="xs"
                                variant="secondary"
                                className="w-full"
                                onClick={() => openMediaModal(wo)}
                              >
                                <Camera className="w-3 h-3 mr-1" />
                                Fotoğraflar
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
      <Dialog open={mediaModalOpen} onOpenChange={setMediaModalOpen}>
        <DialogContent className="max-w-3xl w-[95vw]">
          <DialogHeader>
            <DialogTitle>
              Bakım Fotoğrafları {selectedWorkOrder ? `- ${selectedWorkOrder.room_number || ""}` : ""}
            </DialogTitle>
          </DialogHeader>
          {selectedWorkOrder && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="flex-1">
                  <p className="text-sm font-semibold">{selectedWorkOrder.issue_type}</p>
                  <p className="text-xs text-gray-500">{selectedWorkOrder.description || "-"}</p>
                </div>
                <Badge>{selectedWorkOrder.status}</Badge>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center gap-3 border rounded-lg p-3 bg-gray-50">
                <div className="flex items-center gap-2">
                  <input
                    id={fileInputId}
                    type="file"
                    accept={mediaType === "photo" ? "image/*" : "video/*"}
                    capture={mediaType === "photo" ? "environment" : undefined}
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) {
                        handleMediaCapture(file);
                        e.target.value = "";
                      }
                    }}
                  />
                  <Button
                    size="sm"
                    className="flex items-center gap-2"
                    onClick={() => document.getElementById(fileInputId)?.click()}
                    disabled={uploading}
                  >
                    {uploading ? (
                      <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                    ) : mediaType === "video" ? (
                      <Video className="w-4 h-4" />
                    ) : (
                      <Camera className="w-4 h-4" />
                    )}
                    Yeni {mediaType === "video" ? "Video" : "Fotoğraf"}
                  </Button>
                </div>

                <div className="flex items-center gap-4 text-xs text-gray-600">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="beforeAfter"
                      checked={includeBeforeAfter}
                      onCheckedChange={(checked) => setIncludeBeforeAfter(Boolean(checked))}
                    />
                    <label htmlFor="beforeAfter">Önce/Sonra Etiketle</label>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="text-xs">Tip:</label>
                    <Select value={mediaType} onValueChange={setMediaType}>
                      <SelectTrigger className="h-8 w-28">
                        <SelectValue placeholder="Tip" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="photo">Fotoğraf</SelectItem>
                        <SelectItem value="video">Video</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>

              <div>{renderMediaList()}</div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default MaintenanceWorkOrders;
