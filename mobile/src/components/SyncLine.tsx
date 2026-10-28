import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { useGoogleStatus } from '@/api/hooks';
import { Text } from '@/components/Text';
import { timeAgo } from '@/lib/format';
import { spacing, useColors } from '@/theme';

/**
 * One quiet line about how fresh the data is. Syncing happens by itself (on open, on return and on
 * pull to refresh), so this only reports it; an expired Google sign-in is the one thing to act on.
 */
export function SyncLine() {
  const colors = useColors();
  const google = useGoogleStatus().data;
  if (!google || google.status === 'none') return null;

  if (google.status === 'reconnect_needed') {
    return (
      <Pressable
        accessibilityRole="button"
        onPress={() => router.navigate('/settings')}
        style={[styles.row, styles.expired, { backgroundColor: colors.surfaceRaised }]}
      >
        <Ionicons name="refresh-circle" size={18} color={colors.warning} />
        <Text variant="caption" style={{ flex: 1 }}>
          Google’s sign-in expired, so new days are not coming in. Tap to reconnect.
        </Text>
      </Pressable>
    );
  }

  return (
    <View style={styles.row}>
      {google.syncing ? (
        <>
          <ActivityIndicator size="small" color={colors.muted} />
          <Text variant="caption" color="muted">
            Updating your data…
          </Text>
        </>
      ) : (
        <Text variant="caption" color="faint">
          {google.lastSync ? `Updated ${timeAgo(google.lastSync)}` : 'Not updated yet'}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  expired: { justifyContent: 'flex-start', padding: spacing.sm, borderRadius: 10 },
});
