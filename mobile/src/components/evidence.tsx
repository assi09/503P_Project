import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import type { Evidence } from '@/api/types';
import { PressableScale } from '@/components/PressableScale';
import { Text } from '@/components/Text';
import { Card } from '@/components/ui';
import { keyStats, metricLabel, toolLabel, verdict, windowLabel } from '@/lib/format';
import { radius, spacing, useColors, useMetricColor } from '@/theme';

const TOOL_ICONS = {
  compare_windows: 'git-compare-outline',
  trend: 'trending-up-outline',
  correlate: 'git-network-outline',
  describe: 'stats-chart-outline',
  coverage: 'grid-outline',
} as const;

export function EvidenceCard({ evidence }: { evidence: Evidence }) {
  const colors = useColors();
  const color = useMetricColor(evidence.metrics[0] ?? '');
  const [showRaw, setShowRaw] = useState(false);
  const icon = TOOL_ICONS[evidence.tool as keyof typeof TOOL_ICONS] ?? 'calculator-outline';
  const stats = keyStats(evidence);
  const result = verdict(evidence);

  return (
    <Card>
      <View style={styles.header}>
        <View style={[styles.icon, { backgroundColor: `${color}22` }]}>
          <Ionicons name={icon} size={16} color={color} />
        </View>
        <View style={{ flex: 1 }}>
          <Text variant="headline">{toolLabel(evidence.tool)}</Text>
          <Text variant="caption" color="muted">
            {evidence.metrics.map(metricLabel).join(' and ')}
          </Text>
        </View>
        {!evidence.sufficient && (
          <View style={[styles.warning, { backgroundColor: `${colors.warning}22` }]}>
            <Text variant="caption" color="warning">
              Too little data
            </Text>
          </View>
        )}
      </View>
      <Text variant="caption" color="faint">
        {evidence.windows.map(windowLabel).join('  vs  ')}
      </Text>
      {result && (
        <View style={styles.verdict}>
          <View
            style={[styles.dot, { backgroundColor: result.clear ? color : colors.faint }]}
          />
          <Text variant="caption" style={{ flex: 1 }}>
            {result.text}
          </Text>
        </View>
      )}
      <View style={[styles.stats, { borderColor: colors.border }]}>
        {stats.map((line, i) => (
          <View
            key={line.label}
            style={[
              styles.statRow,
              i > 0 && { borderTopColor: colors.border, borderTopWidth: StyleSheet.hairlineWidth },
            ]}
          >
            <Text color="muted">{line.label}</Text>
            <Text variant="bodyStrong" style={{ fontVariant: ['tabular-nums'] }}>
              {line.value}
            </Text>
          </View>
        ))}
      </View>
      <Pressable
        accessibilityRole="button"
        onPress={() => setShowRaw((value) => !value)}
        style={styles.rawToggle}
        hitSlop={8}
      >
        <Text variant="caption" color="muted">
          {showRaw ? 'Hide' : 'Show'} all statistics
        </Text>
        <Ionicons name={showRaw ? 'chevron-up' : 'chevron-down'} size={14} color={colors.muted} />
      </Pressable>
      {showRaw && (
        <Text
          selectable
          variant="caption"
          color="muted"
          style={[styles.raw, { backgroundColor: colors.background, borderColor: colors.border }]}
        >
          {JSON.stringify(
            { id: evidence.id, tool: evidence.tool, n: evidence.n, ...evidence.stats },
            null,
            2,
          )}
        </Text>
      )}
    </Card>
  );
}

/** A compact link to one piece of evidence, shown under chat answers. */
export function EvidenceChip({ id, label, metric }: { id: string; label: string; metric?: string }) {
  const color = useMetricColor(metric ?? '');
  return (
    <PressableScale
      accessibilityRole="link"
      accessibilityHint="Shows the computation behind this answer"
      onPress={() => router.push(`/evidence/${id}`)}
      style={[styles.chip, { backgroundColor: `${color}1F`, borderColor: `${color}55` }]}
    >
      <Ionicons name="stats-chart" size={11} color={color} />
      <Text variant="caption" color={color} style={styles.chipText} numberOfLines={1}>
        {label}
      </Text>
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  icon: {
    width: 34,
    height: 34,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  warning: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill },
  verdict: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  dot: { width: 8, height: 8, borderRadius: 4 },
  stats: { borderTopWidth: StyleSheet.hairlineWidth, marginTop: spacing.xs },
  statRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 10 },
  chipText: { fontSize: 12, flexShrink: 1 }, // a long label ends with … instead of overflowing
  rawToggle: { flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start' },
  raw: {
    fontFamily: 'Courier',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radius.sm,
    padding: spacing.sm,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
    maxWidth: '100%',
  },
});
