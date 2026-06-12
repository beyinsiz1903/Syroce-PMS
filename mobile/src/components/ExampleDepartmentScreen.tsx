// ── Reference screen pattern (Task #454) ────────────────────────────────────
// This is the canonical "liste -> detay -> aksiyon" template the 14 department
// screen tasks copy from. It is NOT a route (it lives in components/, not
// app/), so it ships nothing to users; it exists so every department screen
// renders loading / empty / error / data states and its detail + action flow
// identically, using only the shared kit in `ui.tsx`.
//
// HOW TO USE IT IN A REAL SCREEN
//   1. Copy this file into `app/(departments)/<name>.tsx` (or a Tier-2 group).
//   2. Replace the mock `useDemoData` with a real `useQuery` (see spa.tsx).
//   3. Replace every inline Turkish string below with `tr.<module>.<key>` from
//      your own i18n module file (e.g. `i18n/modules/departments/<name>.ts`) —
//      inline strings here are only so the template is self-contained.
//   4. Replace the local `selectedId` master/detail with a real detail route
//      (`router.push(\`\${ROUTES.x}/\${id}\`)`) if the detail is deep-linkable;
//      keep it inline only for lightweight peeks.
//
// The point of the template is the SHAPE, not the data.
import React, { useMemo, useState } from 'react';
import { ScrollView, View } from 'react-native';
import {
  ActionButton,
  Badge,
  Body,
  Button,
  Card,
  DetailHeader,
  DetailRow,
  Field,
  FormActions,
  H1,
  ListGroup,
  ListRow,
  Muted,
  SectionTitle,
  SegmentedActions,
  ActionSheet,
} from './ui';
import { DepartmentListState } from './department';
import { listViewState } from '../utils/departmentScreens';
import { spacing, useTheme } from '../theme';
import { formatCurrency } from '../utils/format';

type DemoStatus = 'pending' | 'done';

type DemoItem = {
  id: string;
  name: string;
  room: string;
  amount: number;
  status: DemoStatus;
  note: string;
};

// Lets the template show off every list state without a backend. A real screen
// deletes this and uses the loading / error / data a `useQuery` already gives.
type DataMode = 'data' | 'loading' | 'empty' | 'error';

const DEMO_ITEMS: DemoItem[] = [
  { id: '1', name: 'Ahmet Yılmaz', room: 'Oda 204', amount: 1450, status: 'pending', note: '' },
  { id: '2', name: 'Elif Demir', room: 'Oda 311', amount: 980, status: 'done', note: 'Ödendi' },
  { id: '3', name: 'Can Aydın', room: 'Oda 102', amount: 2300, status: 'pending', note: '' },
];

function useDemoData(mode: DataMode): {
  items: DemoItem[];
  loading: boolean;
  error: unknown;
} {
  return useMemo(() => {
    if (mode === 'loading') return { items: [], loading: true, error: null };
    if (mode === 'error') return { items: [], loading: false, error: new Error('Bağlantı hatası') };
    if (mode === 'empty') return { items: [], loading: false, error: null };
    return { items: DEMO_ITEMS, loading: false, error: null };
  }, [mode]);
}

function statusTone(s: DemoStatus): 'warning' | 'success' {
  return s === 'done' ? 'success' : 'warning';
}

function statusLabel(s: DemoStatus): string {
  return s === 'done' ? 'Tamamlandı' : 'Bekliyor';
}

export default function ExampleDepartmentScreen() {
  const c = useTheme();
  const [mode, setMode] = useState<DataMode>('data');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [note, setNote] = useState('');

  const { items, loading, error } = useDemoData(mode);
  const selected = items.find((i) => i.id === selectedId) || null;
  const state = listViewState({ loading, error, isEmpty: items.length === 0 });

  // ── DETAIL ────────────────────────────────────────────────────────────────
  // A self-contained detail view. In a deep-linkable screen this would be its
  // own route reading the id from `useLocalSearchParams`, with its own
  // loading / empty / error (a cold link has no warm list cache).
  if (selected) {
    return (
      <ScrollView
        style={{ flex: 1, backgroundColor: c.bg }}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
      >
        <DetailHeader
          title={selected.name}
          subtitle={selected.room}
          badges={<Badge label={statusLabel(selected.status)} tone={statusTone(selected.status)} />}
        />

        <Card>
          <DetailRow label="Tutar" value={formatCurrency(selected.amount)} />
          <DetailRow label="Durum" value={statusLabel(selected.status)} />
          <DetailRow label="Not" value={selected.note || '—'} />
        </Card>

        {/* Thumb-zone action bar: the shared segmented control. */}
        <View style={{ marginTop: spacing.lg }}>
          <SegmentedActions>
            <ActionButton
              label="Geri"
              icon="arrow-back"
              onPress={() => setSelectedId(null)}
              bg={c.surfaceAlt}
              fg={c.text}
            />
            <ActionButton
              label="İşlem yap"
              icon="create-outline"
              onPress={() => {
                setNote(selected.note);
                setSheetOpen(true);
              }}
              bg={c.primary}
              fg={c.primaryText}
            />
          </SegmentedActions>
        </View>

        {/* Action sheet: a compact form raised from the bottom. */}
        <ActionSheet visible={sheetOpen} onClose={() => setSheetOpen(false)} title="Not ekle">
          <Field
            label="Not"
            value={note}
            onChangeText={setNote}
            placeholder="Bir not yazın"
            multiline
          />
          <FormActions>
            <Button title="Vazgeç" variant="secondary" onPress={() => setSheetOpen(false)} />
            <Button title="Kaydet" onPress={() => setSheetOpen(false)} />
          </FormActions>
        </ActionSheet>
      </ScrollView>
    );
  }

  // ── LIST ────────────────────────────────────────────────────────────────
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>Örnek Departman</H1>
      <Muted style={{ marginTop: spacing.xs }}>
        Liste → detay → aksiyon deseni için referans şablon.
      </Muted>

      {/* Demo-only: switch the list state. A real screen deletes this row. */}
      <SectionTitle title="Durum (demo)" />
      <SegmentedActions>
        <ActionButton
          label="Veri"
          onPress={() => setMode('data')}
          bg={mode === 'data' ? c.primary : c.surfaceAlt}
          fg={mode === 'data' ? c.primaryText : c.text}
        />
        <ActionButton
          label="Yükleniyor"
          onPress={() => setMode('loading')}
          bg={mode === 'loading' ? c.primary : c.surfaceAlt}
          fg={mode === 'loading' ? c.primaryText : c.text}
        />
        <ActionButton
          label="Boş"
          onPress={() => setMode('empty')}
          bg={mode === 'empty' ? c.primary : c.surfaceAlt}
          fg={mode === 'empty' ? c.primaryText : c.text}
        />
        <ActionButton
          label="Hata"
          onPress={() => setMode('error')}
          bg={mode === 'error' ? c.primary : c.surfaceAlt}
          fg={mode === 'error' ? c.primaryText : c.text}
        />
      </SegmentedActions>

      <SectionTitle title="Kayıtlar" />
      {state !== 'data' ? (
        <DepartmentListState
          loading={loading}
          error={error}
          isEmpty={items.length === 0}
          emptyText="Kayıt bulunamadı"
        />
      ) : (
        <ListGroup>
          {items.map((it, idx) => (
            <ListRow
              key={it.id}
              icon="receipt-outline"
              label={it.name}
              sublabel={it.room}
              value={formatCurrency(it.amount)}
              right={<Badge label={statusLabel(it.status)} tone={statusTone(it.status)} />}
              showChevron
              last={idx === items.length - 1}
              onPress={() => setSelectedId(it.id)}
            />
          ))}
        </ListGroup>
      )}

      <Muted style={{ marginTop: spacing.lg }}>
        Bir kayda dokunun → detay; detayda “İşlem yap” → aksiyon sheet.
      </Muted>
      <Body style={{ marginTop: spacing.xs, color: c.textMuted }}>
        Gerçek ekranda metinler tr.&lt;modul&gt; anahtarlarından gelir.
      </Body>
    </ScrollView>
  );
}
