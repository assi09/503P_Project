import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Switch, View } from 'react-native';

import { usingMock } from '@/api';
import {
  useNotificationSettings,
  useReminders,
  useReport,
  useSetReminderStatus,
  useUpdateNotificationSettings,
} from '@/api/hooks';
import type { NotificationSettings, Reminder } from '@/api/types';
import { PressableScale } from '@/components/PressableScale';
import { QueryState, Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { Card, Chip, SectionTitle } from '@/components/ui';
import { select, success } from '@/lib/haptics';
import { radius, spacing, useColors, useMetricColor } from '@/theme';

const QUIET_HOURS: { label: string; value: NotificationSettings['quietHours'] }[] = [
  { label: '22:00 – 07:00', value: { start: '22:00', end: '07:00' } },
  { label: '23:00 – 08:00', value: { start: '23:00', end: '08:00' } },
  { label: 'Off', value: null },
];
const MAX_PER_DAY = [1, 2, 3];

export default function RemindersScreen() {
  const colors = useColors();
  const reminders = useReminders();
  const [showDeclined, setShowDeclined] = useState(false);

  return (
    <Screen title="Reminders" refreshing={reminders.isRefetching} onRefresh={reminders.refetch}>
      <QueryState query={reminders}>
        {() => {
          const all = reminders.data!;
          const proposed = all.filter((r) => r.status === 'proposed');
          const current = all.filter((r) => r.status === 'active' || r.status === 'muted');
          const declined = all.filter((r) => r.status === 'declined');
          return (
            <>
              {usingMock && (
                <View style={[styles.notice, { backgroundColor: colors.accentSoft }]}>
                  <Ionicons name="information-circle" size={16} color={colors.accent} />
                  <Text variant="caption" color="accent" style={{ flex: 1 }}>
                    Preview: reminders are saved, but notifications are not sent yet.
                  </Text>
                </View>
              )}

              <SectionTitle>Suggested</SectionTitle>
              {proposed.length === 0 ? (
                <Text color="muted">No new suggestions.</Text>
              ) : (
                <>
                  <Text variant="caption" color="muted">
                    Based on patterns in your data. Nothing is scheduled until you approve it.
                  </Text>
                  {proposed.map((r) => (
                    <ProposalCard key={r.id} reminder={r} />
                  ))}
                </>
              )}

              <SectionTitle>Your reminders</SectionTitle>
              {current.length === 0 ? (
                <Text color="muted">No reminders yet.</Text>
              ) : (
                <Card style={{ paddingVertical: spacing.xs }}>
                  {current.map((r, i) => (
                    <ActiveRow key={r.id} reminder={r} divider={i > 0} />
                  ))}
                </Card>
              )}

              {declined.length > 0 && (
                <>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => {
                      select();
                      setShowDeclined((v) => !v);
                    }}
                    style={styles.toggle}
                    hitSlop={8}
                  >
                    <Text variant="caption" color="muted">
                      {showDeclined ? 'Hide' : 'Show'} declined ({declined.length})
                    </Text>
                    <Ionicons
                      name={showDeclined ? 'chevron-up' : 'chevron-down'}
                      size={14}
                      color={colors.muted}
                    />
                  </Pressable>
                  {showDeclined && declined.map((r) => <DeclinedRow key={r.id} reminder={r} />)}
                </>
              )}

              <SectionTitle>Notifications</SectionTitle>
              <SettingsCard />
            </>
          );
        }}
      </QueryState>
    </Screen>
  );
}

function useStatus(reminder: Reminder) {
  const mutation = useSetReminderStatus();
  const pending = mutation.isPending && mutation.variables?.id === reminder.id;
  return {
    pending,
    error: mutation.error,
    set: (status: Reminder['status']) =>
      mutation.mutate(
        { id: reminder.id, status },
        { onSuccess: () => (status === 'active' ? success() : select()) },
      ),
  };
}

function ProposalCard({ reminder }: { reminder: Reminder }) {
  const report = useReport();
  const status = useStatus(reminder);
  const finding = report.data?.findings.find((f) => f.id === reminder.findingId);
  const color = useMetricColor(finding?.metric ?? 'sleep_minutes');

  return (
    <Card glow={color}>
      <View style={styles.titleRow}>
        <View style={[styles.icon, { backgroundColor: `${color}22` }]}>
          <Ionicons name="alarm" size={16} color={color} />
        </View>
        <View style={{ flex: 1 }}>
          <Text variant="headline">{reminder.title}</Text>
          <Text variant="caption" color="muted">
            {reminder.schedule}
          </Text>
        </View>
      </View>
      <View style={[styles.quote, { borderLeftColor: color }]}>
        <Text color="muted">“{reminder.message}”</Text>
      </View>
      <Text variant="caption" color="muted">
        Why: {reminder.reason}
      </Text>
      {finding && (
        <Pressable
          accessibilityRole="link"
          onPress={() => router.push(`/finding/${finding.id}`)}
          hitSlop={6}
        >
          <Text variant="caption" color={color}>
            See the finding: {finding.title} ›
          </Text>
        </Pressable>
      )}
      {status.error && (
        <Text variant="caption" color="danger">
          Could not save. Please try again.
        </Text>
      )}
      <View style={styles.actions}>
        <ActionButton
          label="Not now"
          onPress={() => status.set('declined')}
          disabled={status.pending}
        />
        <ActionButton
          label="Approve"
          primary
          onPress={() => status.set('active')}
          disabled={status.pending}
        />
      </View>
    </Card>
  );
}

function ActiveRow({ reminder, divider }: { reminder: Reminder; divider: boolean }) {
  const colors = useColors();
  const status = useStatus(reminder);
  const on = reminder.status === 'active';

  return (
    <View
      style={[
        styles.row,
        divider && { borderTopColor: colors.border, borderTopWidth: StyleSheet.hairlineWidth },
      ]}
    >
      <View style={{ flex: 1, gap: 2 }}>
        <Text variant="bodyStrong" color={on ? 'text' : 'muted'}>
          {reminder.title}
        </Text>
        <Text variant="caption" color="muted">
          {on ? reminder.schedule : 'Muted'}
        </Text>
      </View>
      <Switch
        accessibilityLabel={`${reminder.title} ${on ? 'on' : 'muted'}`}
        value={on}
        disabled={status.pending}
        onValueChange={(value) => status.set(value ? 'active' : 'muted')}
        trackColor={{ true: colors.accent, false: colors.track }}
        thumbColor="#FFFFFF"
        // react-native-web colors the "on" knob separately.
        {...({ activeThumbColor: '#FFFFFF' } as object)}
      />
    </View>
  );
}

function DeclinedRow({ reminder }: { reminder: Reminder }) {
  const status = useStatus(reminder);
  return (
    <Card style={styles.declined}>
      <Text color="muted" style={{ flex: 1 }}>
        {reminder.title}
      </Text>
      <ActionButton
        label="Restore"
        onPress={() => status.set('proposed')}
        disabled={status.pending}
      />
    </Card>
  );
}

function SettingsCard() {
  const settings = useNotificationSettings();
  const update = useUpdateNotificationSettings();

  return (
    <Card>
      <QueryState query={settings}>
        {() => {
          const current = update.isPending ? update.variables! : settings.data!;
          const save = (next: Partial<NotificationSettings>) =>
            update.mutate({ ...current, ...next });
          return (
            <>
              <Text variant="bodyStrong">Quiet hours</Text>
              <View style={styles.chips}>
                {QUIET_HOURS.map(({ label, value }) => (
                  <Chip
                    key={label}
                    label={label}
                    selected={JSON.stringify(value) === JSON.stringify(current.quietHours)}
                    onPress={() => save({ quietHours: value })}
                  />
                ))}
              </View>
              <Text variant="bodyStrong" style={{ marginTop: spacing.sm }}>
                At most per day
              </Text>
              <View style={styles.chips}>
                {MAX_PER_DAY.map((n) => (
                  <Chip
                    key={n}
                    label={String(n)}
                    selected={current.maxPerDay === n}
                    onPress={() => save({ maxPerDay: n })}
                  />
                ))}
              </View>
              {update.error && (
                <Text variant="caption" color="danger">
                  Could not save. Please try again.
                </Text>
              )}
            </>
          );
        }}
      </QueryState>
    </Card>
  );
}

function ActionButton({
  label,
  onPress,
  primary = false,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  primary?: boolean;
  disabled?: boolean;
}) {
  const colors = useColors();
  return (
    <PressableScale
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      haptic={false}
      style={[
        styles.action,
        primary
          ? { backgroundColor: colors.text }
          : { backgroundColor: colors.surfaceRaised, borderColor: colors.border, borderWidth: 1 },
      ]}
    >
      <Text variant="bodyStrong" color={primary ? 'background' : 'text'}>
        {label}
      </Text>
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  notice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
  },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  icon: {
    width: 34,
    height: 34,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  quote: { borderLeftWidth: 2, paddingLeft: spacing.md, marginVertical: spacing.xs },
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
    justifyContent: 'flex-end',
    marginTop: spacing.sm,
  },
  action: { paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md },
  declined: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  toggle: { flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
});
