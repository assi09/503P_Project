import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Switch, TextInput, View, type TextInputProps } from 'react-native';

import { useChangeReminder, useCreateReminder, useDeleteReminder, useReminders } from '@/api/hooks';
import type { ISODate, Reminder, ReminderChannel, ReminderSchedule } from '@/api/types';
import { Row, Section } from '@/components/list';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { Button, Chip } from '@/components/ui';
import { success } from '@/lib/haptics';
import { describeSchedule, normalizeTime, WEEKDAYS } from '@/lib/reminders';
import { fonts, radius, spacing, useColors } from '@/theme';

type Repeat = 'once' | 'daily' | 'weekdays' | 'weekends' | 'custom';
const REPEATS: { value: Repeat; label: string }[] = [
  { value: 'once', label: 'Once' },
  { value: 'daily', label: 'Every day' },
  { value: 'weekdays', label: 'Weekdays' },
  { value: 'weekends', label: 'Weekends' },
  { value: 'custom', label: 'Choose days' },
];
const DAYS: Record<'daily' | 'weekdays' | 'weekends', number[]> = {
  daily: [0, 1, 2, 3, 4, 5, 6],
  weekdays: [0, 1, 2, 3, 4],
  weekends: [5, 6],
};

function isoDay(offset: number): ISODate {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

function repeatOf(schedule: ReminderSchedule): Repeat {
  if (schedule.kind === 'once') return 'once';
  const days = [...schedule.weekdays].sort((a, b) => a - b).join();
  const named = (Object.keys(DAYS) as (keyof typeof DAYS)[]).find((k) => DAYS[k].join() === days);
  return named ?? 'custom';
}

/** A new reminder (`/reminder/new`), or one of yours to change or delete. */
export default function ReminderScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const reminders = useReminders();
  const existing = reminders.data?.find((r) => r.id === id);
  if (id !== 'new' && !existing) {
    return (
      <Screen>
        <Stack.Screen options={{ title: 'Reminder' }} />
        <Text color="muted">
          {reminders.isLoading ? 'Loading…' : 'This reminder is not there anymore.'}
        </Text>
      </Screen>
    );
  }
  return <ReminderForm key={existing?.version ?? 'new'} existing={existing} />;
}

function ReminderForm({ existing }: { existing?: Reminder }) {
  const colors = useColors();
  const create = useCreateReminder();
  const change = useChangeReminder();
  const remove = useDeleteReminder();
  const start: ReminderSchedule = existing?.schedule ?? {
    kind: 'weekly',
    time: '22:30',
    weekdays: DAYS.weekdays,
  };

  const [title, setTitle] = useState(existing?.title ?? '');
  const [message, setMessage] = useState(existing?.message ?? '');
  const [repeat, setRepeat] = useState<Repeat>(repeatOf(start));
  const [weekdays, setWeekdays] = useState<number[]>(
    start.kind === 'weekly' ? start.weekdays : DAYS.weekdays,
  );
  const [date, setDate] = useState<ISODate>(start.kind === 'once' ? start.date : isoDay(1));
  const [time, setTime] = useState(start.time);
  const [channels, setChannels] = useState<ReminderChannel[]>(
    existing?.channels ?? ['in_app', 'email'],
  );
  const [problem, setProblem] = useState<string | null>(null);

  const busy = create.isPending || change.isPending || remove.isPending;
  const error = problem ?? (create.error ?? change.error ?? remove.error)?.message ?? null;

  function schedule(): ReminderSchedule | null {
    const at = normalizeTime(time);
    if (!at) return null;
    if (repeat === 'once') return { kind: 'once', date, time: at };
    const days = repeat === 'custom' ? weekdays : DAYS[repeat];
    return days.length ? { kind: 'weekly', time: at, weekdays: days } : null;
  }

  function save() {
    const planned = schedule();
    if (!title.trim()) return setProblem('Give the reminder a title.');
    if (!planned) return setProblem('Choose a time like 22:30, and at least one day.');
    if (channels.length === 0) return setProblem('Choose the app, email, or both.');
    setProblem(null);
    const done = () => {
      success();
      router.back();
    };
    const fields = { title: title.trim(), message: message.trim(), schedule: planned, channels };
    if (existing) {
      change.mutate(
        { id: existing.id, change: { version: existing.version, ...fields } },
        { onSuccess: done },
      );
    } else {
      create.mutate(fields, { onSuccess: done });
    }
  }

  const toggle = (channel: ReminderChannel, on: boolean) =>
    setChannels((current) =>
      on ? [...new Set([...current, channel])] : current.filter((c) => c !== channel),
    );
  const inputStyle = [
    styles.input,
    { color: colors.text, backgroundColor: colors.surface, borderColor: colors.border },
  ];
  const field = (label: string, props: TextInputProps) => (
    <View style={styles.field}>
      <Text variant="caption" color="muted">
        {label}
      </Text>
      <TextInput
        accessibilityLabel={label}
        editable={!busy}
        placeholderTextColor={colors.faint}
        style={inputStyle}
        {...props}
      />
    </View>
  );
  const preview = schedule();
  const switchColors = {
    trackColor: { true: colors.accent, false: colors.track },
    thumbColor: '#FFFFFF',
    // react-native-web colors the "on" knob separately.
    ...({ activeThumbColor: '#FFFFFF' } as object),
  };

  return (
    <Screen>
      <Stack.Screen options={{ title: existing ? 'Edit reminder' : 'New reminder' }} />
      {field('Title', {
        value: title,
        onChangeText: setTitle,
        placeholder: 'Wind down',
        maxLength: 80,
      })}
      {field('Message (what you will see)', {
        value: message,
        onChangeText: setMessage,
        placeholder: 'Screens off, lights low.',
        maxLength: 280,
        multiline: true,
      })}

      <Section title="When">
        <View style={styles.block}>
          <View style={styles.chips}>
            {REPEATS.map(({ value, label }) => (
              <Chip
                key={value}
                label={label}
                selected={repeat === value}
                onPress={() => setRepeat(value)}
              />
            ))}
          </View>
          {repeat === 'custom' && (
            <View style={styles.chips}>
              {WEEKDAYS.map((day, index) => (
                <Chip
                  key={day}
                  label={day}
                  selected={weekdays.includes(index)}
                  onPress={() =>
                    setWeekdays((current) =>
                      current.includes(index)
                        ? current.filter((d) => d !== index)
                        : [...current, index].sort((a, b) => a - b),
                    )
                  }
                />
              ))}
            </View>
          )}
          {repeat === 'once' && (
            <View style={styles.chips}>
              <Chip
                label="Today"
                selected={date === isoDay(0)}
                onPress={() => setDate(isoDay(0))}
              />
              <Chip
                label="Tomorrow"
                selected={date === isoDay(1)}
                onPress={() => setDate(isoDay(1))}
              />
              <TextInput
                accessibilityLabel="Date"
                value={date}
                onChangeText={(text) => setDate(text as ISODate)}
                placeholder="2026-11-03"
                placeholderTextColor={colors.faint}
                style={[inputStyle, styles.short]}
              />
            </View>
          )}
          {field('Time (24-hour)', {
            value: time,
            onChangeText: setTime,
            onBlur: () => setTime(normalizeTime(time) ?? time),
            placeholder: '22:30',
            keyboardType: 'numbers-and-punctuation',
            maxLength: 5,
          })}
          <Text variant="caption" color="muted">
            {preview
              ? `${describeSchedule(preview)}, your local time`
              : 'Choose a time like 22:30.'}
          </Text>
        </View>
      </Section>

      <Section title="Send it">
        <Row
          icon="notifications-outline"
          title="In the app"
          accessory={
            <Switch
              accessibilityLabel="In the app"
              value={channels.includes('in_app')}
              onValueChange={(on) => toggle('in_app', on)}
              {...switchColors}
            />
          }
        />
        <Row
          icon="mail-outline"
          title="By email"
          accessory={
            <Switch
              accessibilityLabel="By email"
              value={channels.includes('email')}
              onValueChange={(on) => toggle('email', on)}
              {...switchColors}
            />
          }
        />
      </Section>

      {error && (
        <Text variant="caption" color="danger" style={{ marginTop: spacing.md }}>
          {error}
        </Text>
      )}
      <View style={styles.actions}>
        {existing && (
          <Button
            label="Delete"
            variant="secondary"
            disabled={busy}
            onPress={() => remove.mutate(existing.id, { onSuccess: () => router.back() })}
          />
        )}
        <Button label={existing ? 'Save' : 'Set reminder'} disabled={busy} onPress={save} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  field: { gap: 4, marginTop: spacing.md },
  input: {
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    fontFamily: fonts.regular,
    fontSize: 15,
  },
  short: { minWidth: 130, paddingVertical: 8 },
  block: { gap: spacing.sm, paddingVertical: spacing.sm },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, alignItems: 'center' },
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
    justifyContent: 'flex-end',
    marginTop: spacing.lg,
  },
});
