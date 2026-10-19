import { Ionicons } from '@expo/vector-icons';
import { Stack, router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useReport } from '@/api/hooks';
import type { Evidence } from '@/api/types';
import { LineChart } from '@/components/LineChart';
import { QueryState, Screen } from '@/components/Screen';
import { Button, Card, ChangeBadge, SectionTitle } from '@/components/ui';
import { keyStats, metricLabel, toolLabel, windowLabel } from '@/lib/format';
import { spacing, useColors } from '@/theme';

export default function FindingScreen() {
  const colors = useColors();
  const { id } = useLocalSearchParams<{ id: string }>();
  const report = useReport();

  return (
    <Screen>
      <QueryState query={report}>
        {() => {
          const finding = report.data!.findings.find((f) => f.id === id);
          if (!finding) {
            return <Text style={{ color: colors.muted }}>This finding is no longer available.</Text>;
          }
          return (
            <>
              <Stack.Screen options={{ title: metricLabel(finding.metric) }} />
              <View style={styles.row}>
                <Text style={[styles.title, { color: colors.text }]}>{finding.title}</Text>
                <ChangeBadge direction={finding.direction} label={finding.change} />
              </View>
              <Text style={[styles.summary, { color: colors.text }]}>{finding.summary}</Text>

              <Card>
                <LineChart
                  points={finding.series}
                  metric={finding.metric}
                  highlight={finding.highlight}
                  height={160}
                  showAxis
                />
                {finding.highlight && (
                  <Text style={[styles.caption, { color: colors.muted }]}>
                    Shaded: {windowLabel(finding.highlight)}
                  </Text>
                )}
              </Card>

              <SectionTitle>How we know</SectionTitle>
              {finding.evidenceIds.map((evidenceId) => {
                const evidence = report.data!.evidence[evidenceId];
                return evidence ? (
                  <EvidenceCard key={evidenceId} evidence={evidence} />
                ) : (
                  <Text key={evidenceId} style={{ color: colors.down }}>
                    Missing evidence {evidenceId}.
                  </Text>
                );
              })}

              <Button
                label="Ask about this"
                icon="chatbubble-ellipses-outline"
                onPress={() => router.push({ pathname: '/ask', params: { findingId: finding.id } })}
              />
              <Text style={[styles.caption, { color: colors.muted, textAlign: 'center' }]}>
                Patterns in your own Fitbit data, not medical advice.
              </Text>
            </>
          );
        }}
      </QueryState>
    </Screen>
  );
}

function EvidenceCard({ evidence }: { evidence: Evidence }) {
  const colors = useColors();
  const [showRaw, setShowRaw] = useState(false);

  return (
    <Card>
      <View style={styles.row}>
        <Text style={[styles.evidenceTitle, { color: colors.text }]}>{toolLabel(evidence.tool)}</Text>
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

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  title: { flex: 1, fontSize: 22, fontWeight: '700' },
  summary: { fontSize: 16, lineHeight: 23 },
  caption: { fontSize: 12 },
  evidenceTitle: { fontSize: 16, fontWeight: '600' },
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
});
