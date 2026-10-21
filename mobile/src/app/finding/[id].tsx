import { Stack, router, useLocalSearchParams } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { useReport } from '@/api/hooks';
import { EvidenceCard } from '@/components/evidence';
import { LineChart } from '@/components/LineChart';
import { QueryState, Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { Button, Card, ChangeBadge, SectionTitle } from '@/components/ui';
import { metricLabel, windowLabel } from '@/lib/format';
import { metricFamily, METRIC_COLORS, spacing, useMetricColor } from '@/theme';

export default function FindingScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const report = useReport();

  return (
    <Screen>
      <QueryState query={report}>
        {() => {
          const finding = report.data!.findings.find((f) => f.id === id);
          if (!finding) {
            return <Text color="muted">This finding is no longer available.</Text>;
          }
          return <FindingDetail findingId={finding.id} />;
        }}
      </QueryState>
    </Screen>
  );
}

function FindingDetail({ findingId }: { findingId: string }) {
  const report = useReport().data!;
  const finding = report.findings.find((f) => f.id === findingId)!;
  const color = useMetricColor(finding.metric);
  const family = metricFamily(finding.metric);

  return (
    <>
      <Stack.Screen options={{ title: metricLabel(finding.metric) }} />
      <View style={styles.titleRow}>
        <Text variant="title" style={{ flex: 1 }}>
          {finding.title}
        </Text>
        <ChangeBadge direction={finding.direction} label={finding.change} color={color} />
      </View>
      <Text>{finding.summary}</Text>

      <Card glow={family ? METRIC_COLORS[family].gradient[0] : undefined}>
        <LineChart
          points={finding.series}
          metric={finding.metric}
          highlight={finding.highlight}
          height={180}
          showAxis
        />
        {finding.highlight && (
          <Text variant="caption" color="faint">
            Shaded: {windowLabel(finding.highlight)}
          </Text>
        )}
      </Card>

      <SectionTitle>How we know</SectionTitle>
      {finding.evidenceIds.map((evidenceId) => {
        const evidence = report.evidence[evidenceId];
        return evidence ? (
          <EvidenceCard key={evidenceId} evidence={evidence} />
        ) : (
          <Text key={evidenceId} color="danger">
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
      <Text variant="caption" color="faint" style={{ textAlign: 'center' }}>
        Patterns in your own Fitbit data, not medical advice.
      </Text>
    </>
  );
}

const styles = StyleSheet.create({
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
});
