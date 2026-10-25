import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, View } from 'react-native';

import type { DayMetric, ISODate } from '@/api/types';
import { LineChart } from '@/components/LineChart';
import { Text } from '@/components/Text';
import {
  ACCUMULATING,
  type Stage,
  bigValue,
  compare,
  dayTitle,
  fullDate,
  usualLine,
  valueText,
} from '@/lib/day';
import { select } from '@/lib/haptics';
import {
  METRIC_COLORS,
  fonts,
  radius,
  spacing,
  type as typeScale,
  useColors,
  useMetricColor,
  useScheme,
} from '@/theme';
import { isHovered } from '@/lib/platform';

/** The day's name in large type, its date, and arrows to the day before and after. */
export function DayHeader({
  date,
  today,
  first,
  last,
  partial,
  onChange,
}: {
  date: ISODate;
  today: ISODate; // the newest day with data
  first: ISODate;
  last: ISODate;
  partial: boolean;
  onChange: (date: ISODate | 'latest', step?: number) => void;
}) {
  const colors = useColors();
  const atFirst = date <= first;
  const atLast = date >= last;
  return (
    <View style={styles.header}>
      <View style={{ flex: 1 }}>
        <Text variant="label" color="muted">
          {partial ? `${fullDate(date)} · so far` : fullDate(date)}
        </Text>
        <Text variant="display" accessibilityRole="header">
          {dayTitle(date, today)}
        </Text>
      </View>
      <View style={styles.arrows}>
        {!atLast && (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Back to the latest day"
            onPress={() => {
              select();
              onChange('latest');
            }}
            style={(state) => [
              styles.latest,
              isHovered(state) && { backgroundColor: colors.track },
            ]}
          >
            <Text variant="caption" style={{ fontFamily: fonts.semibold }}>
              Latest
            </Text>
          </Pressable>
        )}
        <Arrow
          icon="chevron-back"
          label="Day before"
          disabled={atFirst}
          onPress={() => onChange(date, -1)}
        />
        <Arrow
          icon="chevron-forward"
          label="Day after"
          disabled={atLast}
          onPress={() => onChange(date, 1)}
        />
      </View>
    </View>
  );
}

function Arrow({
  icon,
  label,
  disabled,
  onPress,
}: {
  icon: 'chevron-back' | 'chevron-forward';
  label: string;
  disabled: boolean;
  onPress: () => void;
}) {
  const colors = useColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      hitSlop={6}
      onPress={() => {
        select();
        onPress();
      }}
      style={(state) => [
        styles.arrow,
        { borderColor: colors.border },
        (isHovered(state) || state.pressed) && !disabled && { backgroundColor: colors.track },
      ]}
    >
      <Ionicons name={icon} size={18} color={disabled ? colors.faint : colors.text} />
    </Pressable>
  );
}

/** One of the day's key values in large figures, its usual, and the last two weeks. */
export function KeyNumber({
  label,
  metric,
  partial,
  large,
  onPress,
}: {
  label: string;
  metric: DayMetric;
  partial: boolean;
  large: boolean; // on wide screens; phones show three numbers across in smaller figures
  onPress: () => void;
}) {
  const colors = useColors();
  const color = useMetricColor(metric.metric);
  const big = bigValue(metric.metric, metric.value);
  const figures = large ? typeScale.hero : typeScale.number;
  const points = metric.recent.map((value, i) => ({ date: String(i), value }));
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${label}: ${big.value} ${big.unit ?? ''}. ${usualLine(metric, partial)}`}
      onPress={onPress}
      style={(state) => [styles.key, isHovered(state) && { backgroundColor: colors.track }]}
    >
      <View style={styles.keyLabel}>
        <View style={[styles.dot, { backgroundColor: color }]} />
        <Text variant="caption" color="muted" numberOfLines={1}>
          {label}
        </Text>
      </View>
      <View style={styles.keyValue}>
        <Text style={figures} numberOfLines={1} adjustsFontSizeToFit>
          {big.value}
        </Text>
        {/* On a phone the label says what steps are; the unit would not fit beside them. */}
        {big.unit && (large || metric.metric !== 'steps') && (
          <Text variant="caption" color="muted" style={{ fontFamily: fonts.semibold }}>
            {big.unit}
          </Text>
        )}
      </View>
      <ComparisonText metric={metric} partial={partial} />
      {points.some((p) => p.value !== null) && (
        <View style={styles.spark}>
          <LineChart points={points} metric={metric.metric} height={28} strokeWidth={1.5} />
        </View>
      )}
    </Pressable>
  );
}

/** "Above your usual" with a small arrow; quiet when the value is in its usual range. */
function ComparisonText({ metric, partial }: { metric: DayMetric; partial: boolean }) {
  const color = useMetricColor(metric.metric);
  const comparison =
    partial && isAccumulating(metric.metric) ? null : compare(metric.value, metric.usual);
  const text =
    partial && isAccumulating(metric.metric)
      ? 'So far today'
      : comparison === 'above'
        ? 'Above usual'
        : comparison === 'below'
          ? 'Below usual'
          : comparison === 'usual'
            ? 'Within usual'
            : 'No usual yet';
  return (
    <View style={styles.comparison}>
      {(comparison === 'above' || comparison === 'below') && (
        <Ionicons
          name={comparison === 'above' ? 'arrow-up' : 'arrow-down'}
          size={12}
          color={color}
        />
      )}
      <Text variant="caption" color="muted" numberOfLines={1}>
        {text}
      </Text>
    </View>
  );
}

function isAccumulating(metric: string): boolean {
  return ACCUMULATING.has(metric);
}

/** A metric as one row: its name and how it compares, and its value at the right. */
export function MetricRow({
  label,
  metric,
  partial,
  onPress,
  value,
  detail,
}: {
  label: string;
  metric: DayMetric;
  partial: boolean;
  onPress?: () => void;
  value?: string; // shown instead of the metric's own formatting, e.g. a wake time
  detail?: string; // shown instead of the usual-range line
}) {
  const colors = useColors();
  const color = useMetricColor(metric.metric);
  const comparison = compare(metric.value, metric.usual);
  const shown = value ?? valueText(metric.metric, metric.value);
  const flagged =
    !(partial && isAccumulating(metric.metric)) && comparison && comparison !== 'usual';
  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityLabel={`${label}: ${shown}. ${detail ?? usualLine(metric, partial)}`}
      disabled={!onPress}
      onPress={onPress}
      style={(state) => [
        styles.row,
        isHovered(state) && onPress && { backgroundColor: colors.track },
      ]}
    >
      <View style={{ flex: 1, gap: 2 }}>
        <Text>{label}</Text>
        <Text variant="caption" color="muted" numberOfLines={1}>
          {detail ?? usualLine(metric, partial)}
        </Text>
      </View>
      {flagged && (
        <Ionicons
          name={comparison === 'above' ? 'arrow-up' : 'arrow-down'}
          size={14}
          color={color}
        />
      )}
      <Text style={styles.rowValue}>{shown}</Text>
      {onPress && <Ionicons name="chevron-forward" size={16} color={colors.faint} />}
    </Pressable>
  );
}

/** The night as one bar: awake, REM, light and deep sleep in shades of the sleep color. */
export function StagesBar({ stages }: { stages: Stage[] }) {
  const scheme = useScheme();
  const colors = useColors();
  const base = METRIC_COLORS.sleep[scheme];
  const shade: Record<Stage['key'], string> = {
    awake: colors.warning,
    rem: `${base}AA`,
    light: `${base}66`,
    deep: base,
  };
  return (
    <View style={styles.stages}>
      <View
        style={[styles.bar, { backgroundColor: colors.track }]}
        accessible
        accessibilityLabel={stages
          .map((s) => `${s.label} ${valueText('deep_sleep_minutes', s.minutes)}`)
          .join(', ')}
      >
        {stages.map((stage) => (
          <View key={stage.key} style={{ flex: stage.share, backgroundColor: shade[stage.key] }} />
        ))}
      </View>
      <View style={styles.legend}>
        {[...stages].reverse().map((stage) => (
          <View key={stage.key} style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: shade[stage.key] }]} />
            <Text variant="caption" color="muted">
              {stage.label}
            </Text>
            <Text
              variant="caption"
              style={{ fontFamily: fonts.semibold, fontVariant: ['tabular-nums'] }}
            >
              {valueText('deep_sleep_minutes', stage.minutes)}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: spacing.md,
    marginBottom: spacing.sm,
  },
  arrows: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, paddingBottom: 4 },
  arrow: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
  },
  latest: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill },
  key: {
    flex: 1,
    gap: 4,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    marginHorizontal: -spacing.sm,
    borderRadius: radius.md,
    minWidth: 0,
  },
  keyLabel: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  keyValue: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
  comparison: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  spark: { marginTop: 4 },
  // Side padding offset by a negative margin: text stays aligned, the hover tint gets room.
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.sm,
    marginHorizontal: -spacing.sm,
    minHeight: 56,
    borderRadius: radius.sm,
  },
  rowValue: { fontFamily: fonts.semibold, fontVariant: ['tabular-nums'] },
  stages: { gap: spacing.sm, paddingVertical: spacing.md },
  bar: { height: 10, borderRadius: radius.pill, overflow: 'hidden', flexDirection: 'row' },
  legend: { flexDirection: 'row', flexWrap: 'wrap', columnGap: spacing.lg, rowGap: 4 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
});
