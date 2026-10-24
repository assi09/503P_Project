import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { useDataStatus } from '@/api/hooks';
import type { DataStatus, MetricCoverage } from '@/api/types';
import { QueryState, Screen } from '@/components/Screen';
import { SegmentedControl } from '@/components/SegmentedControl';
import { PressableScale } from '@/components/PressableScale';
import { Text } from '@/components/Text';
import { Button, Card, SectionTitle } from '@/components/ui';
import { shortDate, timeAgo, windowLabel } from '@/lib/format';
import { useSession } from '@/lib/session';
import { radius, spacing, useColors, useMetricColor, useThemePreference } from '@/theme';

const SOURCE_LABELS: Record<DataStatus['source'], string> = {
  takeout: 'Google Takeout export',
  google_health: 'Google Health (synced)',
  none: 'No data yet',
};

export default function DataScreen() {
  const colors = useColors();
  const status = useDataStatus();

  return (
    <Screen title="Data" refreshing={status.isRefetching} onRefresh={status.refetch}>
      <QueryState query={status}>
        {() => {
          const data = status.data!;
          return (
            <>
              <Card glow={colors.accent}>
                <View style={styles.sourceRow}>
                  <View style={[styles.icon, { backgroundColor: colors.accentSoft }]}>
                    <Ionicons name="watch" size={18} color={colors.accent} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text variant="headline">{SOURCE_LABELS[data.source]}</Text>
                    <Text variant="caption" color="muted">
                      {data.lastSync ? `Updated ${timeAgo(data.lastSync)}` : 'Never updated'}
                      {data.range ? ` · ${windowLabel(data.range)}` : ''}
                    </Text>
                  </View>
                </View>
              </Card>

              <SectionTitle>Coverage</SectionTitle>
              <Card>
                <Text variant="caption" color="muted">
                  Share of days with data. Findings only use metrics with enough days.
                </Text>
                {data.coverage.map((c) => (
                  <CoverageRow key={c.metric} coverage={c} />
                ))}
              </Card>

              <SectionTitle>Low wear days</SectionTitle>
              <Card>
                {data.lowWearDays.length === 0 ? (
                  <Text color="muted">None. Your device was worn enough every day.</Text>
                ) : (
                  <>
                    <Text variant="caption" color="muted">
                      Under 10 hours of wear, so activity totals on these days are left out of
                      activity trends.
                    </Text>
                    <View style={styles.days}>
                      {data.lowWearDays.map((day) => (
                        <View
                          key={day}
                          style={[styles.day, { backgroundColor: colors.surfaceRaised }]}
                        >
                          <Text variant="caption">{shortDate(day)}</Text>
                        </View>
                      ))}
                    </View>
                  </>
                )}
              </Card>

              <SectionTitle>Update your data</SectionTitle>
              <DisabledAction
                icon="cloud-upload"
                title="Upload a new Takeout export"
                detail="Uploading from the app is coming next."
              />
              <DisabledAction
                icon="sync"
                title="Connect Google Health"
                detail="Automatic syncing is planned."
              />

              <Text variant="caption" color="faint" style={styles.privacy}>
                Your data is only used to analyze your own patterns. Profile and account details
                from the export are never read.
              </Text>
            </>
          );
        }}
      </QueryState>

      {/* Outside the data: someone whose data cannot load can still sign out. */}
      <SectionTitle>Appearance</SectionTitle>
      <AppearanceSwitch />

      <SectionTitle>Account</SectionTitle>
      <AccountCard />
    </Screen>
  );
}

function AccountCard() {
  const colors = useColors();
  const { account, logOut } = useSession();
  return (
    <Card>
      <Text variant="headline">{account?.email}</Text>
      {account?.isAdmin && (
        <PressableScale
          accessibilityRole="link"
          onPress={() => router.push('/approvals')}
          style={styles.accountRow}
        >
          <Ionicons name="people-outline" size={18} color={colors.text} />
          <Text style={{ flex: 1 }}>Access requests</Text>
          <Ionicons name="chevron-forward" size={16} color={colors.faint} />
        </PressableScale>
      )}
      <View style={styles.accountActions}>
        <Button label="Sign out" variant="secondary" icon="log-out-outline" onPress={logOut} />
      </View>
    </Card>
  );
}

const APPEARANCE = { System: 'system', Light: 'light', Dark: 'dark' } as const;
type AppearanceLabel = keyof typeof APPEARANCE;

function AppearanceSwitch() {
  const { preference, setPreference } = useThemePreference();
  const labels = Object.keys(APPEARANCE) as AppearanceLabel[];
  const current = labels.find((label) => APPEARANCE[label] === preference) ?? 'System';
  return (
    <SegmentedControl
      options={labels}
      value={current}
      onChange={(label) => setPreference(APPEARANCE[label])}
      accessibilityLabel="Appearance"
    />
  );
}

function CoverageRow({ coverage }: { coverage: MetricCoverage }) {
  const colors = useColors();
  const color = useMetricColor(coverage.metric);
  const percent = Math.round(coverage.fractionPresent * 100);
  return (
    <View style={styles.coverageRow}>
      <Text style={styles.coverageLabel}>{coverage.label}</Text>
      <View
        style={[styles.track, { backgroundColor: colors.track }]}
        accessible
        accessibilityLabel={`${coverage.label}: ${percent}% of days`}
      >
        <View style={[styles.fill, { width: `${percent}%`, backgroundColor: color }]} />
      </View>
      <Text variant="caption" color="muted" style={styles.percent}>
        {percent}%
      </Text>
    </View>
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
      <View style={[styles.icon, { backgroundColor: colors.surfaceRaised }]}>
        <Ionicons name={icon} size={18} color={colors.muted} />
      </View>
      <View style={{ flex: 1 }}>
        <Text variant="bodyStrong" color="muted">
          {title}
        </Text>
        <Text variant="caption" color="faint">
          {detail}
        </Text>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  accountRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  accountActions: { flexDirection: 'row', marginLeft: -spacing.lg },
  sourceRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  icon: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  coverageRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: 4 },
  coverageLabel: { width: 128 },
  track: { flex: 1, height: 6, borderRadius: radius.pill, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: radius.pill },
  percent: { width: 40, textAlign: 'right', fontVariant: ['tabular-nums'] },
  days: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  day: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill },
  disabled: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  privacy: { textAlign: 'center', marginTop: spacing.sm },
});
