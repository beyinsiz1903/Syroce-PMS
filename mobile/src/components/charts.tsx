import React from 'react';
import { Text, View } from 'react-native';
import Svg, { Circle, G } from 'react-native-svg';
import { radius, spacing, useTheme, type ThemeColors } from '../theme';

// Web-safe, premium finansal grafik kiti (Stripe Dashboard hissi). Tum
// gorseller react-native-svg + RN View ile cizilir; reanimated/native-only
// API kullanmaz, Expo Web + native hedeflerinde birebir calisir. Renkler
// koyu premium palete (theme) gore secilir; deger biciminden bagimsizdir
// (cagiran tr-TR + TRY bicimleyiciyi `formatValue` ile gecirir).

export type ChartDatum = { label: string; value: number; color?: string };

// Kategorik seriler icin egrilmis, okunur premium palet. Mor->indigo /
// turuncu->amber konvansiyonuna uyar; her dilim net ve birbirinden ayrik.
export function chartPalette(c: ThemeColors): string[] {
  return [
    c.primary, // mavi
    c.info, // cyan
    c.success, // yesil
    c.vip, // altin
    '#818CF8', // indigo
    c.warning, // amber
    '#2DD4BF', // teal
    '#F472B6', // pembe accent
    c.danger, // kirmizi
    '#60A5FA', // acik mavi
  ];
}

// Halka (donut) kompozisyon grafigi: dilimleri strokeDasharray ile cizer,
// ortada buyuk toplam + kucuk etiket gosterir. Toplam 0 ise yalnizca soluk
// track halkasi gorunur (bos durum). Negatif/eksik degerler 0 sayilir.
export const DonutChart: React.FC<{
  data: ChartDatum[];
  size?: number;
  thickness?: number;
  centerLabel?: string;
  centerValue?: string;
}> = ({ data, size = 168, thickness = 24, centerLabel, centerValue }) => {
  const c = useTheme();
  const palette = chartPalette(c);
  const total = data.reduce((s, d) => s + Math.max(0, d.value), 0);
  const r = (size - thickness) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circ = 2 * Math.PI * r;
  let offset = 0;

  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size}>
        <G rotation={-90} origin={`${cx}, ${cy}`}>
          <Circle cx={cx} cy={cy} r={r} stroke={c.surfaceAlt} strokeWidth={thickness} fill="none" />
          {total > 0
            ? data.map((d, i) => {
                const v = Math.max(0, d.value);
                if (v <= 0) return null;
                const len = (v / total) * circ;
                const color = d.color || palette[i % palette.length];
                const node = (
                  <Circle
                    key={`${d.label}-${i}`}
                    cx={cx}
                    cy={cy}
                    r={r}
                    stroke={color}
                    strokeWidth={thickness}
                    fill="none"
                    strokeDasharray={`${len} ${circ - len}`}
                    strokeDashoffset={-offset}
                    strokeLinecap="butt"
                  />
                );
                offset += len;
                return node;
              })
            : null}
        </G>
      </Svg>
      {centerLabel || centerValue ? (
        <View style={{ position: 'absolute', alignItems: 'center', paddingHorizontal: spacing.sm }}>
          {centerValue ? (
            <Text
              style={{ color: c.text, fontSize: 19, fontWeight: '800', letterSpacing: -0.4 }}
              numberOfLines={1}
              adjustsFontSizeToFit
            >
              {centerValue}
            </Text>
          ) : null}
          {centerLabel ? (
            <Text style={{ color: c.textMuted, fontSize: 11, fontWeight: '600', marginTop: 2 }} numberOfLines={1}>
              {centerLabel}
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
};

// Halka/seri lejandi: renk noktasi + etiket + (istege bagli) deger. Donut ile
// yan yana ya da altinda kullanilir. `formatValue` verilirse deger gosterilir.
export const ChartLegend: React.FC<{
  data: ChartDatum[];
  formatValue?: (n: number) => string;
  maxRows?: number;
}> = ({ data, formatValue, maxRows = 6 }) => {
  const c = useTheme();
  const palette = chartPalette(c);
  const rows = [...data].sort((a, b) => b.value - a.value).slice(0, maxRows);
  return (
    <View style={{ gap: spacing.sm, flex: 1, minWidth: 0 }}>
      {rows.map((d, i) => {
        const color = d.color || palette[i % palette.length];
        return (
          <View
            key={`${d.label}-${i}`}
            style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}
          >
            <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: color }} />
            <Text style={{ color: c.textMuted, fontSize: 13, flex: 1 }} numberOfLines={1}>
              {d.label}
            </Text>
            {formatValue ? (
              <Text style={{ color: c.text, fontSize: 13, fontWeight: '700' }} numberOfLines={1}>
                {formatValue(d.value)}
              </Text>
            ) : null}
          </View>
        );
      })}
    </View>
  );
};

// Stripe "ust kalemler" tarzi siralanmis yatay oran cubuklari: her satir renk
// noktasi + etiket + deger, altinda en yuksek degere gore olceklenmis dolu
// cubuk. En buyukten kucuge siralar, `maxRows` ile sinirlar.
export const BarList: React.FC<{
  data: ChartDatum[];
  formatValue: (n: number) => string;
  maxRows?: number;
}> = ({ data, formatValue, maxRows = 6 }) => {
  const c = useTheme();
  const palette = chartPalette(c);
  const rows = [...data].sort((a, b) => b.value - a.value).slice(0, maxRows);
  const max = rows.reduce((m, d) => Math.max(m, d.value), 0) || 1;

  return (
    <View style={{ gap: spacing.md }}>
      {rows.map((d, i) => {
        const pct = Math.max(0, d.value) / max;
        const color = d.color || palette[i % palette.length];
        return (
          <View key={`${d.label}-${i}`} style={{ gap: 6 }}>
            <View
              style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flex: 1, paddingRight: spacing.sm }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: color }} />
                <Text style={{ color: c.text, fontSize: 13, fontWeight: '600', flex: 1 }} numberOfLines={1}>
                  {d.label}
                </Text>
              </View>
              <Text style={{ color: c.text, fontSize: 13, fontWeight: '700' }} numberOfLines={1}>
                {formatValue(d.value)}
              </Text>
            </View>
            <View style={{ height: 8, borderRadius: radius.pill, backgroundColor: c.surfaceAlt, overflow: 'hidden' }}>
              <View
                style={{
                  height: 8,
                  borderRadius: radius.pill,
                  width: `${Math.max(2, pct * 100)}%`,
                  backgroundColor: color,
                }}
              />
            </View>
          </View>
        );
      })}
    </View>
  );
};

// Tek satirda iki/uc deger karsilastirmasi icin dikey cubuk grubu (kasa akisi:
// Vergili Gelir / Tahsilat / Net Pozisyon). En yuksek mutlak degere gore
// olceklenir; negatif degerler (or. net pozisyon) danger tonunda gosterilir.
export const CompareBars: React.FC<{
  data: ChartDatum[];
  formatValue: (n: number) => string;
  height?: number;
}> = ({ data, formatValue, height = 132 }) => {
  const c = useTheme();
  const palette = chartPalette(c);
  const max = data.reduce((m, d) => Math.max(m, Math.abs(d.value)), 0) || 1;

  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: spacing.md }}>
      {data.map((d, i) => {
        const ratio = Math.abs(d.value) / max;
        const negative = d.value < 0;
        const color = d.color || (negative ? c.danger : palette[i % palette.length]);
        return (
          <View key={`${d.label}-${i}`} style={{ flex: 1, alignItems: 'center', gap: spacing.xs }}>
            <Text style={{ color: c.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1} adjustsFontSizeToFit>
              {formatValue(d.value)}
            </Text>
            <View
              style={{
                width: '70%',
                height,
                justifyContent: 'flex-end',
                backgroundColor: c.surfaceAlt,
                borderRadius: radius.sm,
                overflow: 'hidden',
              }}
            >
              <View
                style={{
                  height: Math.max(4, ratio * height),
                  backgroundColor: color,
                  borderTopLeftRadius: radius.sm,
                  borderTopRightRadius: radius.sm,
                }}
              />
            </View>
            <Text style={{ color: c.textMuted, fontSize: 11, fontWeight: '600', textAlign: 'center' }} numberOfLines={2}>
              {d.label}
            </Text>
          </View>
        );
      })}
    </View>
  );
};
