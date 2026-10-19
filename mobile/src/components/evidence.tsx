import { Ionicons } from '@expo/vector-icons';
import { Link } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Evidence } from '@/api/types';
import { Card } from '@/components/ui';
import { keyStats, metricLabel, toolLabel, windowLabel } from '@/lib/format';
import { spacing, useColors } from '@/theme';

export function EvidenceCard({ evidence }: { evidence: Evidence }) {
  const colors = useColors();
  const [showRaw, setShowRaw] = useState(false);

  return (
    <Card>
      <View style={styles.row}>
        <Text style={[styles.title, { color: colors.text }]}>{toolLabel(evidence.tool)}</Text>
        {!evidence.sufficient && (
          <Text style={[styles.warning, { color: colors.warning }]}>Too little data</Text>
        )}
      </View>
      <Text style={[styles.caption, { color: colors.muted }]}>
        {evidence.metrics.map(metricLabel).join(' and ')} ·{' '}
        {evidence.windows.map(windowLabel).join(' vs ')}
      </Text>
      {keyStats(evidence).map((line) => (
        <View key={line.label} style={styles.statRow}>
          <Text style={{ color: colors.muted }}>{line.label}</Text>
          <Text style={[styles.statValue, { color: colors.text }]}>{line.value}</Text>
        </View>
      ))}
      <Pressable
        accessibilityRole="button"
        onPress={() => setShowRaw((value) => !value)}
        style={styles.rawToggle}
      >
        <Text style={{ color: colors.accent, fontSize: 13 }}>
          {showRaw ? 'Hide' : 'Show'} all statistics
        </Text>
        <Ionicons name={showRaw ? 'chevron-up' : 'chevron-down'} size={14} color={colors.accent} />
      </Pressable>
      {showRaw && (
        <Text selectable style={[styles.raw, { color: colors.muted, borderColor: colors.border }]}>
          {JSON.stringify({ id: evidence.id, tool: evidence.tool, n: evidence.n, ...evidence.stats }, null, 2)}
        </Text>
      )}
    </Card>
  );
}

/** A compact link to one piece of evidence, shown under chat answers. */
export function EvidenceChip({ id, label }: { id: string; label: string }) {
  const colors = useColors();
  return (
    <Link href={`/evidence/${id}`} asChild>
      <Pressable
        accessibilityRole="link"
        accessibilityHint="Shows the computation behind this answer"
        // Link (asChild) needs a single style object: it rejects arrays and pressed-state functions.
        style={StyleSheet.flatten([
          styles.chip,
          { borderColor: colors.border, backgroundColor: colors.surface },
        ])}
      >
        <Ionicons name="stats-chart-outline" size={12} color={colors.accent} />
        <Text style={{ color: colors.accent, fontSize: 12, fontWeight: '600' }}>{label}</Text>
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  title: { fontSize: 16, fontWeight: '600' },
  caption: { fontSize: 12 },
  warning: { fontSize: 12, fontWeight: '600' },
  statRow: { flexDirection: 'row', justifyContent: 'space-between' },
  statValue: { fontWeight: '600', fontVariant: ['tabular-nums'] },
  rawToggle: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingTop: spacing.xs },
  raw: {
    fontFamily: 'Courier',
    fontSize: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: spacing.sm,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
    borderWidth: 1,
  },
});
