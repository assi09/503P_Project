import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Linking, TextInput, View } from 'react-native';

import { api, usingMock } from '@/api';
import type { HealthAction } from '@/api/types';
import { Text } from '@/components/Text';
import { Button, Card } from '@/components/ui';
import { editLog } from '@/lib/actionLog';
import { radius, spacing, useColors } from '@/theme';

const FOOD_FIELDS = [
  ['foodName', 'Food'], ['consumedAt', 'When (date, time and timezone)'], ['mealType', 'Meal type'],
  ['energyKcal', 'Energy (kcal)'], ['proteinG', 'Protein (g)'],
  ['carbohydrateG', 'Carbohydrates (g)'], ['fatG', 'Fat (g)'],
];
const WORKOUT_FIELDS = [
  ['exerciseType', 'Workout type'], ['startTime', 'Start (date, time and timezone)'],
  ['endTime', 'End (date, time and timezone)'], ['activeSeconds', 'Active duration (seconds)'],
  ['distanceKm', 'Distance (km)'],
];
export const LOG_STATUS_LABELS: Record<HealthAction['status'], string> = {
  draft: 'Review before logging', executing: 'Waiting for Google confirmation',
  succeeded: 'Logged', failed: 'Not logged — review the draft', unknown: 'Outcome not confirmed',
  cancelled: 'Draft cancelled', undoing: 'Waiting for deletion confirmation', undone: 'Entry removed',
};

type Edit = { version: number; fields: Record<string, string> };

/** Only these buttons can confirm a reviewed version; model text cannot execute it. */
export function LogDraftCard({ id }: { id: string }) {
  const colors = useColors();
  const client = useQueryClient();
  const key = ['health-action', id];
  const query = useQuery({ queryKey: key, queryFn: () => api.getAction(id) });
  const [editing, setEditing] = useState<Edit | null>(null);
  const [undoReview, setUndoReview] = useState(false);
  const [formError, setFormError] = useState<string>();
  const action = useMutation({
    mutationFn: (run: () => Promise<HealthAction>) => run(),
    retry: false,
    onSuccess: (saved) => {
      client.setQueryData(key, saved);
      client.invalidateQueries({ queryKey: ['health-actions'] });
      setEditing(null);
      setUndoReview(false);
      setFormError(undefined);
    },
    // Refresh after a timeout or stale version; never repeat a write automatically.
    onError: () => { client.invalidateQueries({ queryKey: key }); },
  });
  const connection = useMutation({
    mutationFn: async () => {
      const result = await api.connectGoogle(query.data?.log.kind === 'food' ? 'food_logging' : 'workout_logging');
      if (result.url) await Linking.openURL(result.url);
    },
    retry: false,
  });
  const row = query.data;
  if (!row) return (
    <Card>
      <Text variant="caption">{query.isError ? 'Could not load this logging draft.' : 'Loading logging draft…'}</Text>
      {query.isError && <Button label="Reload draft" variant="secondary" onPress={() => { query.refetch(); }} />}
    </Card>
  );
  const fields = row.log.kind === 'food' ? FOOD_FIELDS : WORKOUT_FIELDS;
  const values = row.log as unknown as Record<string, unknown>;
  const editable = row.status === 'draft' || row.status === 'failed';
  const busy = action.isPending;

  function startEdit() {
    action.reset();
    setFormError(undefined);
    const inputs = Object.fromEntries(fields.map(([name]) => [name, String(values[name] ?? '')]));
    setEditing({ version: row!.version, fields: inputs });
  }
  function save() {
    if (!editing) return;
    try {
      const log = editLog(row!.log, editing.fields);
      action.mutate(() => api.reviseAction(id, editing.version, log));
    } catch (error) { setFormError((error as Error).message); }
  }

  return (
    <Card style={{ gap: spacing.sm, marginTop: spacing.sm }}>
      <Text variant="label">{row.log.kind === 'food' ? 'Food log' : 'Workout log'}{usingMock ? ' · demo' : ''}</Text>
      <Text variant="caption" color="muted">{LOG_STATUS_LABELS[row.status]} · version {row.version}</Text>
      {fields.map(([name, label]) => (
        <View key={name} style={{ gap: 3 }}>
          <Text variant="caption" color="muted">{label}</Text>
          {editing ? (
            <TextInput accessibilityLabel={label} value={editing.fields[name]}
              onChangeText={(text) => setEditing({ ...editing, fields: { ...editing.fields, [name]: text } })}
              editable={!busy} autoCapitalize="none"
              style={{ color: colors.text, backgroundColor: colors.surfaceRaised,
                borderColor: colors.border, borderWidth: 1, borderRadius: radius.sm, padding: spacing.sm }}
            />
          ) : <Text>{String(values[name] ?? 'Not supplied')}</Text>}
        </View>
      ))}
      <Text variant="caption" color="muted">Supplied values, not independently measured. Missing values stay unknown.</Text>
      {row.status === 'draft' && <Text variant="caption">Confirming sends this version to Google Health.{usingMock ? ' This demo only simulates the action.' : ''}</Text>}
      {row.error && <Text variant="caption" color="warning">{row.error}</Text>}
      {(action.error as { code?: string } | null)?.code === 'write_scope_needed' &&
        <Button label="Allow Google logging" disabled={connection.isPending}
          onPress={() => connection.mutate()} />}
      {connection.error && <Text variant="caption" color="danger">{connection.error.message}</Text>}
      {(formError || action.error) && <Text variant="caption" color="danger">{formError || action.error?.message}</Text>}
      {['executing', 'undoing', 'unknown'].includes(row.status) && <Text variant="caption">The result needs checking. Do not create another copy.</Text>}
      {editing ? (
        <>
          <Button label={busy ? 'Saving…' : 'Save draft changes'} disabled={busy} onPress={save} />
          <Button label="Discard changes" variant="secondary" disabled={busy} onPress={() => setEditing(null)} />
        </>
      ) : editable ? (
        <>
          {row.status === 'draft' && <Button label={busy ? 'Sending…' : 'Confirm and log'} disabled={busy} onPress={() => action.mutate(() => api.confirmAction(id, row.version))} />}
          <Button label="Edit draft" variant="secondary" disabled={busy} onPress={startEdit} />
          <Button label="Cancel draft" variant="secondary" disabled={busy} onPress={() => action.mutate(() => api.cancelAction(id, row.version))} />
        </>
      ) : row.status === 'succeeded' ? (
        undoReview ? <>
          <Text>Remove this entry from Google Health?</Text>
          <Button label="Confirm removal" disabled={busy} onPress={() => action.mutate(() => api.undoAction(id, row.version))} />
          <Button label="Keep entry" variant="secondary" disabled={busy} onPress={() => setUndoReview(false)} />
        </> : <Button label="Undo this log" variant="secondary" disabled={busy} onPress={() => setUndoReview(true)} />
      ) : null}
      <Button label="Refresh status" variant="secondary" disabled={busy} onPress={() => { query.refetch(); }} />
    </Card>
  );
}
