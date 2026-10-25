import { router, Stack, useLocalSearchParams } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { useWorkouts } from '@/api/hooks';
import type { Workout } from '@/api/types';
import { workoutTime } from '@/components/day';
import { Section, Stat } from '@/components/list';
import { Screen } from '@/components/Screen';
import { Skeleton } from '@/components/Skeleton';
import { Text } from '@/components/Text';
import { Button } from '@/components/ui';
import { fullDate } from '@/lib/day';
import { METRIC_COLORS, radius, spacing, useColors, useScheme } from '@/theme';

const ZONES = [
  { key: 'light', label: 'Light' },
  { key: 'moderate', label: 'Moderate' },
  { key: 'vigorous', label: 'Vigorous' },
  { key: 'peak', label: 'Peak' },
] as const;

/** One workout: the figures the tracker recorded, time in each heart-rate zone, and Ask. */
export default function WorkoutScreen() {
  const { id, date } = useLocalSearchParams<{ id: string; date: string }>();
  const workouts = useWorkouts(date);
  const workout = workouts.data?.workouts.find((w) => w.id === id);

  return (
    <Screen>
      <Stack.Screen options={{ title: workout?.name ?? 'Workout' }} />
      {workouts.isPending ? (
        <View style={{ gap: spacing.md }}>
          <Skeleton height={16} width={200} radius={radius.sm} />
          <Skeleton height={120} radius={radius.md} />
        </View>
      ) : !workout ? (
        <Text color="muted">This workout is no longer available.</Text>
      ) : (
        <WorkoutDetail workout={workout} date={date} />
      )}
    </Screen>
  );
}

function WorkoutDetail({ workout, date }: { workout: Workout; date: string }) {
  const colors = useColors();
  const minutes = Math.round(
    (workout.activeSeconds ?? (Date.parse(workout.end) - Date.parse(workout.start)) / 1000) / 60,
  );
  const figures = [
    { value: String(minutes), unit: 'min', label: 'Active time' },
    workout.caloriesKcal != null && {
      value: String(Math.round(workout.caloriesKcal)),
      unit: 'kcal',
      label: 'Calories',
    },
    workout.averageHeartRate && {
      value: String(workout.averageHeartRate),
      unit: 'bpm',
      label: 'Average heart rate',
    },
    workout.activeZoneMinutes && {
      value: String(workout.activeZoneMinutes),
      unit: 'min',
      label: 'Active Zone Minutes',
    },
    workout.distanceKm && { value: String(workout.distanceKm), unit: 'km', label: 'Distance' },
    workout.steps && {
      value: workout.steps.toLocaleString('en-US'),
      unit: 'steps',
      label: 'Steps',
    },
  ].filter((f): f is { value: string; unit: string; label: string } => !!f);

  return (
    <View style={{ gap: spacing.lg }}>
      <View style={{ gap: 2 }}>
        <Text variant="label" color="muted">
          {fullDate(date)}
        </Text>
        <Text variant="title">{workout.name}</Text>
        <Text color="muted">{workoutTime(workout)}</Text>
      </View>

      <View style={[styles.figures, { borderColor: colors.border }]}>
        {figures.map((figure) => (
          <View key={figure.label} style={styles.figure}>
            <Stat value={figure.value} unit={figure.unit} label={figure.label} size="medium" />
          </View>
        ))}
      </View>

      {workout.zoneSeconds && <Zones seconds={workout.zoneSeconds} />}

      <View style={styles.actions}>
        <Button
          label="Ask about this workout"
          icon="sparkles-outline"
          // dismissTo returns to the Ask tab; push would stack a second set of tabs.
          onPress={() =>
            router.dismissTo({
              pathname: '/ask',
              params: {
                q: `How did my ${workout.name.toLowerCase()} on ${fullDate(date)} compare with my usual?`,
              },
            })
          }
        />
      </View>
      <Text variant="caption" color="faint">
        {workout.source ? `Recorded by ${workout.source}. ` : ''}Figures as your tracker recorded
        them. Patterns, not medical advice.
      </Text>
    </View>
  );
}

/** Time in each heart-rate zone as one bar, with the minutes under it. */
function Zones({ seconds }: { seconds: NonNullable<Workout['zoneSeconds']> }) {
  const colors = useColors();
  const scheme = useScheme();
  const heart = METRIC_COLORS.heart[scheme];
  const shades = {
    light: `${heart}40`,
    moderate: `${heart}80`,
    vigorous: `${heart}BF`,
    peak: heart,
  };
  const total = ZONES.reduce((sum, z) => sum + (seconds[z.key] ?? 0), 0);
  if (total <= 0) return null;
  return (
    <Section title="Heart-rate zones">
      <View style={styles.zones}>
        <View style={[styles.bar, { backgroundColor: colors.track }]}>
          {ZONES.map((zone) => (
            <View
              key={zone.key}
              style={{ flex: (seconds[zone.key] ?? 0) / total, backgroundColor: shades[zone.key] }}
            />
          ))}
        </View>
        <View style={styles.legend}>
          {ZONES.map((zone) => (
            <View key={zone.key} style={styles.legendItem}>
              <View style={[styles.dot, { backgroundColor: shades[zone.key] }]} />
              <Text variant="caption" color="muted">
                {zone.label}
              </Text>
              <Text variant="caption" style={{ fontVariant: ['tabular-nums'] }}>
                {Math.round((seconds[zone.key] ?? 0) / 60)} min
              </Text>
            </View>
          ))}
        </View>
      </View>
    </Section>
  );
}

const styles = StyleSheet.create({
  figures: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    rowGap: spacing.lg,
    paddingVertical: spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  figure: { minWidth: 140, flexBasis: '33%', flexGrow: 1 },
  zones: { gap: spacing.sm, paddingVertical: spacing.md },
  bar: { height: 10, borderRadius: radius.pill, overflow: 'hidden', flexDirection: 'row' },
  legend: { flexDirection: 'row', flexWrap: 'wrap', columnGap: spacing.lg, rowGap: 4 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  actions: { flexDirection: 'row' },
});
