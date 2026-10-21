import { memo, useId, useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Defs, LinearGradient, Path, Rect, Stop } from 'react-native-svg';

import type { Point, Window } from '@/api/types';
import { Text } from '@/components/Text';
import { chartGeometry } from '@/lib/chart';
import { formatValue, shortDate } from '@/lib/format';
import { useMetricColor } from '@/theme';

interface Props {
  points: Point[];
  metric: string;
  highlight?: Window;
  height?: number;
  showAxis?: boolean; // min/max values and first/last dates
}

/** A line with a soft fill in the metric's color. Days without data stay as gaps. */
export const LineChart = memo(function LineChart({
  points,
  metric,
  highlight,
  height = 48,
  showAxis = false,
}: Props) {
  const color = useMetricColor(metric);
  const fillId = useId().replace(/:/g, '');
  const [width, setWidth] = useState(0);
  const geometry = useMemo(
    () => chartGeometry(points, width, height, highlight, 3),
    [points, width, height, highlight],
  );

  return (
    <View
      accessible
      accessibilityLabel={`${metric} chart from ${points[0]?.date ?? ''} to ${points.at(-1)?.date ?? ''}`}
    >
      <View style={{ flexDirection: 'row' }}>
        <View style={{ flex: 1 }} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
          {width > 0 && (
            <Svg width={width} height={height}>
              <Defs>
                <LinearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
                  <Stop offset="0" stopColor={color} stopOpacity={0.28} />
                  <Stop offset="1" stopColor={color} stopOpacity={0} />
                </LinearGradient>
              </Defs>
              {geometry.highlight && (
                <Rect
                  x={geometry.highlight.x}
                  y={0}
                  width={geometry.highlight.width}
                  height={height}
                  fill={color}
                  fillOpacity={0.08}
                  rx={6}
                />
              )}
              {geometry.areas.map((d) => (
                <Path key={`area-${d}`} d={d} fill={`url(#${fillId})`} />
              ))}
              {geometry.paths.map((d) => (
                <Path
                  key={d}
                  d={d}
                  stroke={color}
                  strokeWidth={2}
                  fill="none"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              ))}
            </Svg>
          )}
        </View>
        {showAxis && geometry.paths.length > 0 && (
          <View style={[styles.yAxis, { height }]}>
            <Text variant="caption" color="faint" style={styles.tabular}>
              {formatValue(metric, geometry.max)}
            </Text>
            <Text variant="caption" color="faint" style={styles.tabular}>
              {formatValue(metric, geometry.min)}
            </Text>
          </View>
        )}
      </View>
      {showAxis && points.length > 0 && (
        <View style={styles.xAxis}>
          <Text variant="caption" color="faint">
            {shortDate(points[0].date)}
          </Text>
          <Text variant="caption" color="faint">
            {shortDate(points[points.length - 1].date)}
          </Text>
        </View>
      )}
    </View>
  );
});

const styles = StyleSheet.create({
  yAxis: { justifyContent: 'space-between', paddingLeft: 8 },
  xAxis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
  tabular: { fontVariant: ['tabular-nums'] },
});
