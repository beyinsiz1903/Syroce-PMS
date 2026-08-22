import { useId, useMemo } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export const COMMON_ROOM_TYPES = [
  'Standard',
  'Deluxe',
  'Superior',
  'Suite',
  'Junior Suite',
  'Family',
  'Presidential',
  'Ağaç Ev',
  'Bungalov',
];

export const BED_TYPE_OPTIONS = [
  { value: 'king', label: 'King / Büyük Çift Kişilik Yatak' },
  { value: 'queen', label: 'Queen / Çift Kişilik Yatak' },
  { value: 'twin', label: 'Twin / İki Tek Kişilik Yatak' },
  { value: 'double', label: 'Double / Çift Kişilik Yatak' },
  { value: 'single', label: 'Single / Tek Kişilik Yatak' },
  { value: 'bunk', label: 'Ranza' },
  { value: 'sofa_bed', label: 'Çekyat' },
];

export const EMPTY_ROOM_CONFIGURATION = {
  room_number: '',
  room_type: 'Standard',
  floor: 1,
  capacity: 2,
  base_price: 100,
  view: '',
  bed_type: '',
};

export function roomToConfiguration(room = {}) {
  return {
    room_number: room.room_number || '',
    room_type: room.room_type || 'Standard',
    floor: Number.isFinite(Number(room.floor)) ? Number(room.floor) : 1,
    capacity: Number.isFinite(Number(room.capacity)) ? Number(room.capacity) : 2,
    base_price: Number.isFinite(Number(room.base_price)) ? Number(room.base_price) : 0,
    view: room.view || '',
    bed_type: room.bed_type || '',
  };
}

export function normalizeRoomConfiguration(room) {
  return {
    room_number: String(room.room_number || '').trim(),
    room_type: String(room.room_type || '').trim(),
    floor: Number(room.floor),
    capacity: Number(room.capacity),
    base_price: Number(room.base_price),
    view: String(room.view || '').trim() || null,
    bed_type: String(room.bed_type || '').trim() || null,
  };
}

export function validateRoomConfiguration(room) {
  const normalized = normalizeRoomConfiguration(room);
  if (!normalized.room_number) return 'Oda numarası zorunludur';
  if (!normalized.room_type) return 'Oda tipi zorunludur';
  if (!Number.isInteger(normalized.floor) || normalized.floor < 0) return 'Kat, sıfır veya daha büyük bir tam sayı olmalıdır';
  if (!Number.isInteger(normalized.capacity) || normalized.capacity < 1) return 'Kapasite en az 1 olmalıdır';
  if (!Number.isFinite(normalized.base_price) || normalized.base_price < 0) return 'Taban fiyat negatif olamaz';
  return null;
}

export function RoomTypeInput({ value, onChange, suggestions = [], testId, idPrefix = 'room-type' }) {
  const generatedId = useId().replace(/:/g, '');
  const listId = `${idPrefix}-${generatedId}`;
  const options = useMemo(
    () => [...new Set([...COMMON_ROOM_TYPES, ...suggestions].filter(Boolean).map(item => String(item).trim()).filter(Boolean))],
    [suggestions],
  );

  return (
    <div>
      <Label htmlFor={listId}>Oda Tipi *</Label>
      <Input
        id={listId}
        list={`${listId}-options`}
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder="Örn. Ağaç Ev, Bungalov, Deluxe"
        required
        data-testid={testId}
      />
      <datalist id={`${listId}-options`}>
        {options.map(option => <option key={option} value={option} />)}
      </datalist>
      <p className="mt-1 text-xs text-slate-500">Listede yoksa oda tipini doğrudan yazabilirsiniz.</p>
    </div>
  );
}

export function BedTypeSelect({ value, onChange, testId }) {
  return (
    <div>
      <Label>Yatak Tipi</Label>
      <Select value={value || 'unspecified'} onValueChange={selected => onChange(selected === 'unspecified' ? '' : selected)}>
        <SelectTrigger data-testid={testId}><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="unspecified">Belirtilmemiş</SelectItem>
          {BED_TYPE_OPTIONS.map(option => (
            <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export default function RoomConfigurationFields({ value, onChange, roomTypeSuggestions = [], testIdPrefix = 'room' }) {
  const setField = (field, fieldValue) => onChange({ ...value, [field]: fieldValue });

  return (
    <div className="space-y-3">
      <div>
        <Label>Oda Numarası *</Label>
        <Input
          value={value.room_number}
          onChange={event => setField('room_number', event.target.value)}
          placeholder="207"
          required
          data-testid={`${testIdPrefix}-number`}
        />
      </div>
      <RoomTypeInput
        value={value.room_type}
        onChange={roomType => setField('room_type', roomType)}
        suggestions={roomTypeSuggestions}
        testId={`${testIdPrefix}-type`}
        idPrefix={`${testIdPrefix}-type`}
      />
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Kat</Label>
          <Input
            type="number"
            min={0}
            step={1}
            value={value.floor}
            onChange={event => setField('floor', event.target.value)}
            required
            data-testid={`${testIdPrefix}-floor`}
          />
        </div>
        <div>
          <Label>Kapasite</Label>
          <Input
            type="number"
            min={1}
            step={1}
            value={value.capacity}
            onChange={event => setField('capacity', event.target.value)}
            required
            data-testid={`${testIdPrefix}-capacity`}
          />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <Label>Taban Fiyat</Label>
          <Input
            type="number"
            min={0}
            step="0.01"
            value={value.base_price}
            onChange={event => setField('base_price', event.target.value)}
            required
            data-testid={`${testIdPrefix}-base-price`}
          />
        </div>
        <div>
          <Label>Manzara</Label>
          <Input
            value={value.view}
            onChange={event => setField('view', event.target.value)}
            placeholder="Göl, orman, bahçe…"
            data-testid={`${testIdPrefix}-view`}
          />
        </div>
      </div>
      <BedTypeSelect
        value={value.bed_type}
        onChange={bedType => setField('bed_type', bedType)}
        testId={`${testIdPrefix}-bed-type`}
      />
    </div>
  );
}
