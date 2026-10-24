import { useQuery } from '@tanstack/react-query';
import { StyleSheet, View } from 'react-native';

import { api } from '@/api';
import { LogDraftCard } from '@/components/LogDraftCard';
import { Text } from '@/components/Text';
import { Card } from '@/components/ui';
import { spacing } from '@/theme';

/** Every food and workout entry, so one stays reachable after its chat message scrolls away. */
export function LogEntries() {
  const query = useQuery({ queryKey: ['health-actions'], queryFn: api.getActions });

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
  // One card per entry: tapping it shows its actions in place.
  return (
    <View style={styles.list}>
      {query.data.map((entry) => (
        <LogDraftCard key={entry.id} id={entry.id} initial={entry} collapsible />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.sm },
});
