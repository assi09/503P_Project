import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { View } from 'react-native';

import { api } from '@/api';
import { LOG_STATUS_LABELS, LogDraftCard } from '@/components/LogDraftCard';
import { Text } from '@/components/Text';
import { Button, Card } from '@/components/ui';
import { spacing } from '@/theme';

/** Saved entries remain reachable after a lost response or an older chat leaves the history. */
export function LogEntries() {
  const query = useQuery({ queryKey: ['health-actions'], queryFn: api.getActions });
  const [selected, setSelected] = useState<string>();
  if (query.isPending) return <Card><Text color="muted">Loading saved entries…</Text></Card>;
  if (query.isError) return (
    <Card>
      <Text color="danger">Could not load saved logging entries.</Text>
      <Button label="Reload entries" variant="secondary" onPress={() => { query.refetch(); }} />
    </Card>
  );
  if (!query.data.length) return (
    <Card><Text color="muted">No logging entries yet. Ask to log a meal or a workout to prepare a draft.</Text></Card>
  );
  return (
    <View style={{ gap: spacing.sm }}>
      <Card>
        {query.data.map((entry) => (
          <Button key={entry.id} variant="secondary"
            label={`${entry.log.kind === 'food' ? entry.log.foodName : entry.log.exerciseType} · ${LOG_STATUS_LABELS[entry.status]}`}
            onPress={() => setSelected(selected === entry.id ? undefined : entry.id)} />
        ))}
      </Card>
      {selected && <LogDraftCard key={selected} id={selected} />}
    </View>
  );
}
