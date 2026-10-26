import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, Platform, StyleSheet, View } from 'react-native';

import { keys, useGoogleAction, useGoogleStatus } from '@/api/hooks';
import { ApiError } from '@/api/http';
import { api } from '@/api';
import { Text } from '@/components/Text';
import { Button } from '@/components/ui';
import { timeAgo } from '@/lib/format';
import { radius, spacing, useColors } from '@/theme';

// What Google's page answered, passed back in the address as ?google=…
const RETURNED: Record<string, { text: string; good: boolean }> = {
  connected: { text: 'Google Health is connected. Your history is syncing.', good: true },
  cancelled: { text: 'Nothing was connected: access was not given on Google’s page.', good: false },
  expired: { text: 'That sign-in took too long. Try connecting again.', good: false },
  failed: { text: 'Google did not finish the sign-in. Try connecting again.', good: false },
};

const SCOPE_NAMES: Record<string, string> = {
  activity_and_fitness: 'activity',
  health_metrics_and_measurements: 'heart and body',
  sleep: 'sleep',
  nutrition: 'nutrition',
};

function scopeName(scope: string): string {
  const key = scope.replace(/^.*googlehealth\./, '').replace(/\.readonly$/, '');
  return SCOPE_NAMES[key] ?? key;
}

/**
 * Connecting the person's own Google Health account, and keeping it synced. `compact` shows only
 * the button to connect, under a page that already says what connecting does.
 */
export function GoogleHealthCard({ returned, compact }: { returned?: string; compact?: boolean }) {
  const colors = useColors();
  const client = useQueryClient();
  const status = useGoogleStatus();
  const action = useGoogleAction();
  const [opening, setOpening] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);
  const google = status.data;

  // When a sync finishes, every screen showing data reloads it, including those that had none.
  const wasSyncing = useRef(false);
  useEffect(() => {
    if (wasSyncing.current && google && !google.syncing) client.invalidateQueries();
    wasSyncing.current = google?.syncing ?? false;
  }, [google, client]);

  async function connect() {
    setOpening(true);
    setOpenError(null);
    try {
      const { url } = await api.connectGoogle();
      if (!url) {
        // The mock connects without a Google page.
        await client.invalidateQueries({ queryKey: keys.google });
      } else if (Platform.OS === 'web') {
        window.location.assign(url); // Google sends the browser back to Settings
        return;
      } else {
        await Linking.openURL(url);
      }
    } catch (caught) {
      setOpenError(caught instanceof ApiError ? caught.message : 'Could not start connecting.');
    }
    setOpening(false);
  }

  const notice = returned ? RETURNED[returned] : undefined;
  const connected = google?.status === 'active';
  const expired = google?.status === 'reconnect_needed';

  let title = 'Connect Google Health';
  let detail =
    'Read-only access to your Fitbit data through your Google account. Your whole history is synced, then kept up to date.';
  if (connected && google.syncing) {
    title = 'Syncing your data…';
    detail = google.lastSync
      ? `Last synced ${timeAgo(google.lastSync)}.`
      : 'The first sync reads your whole history, newest days first.';
  } else if (connected) {
    title = 'Google Health connected';
    detail = google.lastSync ? `Synced ${timeAgo(google.lastSync)}.` : 'Not synced yet.';
  } else if (expired) {
    title = 'Google sign-in expired';
    detail = 'Google ends the sign-in after 7 days while Patterns is in testing. Connect again.';
  }

  const error = openError ?? action.error?.message ?? google?.lastError ?? null;

  return (
    <View style={styles.block}>
      {notice && (
        <View
          style={[
            styles.notice,
            { backgroundColor: notice.good ? colors.accentSoft : colors.surfaceRaised },
          ]}
        >
          <Text variant="caption">{notice.text}</Text>
        </View>
      )}
      {!compact && (
        <View style={styles.row}>
          {connected && google.syncing ? (
            <ActivityIndicator size="small" color={colors.accent} />
          ) : (
            <Ionicons
              name={connected ? 'checkmark-circle' : 'logo-google'}
              size={20}
              color={connected ? colors.accent : colors.text}
            />
          )}
          <View style={{ flex: 1, gap: 2 }}>
            <Text variant="headline">{title}</Text>
            <Text variant="caption" color="muted">
              {detail}
            </Text>
          </View>
        </View>
      )}

      {connected && google.missingScopes.length > 0 && (
        <Text variant="caption" color="warning">
          Not shared on Google’s page: {google.missingScopes.map(scopeName).join(', ')}. Connect
          again to include them.
        </Text>
      )}
      {error && (
        <Text variant="caption" color="danger">
          {error}
        </Text>
      )}

      <View style={styles.actions}>
        {connected && compact ? null : connected ? (
          <>
            <Button
              label="Sync now"
              icon="sync"
              disabled={google.syncing || action.isPending}
              onPress={() => action.mutate('sync')}
            />
            <Button
              label="Disconnect"
              variant="secondary"
              disabled={action.isPending}
              onPress={() => action.mutate('disconnect')}
            />
          </>
        ) : (
          <Button
            label={
              opening
                ? 'Opening Google…'
                : expired
                  ? 'Connect again'
                  : compact
                    ? 'Connect Google Health'
                    : 'Connect'
            }
            icon="arrow-forward"
            iconAfter
            disabled={opening || status.isPending}
            onPress={connect}
          />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  block: { gap: spacing.sm, paddingVertical: spacing.md },
  notice: { padding: spacing.md, borderRadius: radius.md },
  row: { flexDirection: 'row', gap: spacing.md, alignItems: 'center' },
  actions: { flexDirection: 'row', gap: spacing.xs, marginTop: spacing.xs, flexWrap: 'wrap' },
});
