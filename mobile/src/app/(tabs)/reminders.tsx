import { Ionicons } from '@expo/vector-icons';
import { Link } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Switch, Text, View } from 'react-native';

import {
  useNotificationSettings,
  useReminders,
  useReport,
  useSetReminderStatus,
  useUpdateNotificationSettings,
} from '@/api/hooks';
import { usingMock } from '@/api';
import type { NotificationSettings, Reminder } from '@/api/types';
import { QueryState, Screen } from '@/components/Screen';
import { Card, Chip, SectionTitle } from '@/components/ui';
import { radius, spacing, useColors } from '@/theme';

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
    <Screen refreshing={reminders.isRefetching} onRefresh={reminders.refetch}>
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
                  <Ionicons name="information-circle-outline" size={16} color={colors.accent} />
                  <Text style={[styles.noticeText, { color: colors.accent }]}>
                    Preview: reminders are saved, but notifications are not sent yet.
                  </Text>
                </View>
              )}

              <SectionTitle>Suggested</SectionTitle>
              {proposed.length === 0 ? (
                <Text style={{ color: colors.muted }}>No new suggestions.</Text>
              ) : (
                <>
                  <Text style={[styles.hint, { color: colors.muted }]}>
                    Based on patterns in your data. Nothing is scheduled until you approve it.
                  </Text>
                  {proposed.map((r) => (
                    <ProposalCard key={r.id} reminder={r} />
                  ))}
                </>
              )}

              <SectionTitle>Your reminders</SectionTitle>
              {current.length === 0 ? (
                <Text style={{ color: colors.muted }}>No reminders yet.</Text>
              ) : (
                current.map((r) => <ActiveRow key={r.id} reminder={r} />)
              )}

              {declined.length > 0 && (
                <>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => setShowDeclined((v) => !v)}
                    style={styles.toggle}
                  >
                    <Text style={{ color: colors.accent, fontWeight: '600' }}>
                      {showDeclined ? 'Hide' : 'Show'} declined ({declined.length})
                    </Text>
                    <Ionicons
                      name={showDeclined ? 'chevron-up' : 'chevron-down'}
                      size={14}
                      color={colors.accent}
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
    set: (status: Reminder['status']) => mutation.mutate({ id: reminder.id, status }),
  };
}

function ProposalCard({ reminder }: { reminder: Reminder }) {
  const colors = useColors();
  const report = useReport();
  const status = useStatus(reminder);
  const finding = report.data?.findings.find((f) => f.id === reminder.findingId);

  return (
    <Card>
      <View style={styles.titleRow}>
        <Ionicons name="alarm-outline" size={18} color={colors.accent} />
        <Text style={[styles.title, { color: colors.text }]}>{reminder.title}</Text>
      </View>
      <Text style={{ color: colors.text }}>{reminder.schedule}</Text>
      <Text style={[styles.hint, { color: colors.muted }]}>
        “{reminder.message}”
      </Text>
      <Text style={[styles.reason, { color: colors.muted }]}>Why: {reminder.reason}</Text>
      {finding && (
        <Link href={`/finding/${finding.id}`} style={[styles.link, { color: colors.accent }]}>
          See the finding: {finding.title}
        </Link>
      )}
      {status.error && (
        <Text style={{ color: colors.down }}>Could not save. Please try again.</Text>
      )}
      <View style={styles.actions}>
        <ActionButton label="Not now" onPress={() => status.set('declined')} disabled={status.pending} />
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

function ActiveRow({ reminder }: { reminder: Reminder }) {
  const colors = useColors();
  const status = useStatus(reminder);
  const on = reminder.status === 'active';

  return (
    <Card style={styles.rowCard}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[styles.title, { color: on ? colors.text : colors.muted }]}>{reminder.title}</Text>
        <Text style={{ color: colors.muted, fontSize: 13 }}>
          {on ? reminder.schedule : 'Muted'}
        </Text>
      </View>
      <Switch
        accessibilityLabel={`${reminder.title} ${on ? 'on' : 'muted'}`}
        value={on}
        disabled={status.pending}
        onValueChange={(value) => status.set(value ? 'active' : 'muted')}
        trackColor={{ true: colors.accent, false: colors.border }}
        thumbColor="#FFFFFF"
      />
    </Card>
  );
}

function DeclinedRow({ reminder }: { reminder: Reminder }) {
  const colors = useColors();
  const status = useStatus(reminder);
  return (
    <Card style={styles.rowCard}>
      <Text style={[styles.title, { flex: 1, color: colors.muted }]}>{reminder.title}</Text>
      <ActionButton label="Restore" onPress={() => status.set('proposed')} disabled={status.pending} />
    </Card>
  );
}

function SettingsCard() {
  const colors = useColors();
  const settings = useNotificationSettings();
  const update = useUpdateNotificationSettings();

  return (
    <Card>
      <QueryState query={settings}>
        {() => {
          const current = update.isPending ? update.variables! : settings.data!;
          const save = (next: Partial<NotificationSettings>) => update.mutate({ ...current, ...next });
          return (
            <>
              <Text style={[styles.settingLabel, { color: colors.text }]}>Quiet hours</Text>
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
              <Text style={[styles.settingLabel, { color: colors.text }]}>At most per day</Text>
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
                <Text style={{ color: colors.down }}>Could not save. Please try again.</Text>
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
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.action,
        primary
          ? { backgroundColor: colors.accent }
          : { borderColor: colors.border, borderWidth: 1 },
        { opacity: pressed || disabled ? 0.6 : 1 },
      ]}
    >
      <Text style={{ color: primary ? colors.onAccent : colors.text, fontWeight: '600' }}>{label}</Text>
    </Pressable>
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
  noticeText: { flex: 1, fontSize: 13 },
  hint: { fontSize: 13, lineHeight: 18 },
  reason: { fontSize: 13, lineHeight: 18, fontStyle: 'italic' },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  title: { fontSize: 16, fontWeight: '600' },
  link: { fontSize: 13, fontWeight: '600' },
  actions: { flexDirection: 'row', gap: spacing.sm, justifyContent: 'flex-end', marginTop: spacing.xs },
  action: { paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.md },
  rowCard: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  toggle: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: spacing.xs },
  settingLabel: { fontSize: 14, fontWeight: '600' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
});
