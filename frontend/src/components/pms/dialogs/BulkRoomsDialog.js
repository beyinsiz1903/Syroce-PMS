import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Plus, X, Calendar, User, CreditCard, BedDouble, Search,
  CheckCircle, Clock, DollarSign, MapPin, Phone, Mail,
  FileText, Download, Trash2, Edit, Eye, Star, Upload
} from 'lucide-react';


const BulkRoomsDialog = ({ openDialog, setOpenDialog, rooms, loadData, tenant }) => {
  const { t } = useTranslation();
  const [bulkRoomTab, setBulkRoomTab] = useState('range');
  const [bulkRoomData, setBulkRoomData] = useState({ prefix: '', start_number: 101, end_number: 110, floor: 1, room_type: 'Standard', capacity: 2, base_price: 100, amenities: [], view: '', bed_type: '' });
  const [csvFile, setCsvFile] = useState(null);
  const [csvPreview, setCsvPreview] = useState(null);

  return (
    <>
        <Dialog open={openDialog === 'bulk-rooms'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent className="max-w-3xl">
            <DialogHeader>
              <DialogTitle>Hızlı / Çoklu Oda Ekle</DialogTitle>
              <DialogDescription>
                100+ odayı tek tek eklemek yerine aralık (range), şablon (template) veya CSV ile içeri aktarabilirsiniz.
              </DialogDescription>
            </DialogHeader>

            <Tabs value={bulkRoomTab} onValueChange={setBulkRoomTab} className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="range">Aralık (Range)</TabsTrigger>
                <TabsTrigger value="template">Şablon (Template)</TabsTrigger>
                <TabsTrigger value="csv">CSV Import</TabsTrigger>
              </TabsList>

              <TabsContent value="range" className="pt-4">
                <form onSubmit={handleBulkCreateRange} className="space-y-4">
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <Label>Prefix (opsiyonel)</Label>
                      <Input value={bulkRange.prefix} onChange={(e) => setBulkRange(p => ({ ...p, prefix: e.target.value }))} placeholder="A" />
                    </div>
                    <div>
                      <Label>Başlangıç No</Label>
                      <Input type="number" value={bulkRange.start_number} onChange={(e) => setBulkRange(p => ({ ...p, start_number: parseInt(e.target.value) }))} />
                    </div>
                    <div>
                      <Label>Bitiş No</Label>
                      <Input type="number" value={bulkRange.end_number} onChange={(e) => setBulkRange(p => ({ ...p, end_number: parseInt(e.target.value) }))} />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Oda Tipi</Label>
                      <Select value={bulkRange.room_type} onValueChange={(v) => setBulkRange(p => ({ ...p, room_type: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="standard">Standard</SelectItem>
                          <SelectItem value="deluxe">Deluxe</SelectItem>
                          <SelectItem value="suite">Suite</SelectItem>
                          <SelectItem value="presidential">Presidential</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Kat</Label>
                      <Input type="number" value={bulkRange.floor} onChange={(e) => setBulkRange(p => ({ ...p, floor: parseInt(e.target.value) }))} />
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <Label>Kapasite</Label>
                      <Input type="number" value={bulkRange.capacity} onChange={(e) => setBulkRange(p => ({ ...p, capacity: parseInt(e.target.value) }))} />
                    </div>
                    <div>
                      <Label>Base Price</Label>
                      <Input type="number" step="0.01" value={bulkRange.base_price} onChange={(e) => setBulkRange(p => ({ ...p, base_price: parseFloat(e.target.value) }))} />
                    </div>
                    <div>
                      <Label>Manzara</Label>
                      <Input value={bulkRange.view} onChange={(e) => setBulkRange(p => ({ ...p, view: e.target.value }))} placeholder="sea/city/garden" />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Yatak Tipi</Label>
                      <Input value={bulkRange.bed_type} onChange={(e) => setBulkRange(p => ({ ...p, bed_type: e.target.value }))} placeholder="king/twin/queen" />
                    </div>
                    <div>
                      <Label>Amenities (| ile ayırın)</Label>
                      <Input
                        value={(bulkRange.amenities || []).join('|')}
                        onChange={(e) => setBulkRange(p => ({ ...p, amenities: e.target.value.split('|').map(s => s.trim()).filter(Boolean) }))}
                        placeholder="wifi|balcony|minibar"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end gap-2 pt-2">
                    <Button type="button" variant="outline" onClick={() => setOpenDialog(null)}>Vazgeç</Button>
                    <Button type="submit">Oluştur</Button>
                  </div>
                </form>
              </TabsContent>

              <TabsContent value="template" className="pt-4">
                <form onSubmit={handleBulkCreateTemplate} className="space-y-4">
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <Label>Prefix (opsiyonel)</Label>
                      <Input value={bulkTemplate.prefix} onChange={(e) => setBulkTemplate(p => ({ ...p, prefix: e.target.value }))} placeholder="B" />
                    </div>
                    <div>
                      <Label>Start No</Label>
                      <Input type="number" value={bulkTemplate.start_number} onChange={(e) => setBulkTemplate(p => ({ ...p, start_number: parseInt(e.target.value) }))} />
                    </div>
                    <div>
                      <Label>Adet</Label>
                      <Input type="number" value={bulkTemplate.count} onChange={(e) => setBulkTemplate(p => ({ ...p, count: parseInt(e.target.value) }))} />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Oda Tipi</Label>
                      <Select value={bulkTemplate.room_type} onValueChange={(v) => setBulkTemplate(p => ({ ...p, room_type: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="standard">Standard</SelectItem>
                          <SelectItem value="deluxe">Deluxe</SelectItem>
                          <SelectItem value="suite">Suite</SelectItem>
                          <SelectItem value="presidential">Presidential</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Kat</Label>
                      <Input type="number" value={bulkTemplate.floor} onChange={(e) => setBulkTemplate(p => ({ ...p, floor: parseInt(e.target.value) }))} />
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <Label>Kapasite</Label>
                      <Input type="number" value={bulkTemplate.capacity} onChange={(e) => setBulkTemplate(p => ({ ...p, capacity: parseInt(e.target.value) }))} />
                    </div>
                    <div>
                      <Label>Base Price</Label>
                      <Input type="number" step="0.01" value={bulkTemplate.base_price} onChange={(e) => setBulkTemplate(p => ({ ...p, base_price: parseFloat(e.target.value) }))} />
                    </div>
                    <div>
                      <Label>Manzara</Label>
                      <Input value={bulkTemplate.view} onChange={(e) => setBulkTemplate(p => ({ ...p, view: e.target.value }))} placeholder="sea/city/garden" />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Yatak Tipi</Label>
                      <Input value={bulkTemplate.bed_type} onChange={(e) => setBulkTemplate(p => ({ ...p, bed_type: e.target.value }))} placeholder="king/twin/queen" />
                    </div>
                    <div>
                      <Label>Amenities (| ile ayırın)</Label>
                      <Input
                        value={(bulkTemplate.amenities || []).join('|')}
                        onChange={(e) => setBulkTemplate(p => ({ ...p, amenities: e.target.value.split('|').map(s => s.trim()).filter(Boolean) }))}
                        placeholder="wifi|balcony|minibar"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end gap-2 pt-2">
                    <Button type="button" variant="outline" onClick={() => setOpenDialog(null)}>Vazgeç</Button>
                    <Button type="submit">Oluştur</Button>
                  </div>
                </form>
              </TabsContent>

              <TabsContent value="csv" className="pt-4">
                <form onSubmit={handleBulkImportCsv} className="space-y-4">
                  <div className="text-sm text-gray-600">
                    CSV kolonları: <span className="font-mono text-xs">room_number, room_type, floor, capacity, base_price, view, bed_type, amenities</span>
                    <br />
                    amenities alanında birden çok değer için <span className="font-mono text-xs">wifi|balcony|minibar</span> formatını kullan.
                  </div>

                  <div className="flex gap-2">
                    <Button type="button" variant="outline" onClick={downloadRoomsCsvTemplate}>
                      <Download className="w-4 h-4 mr-2" />
                      Örnek CSV indir
                    </Button>
                  </div>

                  <div>
                    <Label>CSV Dosyası</Label>
                    <Input type="file" accept=".csv,text/csv" onChange={(e) => setBulkCsvFile(e.target.files?.[0] || null)} />
                  </div>

                  <div className="text-xs text-gray-500">
                    CSV import backend endpoint&apos;i bir sonraki adımda eklenecek. Şimdilik range/template ile hızlı oluşturma hazır.
                  </div>

                  <div className="flex justify-end gap-2 pt-2">
                    <Button type="button" variant="outline" onClick={() => setOpenDialog(null)}>Kapat</Button>
                    <Button type="submit" disabled={!bulkCsvFile}>Import</Button>
                  </div>
                </form>
              </TabsContent>
            </Tabs>
          </DialogContent>
        </Dialog>
    </>
  );
};

export default BulkRoomsDialog;
