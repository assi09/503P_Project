import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { type ReactNode, useEffect, useState } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { runOnJS } from 'react-native-reanimated';

import { useDay, useHourlySteps, useReport, useWorkouts } from '@/api/hooks';
import type { DaySummary, Finding, ISODate } from '@/api/types';
import { CheckInSection } from '@/components/checkin';
import {
  DayHeader,
  HourlyBars,
  KeyNumber,
  MetricRow,
  StagesBar,
  WorkoutRow,
} from '@/components/day';
import { QuestionCard } from '@/components/insights';
import { Section } from '@/components/list';
import { Screen } from '@/components/Screen';
import { Skeleton } from '@/components/Skeleton';
import { Text } from '@/components/Text';
import { metricOf, shiftDate, stages, STRAIN_BANDS, wakeHour } from '@/lib/day';
import { formatValue, metricLabel } from '@/lib/format';
import { useWide } from '@/lib/layout';
import { radius, spacing, useColors, useMetricColor } from '@/theme';
import { isHovered } from '@/lib/platform';

// Our own four scores of the day (docs/scores.md): one row on wide screens, two by two on phones.
const KEY_NUMBERS = [
  { metric: 'recovery_score', label: 'Recovery' },
  { metric: 'strain', label: 'Strain' },
  { metric: 'sleep_minutes', label: 'Sleep' },
  { metric: 'stress_score', label: 'Stress' },
];
const ACTIVITY = [
  'steps',
  'active_zone_minutes',
  'distance_km',
  'calories',
  'very_active_minutes',
  'moderately_active_minutes',
];
const HEART = ['resting_hr', 'hrv_ms', 'respiratory_rate', 'skin_temp_variation_c'];

export default function TodayScreen() {
  const [date, setDate] = useState<ISODate | 'latest'>('latest');
  const day = useDay(date);
  const report = useReport();
  const wide = useWide();
  const data = day.data;

  function change(to: ISODate | 'latest', step = 0) {
    if (to === 'latest' || !data) return setDate('latest');
    const next = shiftDate(to, step);
    if (next < data.first) return;
    setDate(next >= data.last ? 'latest' : next);
  }

  // On the web, the arrow keys move between days.
  useEffect(() => {
    if (Platform.OS !== 'web' || !data) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return;
      if (event.key === 'ArrowLeft') change(data.date, -1);
      if (event.key === 'ArrowRight') change(data.date, 1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  // On phones a sideways swipe moves between days; vertical scrolling is left alone.
  const swipe = Gesture.Pan()
    .enabled(Platform.OS !== 'web' && !!data)
    .activeOffsetX([-30, 30])
    .failOffsetY([-12, 12])
    .onEnd((event) => {
      if (Math.abs(event.translationX) > 60 && data) {
        runOnJS(change)(data.date, event.translationX < 0 ? 1 : -1);
      }
    });

  const open = (metric: string) =>
    router.push({ pathname: '/metric/[metric]', params: { metric, date: data?.date ?? '' } });

  return (
    <GestureDetector gesture={swipe}>
      <View style={{ flex: 1 }}>
        <Screen
          wide
          refreshing={day.isRefetching && !day.isPlaceholderData}
          onRefresh={() => {
            day.refetch();
            report.refetch();
          }}
          header={
            data ? (
              <DayHeader
                date={data.date}
                today={data.last}
                first={data.first}
                last={data.last}
                partial={data.partial}
                onChange={change}
              />
            ) : (
              <View style={styles.headerSkeleton}>
                <Skeleton height={14} width={160} radius={radius.sm} />
                <Skeleton height={36} width={140} radius={radius.sm} />
              </View>
            )
          }
        >
          {day.error && !data ? (
            <Section>
              <Pressable onPress={() => day.refetch()} style={styles.error}>
                <Text>Could not load this day.</Text>
                <Text variant="caption" color="muted">
                  {day.error.message} Tap to try again.
                </Text>
              </Pressable>
            </Section>
          ) : !data ? (
            <DaySkeleton wide={wide} />
          ) : (
            <View style={{ opacity: day.isPlaceholderData ? 0.5 : 1, gap: spacing.md }}>
              <DayBody
                day={data}
                wide={wide}
                open={open}
                changes={
                  <Changes
                    findings={report.data?.findings ?? []}
                    questions={report.data?.questions}
                  />
                }
              />
              <Text variant="caption" color="faint" style={styles.footer}>
                Your own Fitbit data compared with your own usual range, the middle half of the four
                weeks before. Patterns, not medical advice.
              </Text>
            </View>
          )}
        </Screen>
      </View>
    </GestureDetector>
  );
}

function DayBody({
  day,
  wide,
  open,
  changes,
}: {
  day: DaySummary;
  wide: boolean;
  open: (metric: string) => void;
  changes: ReactNode; // what the screen found lately; under Sleep on wide screens
}) {
  const colors = useColors();
  const night = stages(day);
  const bedtime = metricOf(day, 'bedtime_hour');
  const wake = wakeHour(bedtime.value, metricOf(day, 'time_in_bed').value);

  const workouts = useWorkouts(day.date);
  const hourly = useHourlySteps(day.date);

  const keyNumber = ({ metric, label }: (typeof KEY_NUMBERS)[number]) => (
    <KeyNumber
      key={metric}
      label={label}
      metric={metricOf(day, metric)}
      partial={day.partial}
      large={wide}
      note={metric === 'strain' && day.strain ? STRAIN_BANDS[day.strain.band] : undefined}
      onPress={() => open(metric)}
    />
  );
  const keys = (
    <View style={[styles.keys, { borderColor: colors.border }]}>
      {wide ? (
        <View style={styles.keyRow}>{KEY_NUMBERS.map(keyNumber)}</View>
      ) : (
        [KEY_NUMBERS.slice(0, 2), KEY_NUMBERS.slice(2)].map((row) => (
          <View key={row[0].metric} style={styles.keyRow}>
            {row.map(keyNumber)}
          </View>
        ))
      )}
    </View>
  );

  const sleep = (
    <Section title="Sleep">
      {night ? <StagesBar stages={night} /> : null}
      <MetricRow
        label="Time asleep"
        metric={metricOf(day, 'sleep_minutes')}
        partial={false}
        onPress={() => open('sleep_minutes')}
      />
      <MetricRow
        label="Bedtime"
        metric={bedtime}
        partial={false}
        onPress={() => open('bedtime_hour')}
      />
      {wake !== null ? (
        <MetricRow
          label="Woke up"
          metric={{ metric: 'wake', value: null, usual: null, recent: [] }}
          partial={false}
          value={formatValue('bedtime_hour', wake)}
          detail="Bedtime plus time in bed"
        />
      ) : null}
      <MetricRow
        label="Sleep efficiency"
        metric={metricOf(day, 'sleep_efficiency')}
        partial={false}
        onPress={() => open('sleep_efficiency')}
      />
    </Section>
  );

  const activity = (
    <Section
      title="Activity"
      footer={
        day.lowWear
          ? 'Your tracker was worn under 10 hours this day, so these totals are low and left out of your usual range.'
          : undefined
      }
    >
      {hourly.data?.steps.some((s) => s !== null) ? (
        <HourlyBars steps={hourly.data.steps} />
      ) : null}
      {ACTIVITY.map((metric) => (
        <MetricRow
          key={metric}
          label={metricLabel(metric)}
          metric={metricOf(day, metric)}
          partial={day.partial}
          onPress={() => open(metric)}
        />
      ))}
    </Section>
  );

  // Without a Google Health connection there is nothing to read workouts from: say nothing.
  const sessions = workouts.data?.available ? (
    <Section title="Workouts">
      {workouts.data.workouts.length ? (
        workouts.data.workouts.map((workout) => (
          <WorkoutRow
            key={workout.id}
            workout={workout}
            onPress={() =>
              router.push({
                pathname: '/workout/[id]',
                params: { id: workout.id, date: day.date },
              })
            }
          />
        ))
      ) : (
        <View style={styles.none}>
          <Text color="muted">
            {day.partial ? 'No workouts yet today.' : 'No workouts this day.'} Tell the Ask tab
            about one and it can log it with what your tracker recorded.
          </Text>
        </View>
      )}
    </Section>
  ) : null;
  const checkIn = <CheckInSection day={day.date} today={day.partial} />;

  const heart = (
    <Section title="Heart and body">
      {HEART.map((metric) => (
        <MetricRow
          key={metric}
          label={metricLabel(metric)}
          metric={metricOf(day, metric)}
          partial={false}
          onPress={() => open(metric)}
        />
      ))}
    </Section>
  );

  if (!wide) {
    return (
      <>
        {keys}
        {checkIn}
        {sleep}
        {activity}
        {sessions}
        {heart}
        {changes}
      </>
    );
  }
  return (
    <>
      {keys}
      <View style={styles.columns}>
        <View style={styles.column}>
          {checkIn}
          {sleep}
          {sessions}
        </View>
        <View style={styles.column}>
          {activity}
          {heart}
          {changes}
        </View>
      </View>
    </>
  );
}

/** What the screen found across the last weeks, as rows that open the finding. */
function Changes({
  findings,
  questions,
}: {
  findings: Finding[];
  questions?: Parameters<typeof QuestionCard>[0]['question'][];
}) {
  const open = (questions ?? []).filter((q) => !q.answer);
  return (
    <>
      {open.map((question) => (
        <QuestionCard key={question.id} question={question} />
      ))}
      <Section
        title="What changed lately"
        footer={
          findings.length
            ? 'The last two weeks against the four before, tested and corrected for many tests.'
            : undefined
        }
      >
        {findings.length === 0 ? (
          <View style={styles.none}>
            <Text color="muted">
              Nothing differed clearly from the weeks before. Ask about any metric in the Ask tab.
            </Text>
          </View>
        ) : (
          findings.map((finding) => <FindingRow key={finding.id} finding={finding} />)
        )}
      </Section>
    </>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  const colors = useColors();
  const color = useMetricColor(finding.metric);
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityHint="Opens the evidence for this finding"
      onPress={() => router.push(`/finding/${finding.id}`)}
      style={(state) => [styles.finding, isHovered(state) && { backgroundColor: colors.track }]}
    >
      <View style={[styles.findingDot, { backgroundColor: color }]} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text>{finding.title}</Text>
        <Text variant="caption" color="muted" numberOfLines={2}>
          {metricLabel(finding.metric)} · {finding.change}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={16} color={colors.faint} />
    </Pressable>
  );
}

function DaySkeleton({ wide }: { wide: boolean }) {
  return (
    <View style={{ gap: spacing.lg }}>
      {(wide ? [4] : [2, 2]).map((count, row) => (
        <View key={row} style={styles.keysSkeleton}>
          {Array.from({ length: count }, (_, i) => (
            <View key={i} style={{ flex: 1, gap: spacing.sm }}>
              <Skeleton height={12} width={70} radius={radius.sm} />
              <Skeleton height={wide ? 44 : 30} radius={radius.sm} />
              <Skeleton height={12} width={90} radius={radius.sm} />
            </View>
          ))}
        </View>
      ))}
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} height={18} radius={radius.sm} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  headerSkeleton: { gap: spacing.sm, marginBottom: spacing.md },
  keys: {
    gap: spacing.md,
    paddingBottom: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  keyRow: { flexDirection: 'row', gap: spacing.lg },
  keysSkeleton: { flexDirection: 'row', gap: spacing.lg },
  columns: { flexDirection: 'row', gap: spacing.xxl, alignItems: 'flex-start' },
  column: { flex: 1, minWidth: 0 },
  none: { paddingVertical: spacing.md },
  finding: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.sm,
    marginHorizontal: -spacing.sm,
    borderRadius: radius.sm,
  },
  findingDot: { width: 8, height: 8, borderRadius: 4 },
  error: { paddingVertical: spacing.md, gap: 2 },
  footer: { textAlign: 'center', marginTop: spacing.lg },
});
