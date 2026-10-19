import { Stack, router, useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { useReport } from '@/api/hooks';
import { EvidenceCard } from '@/components/evidence';
import { LineChart } from '@/components/LineChart';
import { QueryState, Screen } from '@/components/Screen';
import { Button, Card, ChangeBadge, SectionTitle } from '@/components/ui';
import { metricLabel, windowLabel } from '@/lib/format';
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
                // dismissTo closes this screen and switches to the existing Ask tab; push and
                // navigate would stack a second copy of the tabs with its own chat.
                onPress={() => router.dismissTo({ pathname: '/ask', params: { findingId: finding.id } })}
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

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  title: { flex: 1, fontSize: 22, fontWeight: '700' },
  summary: { fontSize: 16, lineHeight: 23 },
  caption: { fontSize: 12 },
});
