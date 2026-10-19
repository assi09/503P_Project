import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';

import { useDataStatus } from '@/api/hooks';
import type { DataStatus } from '@/api/types';
import { QueryState, Screen } from '@/components/Screen';
import { Card, SectionTitle } from '@/components/ui';
import { shortDate, timeAgo, windowLabel } from '@/lib/format';
import { radius, spacing, useColors } from '@/theme';

const SOURCE_LABELS: Record<DataStatus['source'], string> = {
  takeout: 'Google Takeout export',
  google_health: 'Google Health (synced)',
  none: 'No data yet',
};

export default function DataScreen() {
  const colors = useColors();
  const status = useDataStatus();

  return (
    <Screen refreshing={status.isRefetching} onRefresh={status.refetch}>
      <QueryState query={status}>
        {() => {
          const data = status.data!;
          return (
            <>
              <Card>
                <View style={styles.sourceRow}>
                  <Ionicons name="watch-outline" size={22} color={colors.accent} />
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.title, { color: colors.text }]}>
                      {SOURCE_LABELS[data.source]}
                    </Text>
                    <Text style={{ color: colors.muted, fontSize: 13 }}>
                      {data.lastSync ? `Updated ${timeAgo(data.lastSync)}` : 'Never updated'}
                      {data.range ? ` · ${windowLabel(data.range)}` : ''}
                    </Text>
                  </View>
                </View>
              </Card>

              <SectionTitle>Coverage</SectionTitle>
              <Card>
                <Text style={[styles.hint, { color: colors.muted }]}>
                  Share of days with data. Findings only use metrics with enough days.
                </Text>
                {data.coverage.map((c) => (
                  <View key={c.metric} style={styles.coverageRow}>
                    <Text style={[styles.coverageLabel, { color: colors.text }]}>{c.label}</Text>
                    <View
                      style={[styles.track, { backgroundColor: colors.border }]}
                      accessible
                      accessibilityLabel={`${c.label}: ${Math.round(c.fractionPresent * 100)}% of days`}
                    >
                      <View
                        style={[
                          styles.fill,
                          { width: `${Math.round(c.fractionPresent * 100)}%`, backgroundColor: colors.accent },
                        ]}
                      />
                    </View>
                    <Text style={[styles.percent, { color: colors.muted }]}>
                      {Math.round(c.fractionPresent * 100)}%
                    </Text>
                  </View>
                ))}
              </Card>

              <SectionTitle>Low wear days</SectionTitle>
              <Card>
                {data.lowWearDays.length === 0 ? (
                  <Text style={{ color: colors.muted }}>None. Your device was worn enough every day.</Text>
                ) : (
                  <>
                    <Text style={[styles.hint, { color: colors.muted }]}>
                      Under 10 hours of wear, so activity totals on these days are left out of
                      activity trends.
                    </Text>
                    <Text style={{ color: colors.text }}>
                      {data.lowWearDays.map(shortDate).join(', ')}
                    </Text>
                  </>
                )}
              </Card>

              <SectionTitle>Update your data</SectionTitle>
              <DisabledAction
                icon="cloud-upload-outline"
                title="Upload a new Takeout export"
                detail="Available once the app is connected to the server."
              />
              <DisabledAction
                icon="sync-outline"
                title="Connect Google Health"
                detail="Automatic syncing is planned."
              />

              <Text style={[styles.privacy, { color: colors.muted }]}>
                Your data is only used to analyze your own patterns. Profile and account details from
                the export are never read.
              </Text>
            </>
          );
        }}
      </QueryState>
    </Screen>
  );
}

function DisabledAction({
  icon,
  title,
  detail,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  detail: string;
}) {
  const colors = useColors();
  return (
    <Card style={styles.disabled}>
      <Ionicons name={icon} size={20} color={colors.muted} />
      <View style={{ flex: 1 }}>
        <Text style={[styles.title, { color: colors.muted }]}>{title}</Text>
        <Text style={{ color: colors.muted, fontSize: 13 }}>{detail}</Text>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  sourceRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  title: { fontSize: 16, fontWeight: '600' },
  hint: { fontSize: 13, lineHeight: 18 },
  coverageRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  coverageLabel: { width: 120, fontSize: 14 },
  track: { flex: 1, height: 8, borderRadius: radius.sm, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: radius.sm },
  percent: { width: 40, textAlign: 'right', fontSize: 13, fontVariant: ['tabular-nums'] },
  disabled: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, opacity: 0.8 },
  privacy: { fontSize: 12, textAlign: 'center', lineHeight: 17, marginTop: spacing.sm },
});
