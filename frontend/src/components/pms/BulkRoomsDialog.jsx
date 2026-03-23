import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Download } from 'lucide-react';

const BulkRoomsDialog = ({ open, onClose, onRoomsCreated }) => {
  const { t } = useTranslation();
  const [bulkRoomTab, setBulkRoomTab] = useState('range');
  const [bulkRange, setBulkRange] = useState({ prefix: '', start_number: 101, end_number: 110, room_type: 'standard', floor: 1, capacity: 2, base_price: 150, view: '', bed_type: 'king', amenities: [] });
  const [bulkTemplate, setBulkTemplate] = useState({ prefix: '', start_number: 201, count: 5, room_type: 'deluxe', floor: 2, capacity: 2, base_price: 250, view: '', bed_type: 'king', amenities: [] });
  const [bulkCsvFile, setBulkCsvFile] = useState(null);

  const handleBulkCreateRange = async (e) => {
    e.preventDefault();
    try {
      const res = await axios.post('/pms/rooms/bulk-create/range', bulkRange);
      toast.success(`${res.data.created_count || 'Rooms'} created successfully`);
      onClose();
      onRoomsCreated?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Bulk create failed');
    }
  };

  const handleBulkCreateTemplate = async (e) => {
    e.preventDefault();
    try {
      const res = await axios.post('/pms/rooms/bulk-create/template', bulkTemplate);
      toast.success(`${res.data.created_count || 'Rooms'} created successfully`);
      onClose();
      onRoomsCreated?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Bulk create failed');
    }
  };

  const handleBulkImportCsv = async (e) => {
    e.preventDefault();
    if (!bulkCsvFile) return;
    const formData = new FormData();
    formData.append('file', bulkCsvFile);
    try {
      const res = await axios.post('/pms/rooms/bulk-create/csv', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success(`${res.data.created_count || 'Rooms'} imported from CSV`);
      onClose();
      onRoomsCreated?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'CSV import failed');
    }
  };

  const downloadRoomsCsvTemplate = () => {
    const csv = 'room_number,room_type,floor,capacity,base_price,view,bed_type,amenities\n101,standard,1,2,150,city,king,wifi|minibar\n102,deluxe,1,3,250,sea,twin,wifi|minibar|balcony';
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'rooms_template.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t('pms.bulkAddRooms')}</DialogTitle>
          <DialogDescription>Range, template veya CSV ile toplu oda ekleme</DialogDescription>
        </DialogHeader>

        <Tabs value={bulkRoomTab} onValueChange={setBulkRoomTab} className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="range">Range</TabsTrigger>
            <TabsTrigger value="template">Template</TabsTrigger>
            <TabsTrigger value="csv">CSV Import</TabsTrigger>
          </TabsList>

          <TabsContent value="range" className="pt-4">
            <form onSubmit={handleBulkCreateRange} className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Prefix</Label><Input value={bulkRange.prefix} onChange={(e) => setBulkRange(p => ({...p, prefix: e.target.value}))} placeholder="A" /></div>
                <div><Label>Start</Label><Input type="number" value={bulkRange.start_number} onChange={(e) => setBulkRange(p => ({...p, start_number: parseInt(e.target.value)}))} /></div>
                <div><Label>End</Label><Input type="number" value={bulkRange.end_number} onChange={(e) => setBulkRange(p => ({...p, end_number: parseInt(e.target.value)}))} /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>{t('booking.roomType')}</Label>
                  <Select value={bulkRange.room_type} onValueChange={(v) => setBulkRange(p => ({...p, room_type: v}))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="standard">Standard</SelectItem>
                      <SelectItem value="deluxe">Deluxe</SelectItem>
                      <SelectItem value="suite">Suite</SelectItem>
                      <SelectItem value="presidential">Presidential</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Floor</Label><Input type="number" value={bulkRange.floor} onChange={(e) => setBulkRange(p => ({...p, floor: parseInt(e.target.value)}))} /></div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Capacity</Label><Input type="number" value={bulkRange.capacity} onChange={(e) => setBulkRange(p => ({...p, capacity: parseInt(e.target.value)}))} /></div>
                <div><Label>Base Price</Label><Input type="number" step="0.01" value={bulkRange.base_price} onChange={(e) => setBulkRange(p => ({...p, base_price: parseFloat(e.target.value)}))} /></div>
                <div><Label>View</Label><Input value={bulkRange.view} onChange={(e) => setBulkRange(p => ({...p, view: e.target.value}))} placeholder="sea/city" /></div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
                <Button type="submit">{t('common.create')}</Button>
              </div>
            </form>
          </TabsContent>

          <TabsContent value="template" className="pt-4">
            <form onSubmit={handleBulkCreateTemplate} className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Prefix</Label><Input value={bulkTemplate.prefix} onChange={(e) => setBulkTemplate(p => ({...p, prefix: e.target.value}))} placeholder="B" /></div>
                <div><Label>Start</Label><Input type="number" value={bulkTemplate.start_number} onChange={(e) => setBulkTemplate(p => ({...p, start_number: parseInt(e.target.value)}))} /></div>
                <div><Label>Count</Label><Input type="number" value={bulkTemplate.count} onChange={(e) => setBulkTemplate(p => ({...p, count: parseInt(e.target.value)}))} /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>{t('booking.roomType')}</Label>
                  <Select value={bulkTemplate.room_type} onValueChange={(v) => setBulkTemplate(p => ({...p, room_type: v}))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="standard">Standard</SelectItem>
                      <SelectItem value="deluxe">Deluxe</SelectItem>
                      <SelectItem value="suite">Suite</SelectItem>
                      <SelectItem value="presidential">Presidential</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Floor</Label><Input type="number" value={bulkTemplate.floor} onChange={(e) => setBulkTemplate(p => ({...p, floor: parseInt(e.target.value)}))} /></div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Capacity</Label><Input type="number" value={bulkTemplate.capacity} onChange={(e) => setBulkTemplate(p => ({...p, capacity: parseInt(e.target.value)}))} /></div>
                <div><Label>Base Price</Label><Input type="number" step="0.01" value={bulkTemplate.base_price} onChange={(e) => setBulkTemplate(p => ({...p, base_price: parseFloat(e.target.value)}))} /></div>
                <div><Label>View</Label><Input value={bulkTemplate.view} onChange={(e) => setBulkTemplate(p => ({...p, view: e.target.value}))} placeholder="sea/city" /></div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
                <Button type="submit">{t('common.create')}</Button>
              </div>
            </form>
          </TabsContent>

          <TabsContent value="csv" className="pt-4">
            <form onSubmit={handleBulkImportCsv} className="space-y-4">
              <div className="text-sm text-gray-600">
                CSV columns: <span className="font-mono text-xs">room_number, room_type, floor, capacity, base_price, view, bed_type, amenities</span>
              </div>
              <Button type="button" variant="outline" onClick={downloadRoomsCsvTemplate}>
                <Download className="w-4 h-4 mr-2" />CSV Template
              </Button>
              <div><Label>CSV File</Label><Input type="file" accept=".csv,text/csv" onChange={(e) => setBulkCsvFile(e.target.files?.[0] || null)} /></div>
              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={onClose}>{t('common.close')}</Button>
                <Button type="submit" disabled={!bulkCsvFile}>Import</Button>
              </div>
            </form>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
};

export default BulkRoomsDialog;
