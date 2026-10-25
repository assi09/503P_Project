import { memo, useId, useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Path, Rect, Stop } from 'react-native-svg';

import type { ISODate, Point, Usual, Window } from '@/api/types';
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
  usual?: Usual | null; // drawn as a band behind the line
  marker?: ISODate; // a dot on this day's value
  strokeWidth?: number;
  fill?: boolean; // the soft area under the line; off where a usual band is drawn large
}

/** A line with a soft fill in the metric's color. Days without data stay as gaps. */
export const LineChart = memo(function LineChart({
  points,
  metric,
  highlight,
  height = 48,
  showAxis = false,
  usual,
  marker,
  strokeWidth = 2,
  fill = true,
}: Props) {
  const color = useMetricColor(metric);
  const fillId = useId().replace(/:/g, '');
  const [width, setWidth] = useState(0);
  const geometry = useMemo(
    () => chartGeometry(points, width, height, highlight, 3, usual ?? undefined),
    [points, width, height, highlight, usual],
  );
  const markerIndex = marker ? points.findIndex((p) => p.date === marker) : -1;
  const dot = markerIndex >= 0 ? geometry.coords[markerIndex] : null;

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
              {geometry.band && (
                <Rect
                  x={0}
                  y={geometry.band.y}
                  width={width}
                  height={geometry.band.height}
                  fill={color}
                  fillOpacity={0.1}
                  rx={3}
                />
              )}
              {fill && geometry.areas.map((d) => (
                <Path key={`area-${d}`} d={d} fill={`url(#${fillId})`} />
              ))}
              {geometry.paths.map((d) => (
                <Path
                  key={d}
                  d={d}
                  stroke={color}
                  strokeWidth={strokeWidth}
                  fill="none"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              ))}
              {dot && <Circle cx={dot.x} cy={dot.y} r={strokeWidth + 2} fill={color} />}
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
