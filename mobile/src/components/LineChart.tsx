import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Path, Rect } from 'react-native-svg';

import type { Point, Window } from '@/api/types';
import { chartGeometry } from '@/lib/chart';
import { formatValue, shortDate } from '@/lib/format';
import { useColors } from '@/theme';

interface Props {
  points: Point[];
  metric: string;
  highlight?: Window;
  height?: number;
  showAxis?: boolean; // min/max values and first/last dates
}

export function LineChart({ points, metric, highlight, height = 48, showAxis = false }: Props) {
  const colors = useColors();
  const [width, setWidth] = useState(0);
  const geometry = chartGeometry(points, width, height, highlight, 3);

  return (
    <View
      accessible
      accessibilityLabel={`${metric} chart from ${points[0]?.date ?? ''} to ${points.at(-1)?.date ?? ''}`}
    >
      <View style={{ flexDirection: 'row' }}>
        <View style={{ flex: 1 }} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
          {width > 0 && (
            <Svg width={width} height={height}>
              {geometry.highlight && (
                <Rect
                  x={geometry.highlight.x}
                  y={0}
                  width={geometry.highlight.width}
                  height={height}
                  fill={colors.chartHighlight}
                  rx={4}
                />
              )}
              {geometry.paths.map((d) => (
                <Path
                  key={d}
                  d={d}
                  stroke={colors.chart}
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
            <Text style={[styles.axisText, { color: colors.muted }]}>
              {formatValue(metric, geometry.max)}
            </Text>
            <Text style={[styles.axisText, { color: colors.muted }]}>
              {formatValue(metric, geometry.min)}
            </Text>
          </View>
        )}
      </View>
      {showAxis && points.length > 0 && (
        <View style={styles.xAxis}>
          <Text style={[styles.axisText, { color: colors.muted }]}>{shortDate(points[0].date)}</Text>
          <Text style={[styles.axisText, { color: colors.muted }]}>
            {shortDate(points[points.length - 1].date)}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  yAxis: { justifyContent: 'space-between', paddingLeft: 8 },
  xAxis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 },
  axisText: { fontSize: 11, fontVariant: ['tabular-nums'] },
});
