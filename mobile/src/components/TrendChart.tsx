import React, { useId, useState } from 'react';
import { LayoutChangeEvent, View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Path, Stop } from 'react-native-svg';
import { useTheme } from '../theme';

// Web-safe sparkline / area chart built on react-native-svg (already a project
// dependency and renders identically on Expo Web). Draws a smooth gradient
// fill under a single value series with a marker on the latest point. The
// container width is measured via onLayout so the chart scales to any column
// without distorting the stroke (no viewBox stretching).
export const TrendChart: React.FC<{
  data: number[];
  height?: number;
  color?: string;
  testID?: string;
}> = ({ data, height = 168, color, testID }) => {
  const c = useTheme();
  const stroke = color ?? c.primary;
  const gradId = useId();
  const [width, setWidth] = useState(0);

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width);

  const padX = 8;
  const padY = 16;
  const n = data.length;
  const max = n ? Math.max(...data) : 0;
  const min = n ? Math.min(...data) : 0;
  const range = max - min || 1;

  const ready = width > 0 && n > 1;

  let linePath = '';
  let areaPath = '';
  let lastX = 0;
  let lastY = 0;

  if (ready) {
    const stepX = (width - padX * 2) / (n - 1);
    const toY = (v: number) => padY + (1 - (v - min) / range) * (height - padY * 2);
    const coords = data.map((v, i) => ({ x: padX + i * stepX, y: toY(v) }));
    linePath = coords
      .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)},${p.y.toFixed(2)}`)
      .join(' ');
    const baseline = height - padY;
    areaPath = `${linePath} L${coords[n - 1].x.toFixed(2)},${baseline.toFixed(2)} L${coords[0].x.toFixed(2)},${baseline.toFixed(2)} Z`;
    lastX = coords[n - 1].x;
    lastY = coords[n - 1].y;
  }

  return (
    <View testID={testID} onLayout={onLayout} style={{ width: '100%', height }}>
      {ready ? (
        <Svg width={width} height={height}>
          <Defs>
            <LinearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={stroke} stopOpacity={0.3} />
              <Stop offset="1" stopColor={stroke} stopOpacity={0} />
            </LinearGradient>
          </Defs>
          <Path d={areaPath} fill={`url(#${gradId})`} />
          <Path
            d={linePath}
            stroke={stroke}
            strokeWidth={2.5}
            fill="none"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <Circle cx={lastX} cy={lastY} r={5} fill={stroke} />
          <Circle cx={lastX} cy={lastY} r={9} fill={stroke} fillOpacity={0.18} />
        </Svg>
      ) : null}
    </View>
  );
};
