import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { useChangeReminder, useReminders } from '@/api/hooks';
import { Text } from '@/components/Text';
import { Button, Card } from '@/components/ui';
import { select, success } from '@/lib/haptics';
import { dueText } from '@/lib/reminders';
import { radius, spacing, useColors } from '@/theme';

/**
 * A reminder the agent prepared in the chat. It is off until the person taps Set (decision 10);
 * the card then shows it as on, and the Reminders tab keeps it from there.
 */
export function ReminderDraftCard({ id }: { id: string }) {
  const colors = useColors();
  const reminders = useReminders();
  const change = useChangeReminder();
  const reminder = reminders.data?.find((r) => r.id === id);

  if (!reminder) {
    return reminders.isLoading ? null : (
      <Text variant="caption" color="muted">
        This reminder was removed.
      </Text>
    );
  }

  const proposed = reminder.status === 'proposed';
  const on = reminder.status === 'active';
  const via =
    reminder.channels.length === 2
      ? 'in the app and by email'
      : reminder.channels[0] === 'email'
        ? 'by email'
        : 'in the app';
  const decide = (status: 'active' | 'declined') =>
    change.mutate(
      { id, change: { version: reminder.version, status } },
      { onSuccess: () => (status === 'active' ? success() : select()) },
    );
  const state = proposed
    ? 'Not on yet'
    : on
      ? `On${reminder.nextDueAt ? ` · next ${dueText(reminder.nextDueAt)}` : ''}`
      : reminder.status === 'paused'
        ? 'Paused'
        : reminder.status === 'declined'
          ? 'Not set'
          : 'Done';

  return (
    <Card style={styles.card}>
      <View style={styles.head}>
        <View style={[styles.icon, { backgroundColor: colors.accentSoft }]}>
          <Ionicons name="alarm-outline" size={16} color={colors.accent} />
        </View>
        <View style={{ flex: 1 }}>
          <Text variant="bodyStrong">{reminder.title}</Text>
          <Text variant="caption" color="muted">
            {reminder.scheduleText} · {via}
          </Text>
        </View>
        <Text variant="caption" color={on ? 'accent' : 'muted'}>
          {state}
        </Text>
      </View>
      {reminder.message ? <Text color="muted">“{reminder.message}”</Text> : null}
      {change.error && (
        <Text variant="caption" color="danger">
          {change.error.message}
        </Text>
      )}
      {proposed ? (
        <View style={styles.actions}>
          <Button
            label="Not now"
            variant="secondary"
            disabled={change.isPending}
            onPress={() => decide('declined')}
          />
          <Button
            label="Edit"
            variant="secondary"
            disabled={change.isPending}
            onPress={() => router.push(`/reminder/${id}`)}
          />
          <Button
            label="Set"
            icon="checkmark"
            disabled={change.isPending}
            onPress={() => decide('active')}
          />
        </View>
      ) : (
        on && (
          <Text variant="caption" color="muted">
            Change or pause it in Reminders.
          </Text>
        )
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { marginTop: spacing.sm },
  head: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  icon: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actions: { flexDirection: 'row', gap: spacing.sm, justifyContent: 'flex-end', marginTop: 4 },
});
