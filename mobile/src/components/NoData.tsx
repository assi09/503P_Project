import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { useGoogleStatus } from '@/api/hooks';
import { GoogleHealthCard } from '@/components/GoogleHealthCard';
import { Row, Section } from '@/components/list';
import { Text } from '@/components/Text';
import { useSession } from '@/lib/session';
import { spacing, useColors } from '@/theme';

/**
 * What a screen that needs Fitbit data shows before there is any: what it will show, connecting
 * in place, and for a supervisor the way to their team, which needs no Fitbit (docs/teams.md).
 */
export function NoData({ shows }: { shows: string }) {
  const colors = useColors();
  const { account } = useSession();
  const google = useGoogleStatus().data;
  const syncing = google?.status === 'active';
  return (
    <View style={styles.page}>
      <View style={styles.intro}>
        <View style={[styles.icon, { backgroundColor: colors.accentSoft }]}>
          <Ionicons name={syncing ? 'sync' : 'watch-outline'} size={24} color={colors.accent} />
        </View>
        <Text variant="title">{syncing ? 'Your data is on its way' : 'Connect your Fitbit'}</Text>
        <Text color="muted">
          {syncing
            ? `The first sync reads your whole history, newest days first. ${shows} once it is done.`
            : `${shows} from your own Fitbit data. Connect it through your Google account; nothing else is needed.`}
        </Text>
      </View>
      <GoogleHealthCard compact />
      {account?.role === 'supervisor' ? (
        <Section footer="Your team's weekly report needs no Fitbit of your own.">
          <Row
            icon="people-outline"
            title="Open your team"
            onPress={() => router.navigate('/team')}
          />
        </Section>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  page: { gap: spacing.lg },
  intro: { gap: spacing.sm, paddingTop: spacing.md },
  icon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xs,
  },
});
