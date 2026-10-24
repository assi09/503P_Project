import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { api } from '@/api';
import { LogDraftCard, logIcon, StatusPill } from '@/components/LogDraftCard';
import { PressableScale } from '@/components/PressableScale';
import { Text } from '@/components/Text';
import { Card } from '@/components/ui';
import { logDetails, logTitle } from '@/lib/actionLog';
import { radius, spacing, useColors } from '@/theme';

/** Every food and workout entry, so one stays reachable after its chat message scrolls away. */
export function LogEntries() {
  const colors = useColors();
  const query = useQuery({ queryKey: ['health-actions'], queryFn: api.getActions });
  const [open, setOpen] = useState<string>();

  if (query.isPending) {
    return (
      <Card>
        <Text color="muted">Loading your entries…</Text>
      </Card>
    );
  }
  if (query.isError) {
    return (
      <Card>
        <Text color="danger">Could not load your entries.</Text>
      </Card>
    );
  }
  if (!query.data.length) {
    return (
      <Card>
        <Text color="muted">
          Nothing logged yet. Tell Patterns what you ate or a workout you did, and it prepares an
          entry for you to check.
        </Text>
      </Card>
    );
  }
  return (
    <View style={styles.list}>
      <Card style={styles.rows}>
        {query.data.map((entry, index) => (
          <PressableScale
            key={entry.id}
            accessibilityRole="button"
            accessibilityState={{ expanded: open === entry.id }}
            onPress={() => setOpen(open === entry.id ? undefined : entry.id)}
            style={[
              styles.row,
              index > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
            ]}
          >
            <View style={[styles.icon, { backgroundColor: colors.accentSoft }]}>
              <Ionicons name={logIcon(entry.log)} size={16} color={colors.accent} />
            </View>
            <View style={styles.text}>
              <Text variant="bodyStrong" numberOfLines={1}>
                {logTitle(entry.log)}
              </Text>
              <Text variant="caption" color="muted" numberOfLines={1}>
                {logDetails(entry.log).join(' · ')}
              </Text>
            </View>
            <StatusPill status={entry.status} />
          </PressableScale>
        ))}
      </Card>
      {open && <LogDraftCard key={open} id={open} />}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.sm },
  rows: { paddingVertical: spacing.xs, gap: 0 },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md },
  icon: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  text: { flex: 1, gap: 2 },
});
