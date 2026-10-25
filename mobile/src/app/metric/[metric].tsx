import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { useDay, useMetricSeries } from '@/api/hooks';
import type { ISODate, Point } from '@/api/types';
import { LineChart } from '@/components/LineChart';
import { Section, Stat } from '@/components/list';
import { Screen } from '@/components/Screen';
import { SegmentedControl } from '@/components/SegmentedControl';
import { Skeleton } from '@/components/Skeleton';
import { Text } from '@/components/Text';
import { Button } from '@/components/ui';
import { bigValue, dayTitle, metricOf, usualLine, valueText } from '@/lib/day';
import { metricLabel } from '@/lib/format';
import { useWide } from '@/lib/layout';
import { radius, spacing, useColors, useMetricColor } from '@/theme';
import { isHovered } from '@/lib/platform';

const SPANS = { '7 days': 7, '30 days': 30, '90 days': 90 } as const;
type Span = keyof typeof SPANS;

/** One metric: the day's value, the last weeks as a chart with the usual band, and the days. */
export default function MetricScreen() {
  const { metric, date } = useLocalSearchParams<{ metric: string; date?: string }>();
  const [span, setSpan] = useState<Span>('30 days');
  const [selected, setSelected] = useState<ISODate | undefined>(date || undefined);
  const day = useDay(selected ?? 'latest');
  const series = useMetricSeries(metric, SPANS[span], day.data?.date);
  const color = useMetricColor(metric);
  const colors = useColors();
  const wide = useWide();
  const label = metricLabel(metric);

  const value = day.data ? metricOf(day.data, metric) : undefined;
  const big = value ? bigValue(metric, value.value) : undefined;
  const points = series.data?.points ?? [];
  const known = points.filter((p): p is Point & { value: number } => p.value !== null);
  const average = known.length ? known.reduce((sum, p) => sum + p.value, 0) / known.length : null;

  return (
    <Screen wide>
      <Stack.Screen options={{ title: label }} />
      {!day.data || !value || !big ? (
        <View style={{ gap: spacing.md }}>
          <Skeleton height={14} width={120} radius={radius.sm} />
          <Skeleton height={48} width={180} radius={radius.sm} />
          <Skeleton height={200} radius={radius.md} />
        </View>
      ) : (
        <View style={wide ? styles.columns : undefined}>
          <View style={[wide && styles.main, { gap: spacing.lg }]}>
            <View style={{ gap: spacing.xs }}>
              <Text variant="label" color="muted">
                {dayTitle(day.data.date, day.data.last)}
                {day.data.partial ? ' · so far' : ''}
              </Text>
              <Stat value={big.value} unit={big.unit} label={usualLine(value, day.data.partial)} />
            </View>

            <View style={{ gap: spacing.md }}>
              <SegmentedControl
                options={Object.keys(SPANS) as Span[]}
                value={span}
                onChange={setSpan}
                accessibilityLabel="Period"
              />
              <View style={{ opacity: series.isPlaceholderData ? 0.5 : 1 }}>
                {series.data ? (
                  <LineChart
                    points={points}
                    metric={metric}
                    height={wide ? 240 : 180}
                    showAxis
                    fill={false}
                    usual={series.data.usual}
                    marker={day.data.date}
                  />
                ) : (
                  <Skeleton height={wide ? 240 : 180} radius={radius.md} />
                )}
              </View>
              <View style={styles.legend}>
                <View style={[styles.band, { backgroundColor: color, opacity: 0.18 }]} />
                <Text variant="caption" color="muted">
                  Your usual range: the middle half of the four weeks before
                </Text>
              </View>
            </View>

            <View style={[styles.summary, { borderColor: colors.border }]}>
              <Summary
                label={`${span} average`}
                value={average === null ? '–' : valueText(metric, average)}
              />
              <Summary
                label="Lowest"
                value={
                  known.length ? valueText(metric, Math.min(...known.map((p) => p.value))) : '–'
                }
              />
              <Summary
                label="Highest"
                value={
                  known.length ? valueText(metric, Math.max(...known.map((p) => p.value))) : '–'
                }
              />
            </View>

            <View style={styles.ask}>
              <Button
                label={`Ask about ${label.toLowerCase()}`}
                icon="sparkles-outline"
                onPress={() => router.push({ pathname: '/ask', params: { metric } })}
              />
            </View>
          </View>

          <View style={wide ? styles.side : undefined}>
            <Section title="Day by day">
              {[...points]
                .reverse()
                .slice(0, 14)
                .map((point) => (
                  <DayRow
                    key={point.date}
                    metric={metric}
                    point={point}
                    last={day.data!.last}
                    selected={point.date === day.data!.date}
                    onPress={() => setSelected(point.date)}
                  />
                ))}
            </Section>
          </View>
        </View>
      )}
    </Screen>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1, gap: 2 }}>
      <Text variant="caption" color="muted">
        {label}
      </Text>
      <Text variant="bodyStrong" style={{ fontVariant: ['tabular-nums'] }}>
        {value}
      </Text>
    </View>
  );
}

function DayRow({
  metric,
  point,
  last,
  selected,
  onPress,
}: {
  metric: string;
  point: Point;
  last: ISODate;
  selected: boolean;
  onPress: () => void;
}) {
  const colors = useColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      disabled={point.value === null}
      style={(state) => [
        styles.dayRow,
        (isHovered(state) || selected) && { backgroundColor: colors.track },
      ]}
    >
      <Text style={{ flex: 1 }} color={selected ? 'text' : undefined}>
        {dayTitle(point.date, last)}
      </Text>
      <Text style={styles.dayValue} color={point.value === null ? 'faint' : 'text'}>
        {point.value === null ? 'No data' : valueText(metric, point.value)}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  columns: { flexDirection: 'row', gap: spacing.xxl, alignItems: 'flex-start' },
  main: { flex: 3, minWidth: 0 },
  side: { flex: 2, minWidth: 0 },
  legend: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  band: { width: 16, height: 10, borderRadius: 3 },
  summary: {
    flexDirection: 'row',
    gap: spacing.md,
    paddingVertical: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  ask: { flexDirection: 'row', marginBottom: spacing.md },
  dayRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.sm,
    marginHorizontal: -spacing.sm,
    borderRadius: radius.sm,
  },
  dayValue: { fontVariant: ['tabular-nums'], minWidth: 90, textAlign: 'right' },
});
