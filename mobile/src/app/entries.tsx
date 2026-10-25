import { StyleSheet } from 'react-native';

import { LogEntries } from '@/components/LogEntries';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { spacing } from '@/theme';

/** Every food and workout entry, so one stays reachable after its chat message scrolls away. */
export default function Entries() {
  return (
    <Screen>
      <Text color="muted" style={styles.note}>
        Entries the agent prepared from what you told it. Nothing reaches Google Health until you
        log it, and a logged entry can be undone.
      </Text>
      <LogEntries />
    </Screen>
  );
}

const styles = StyleSheet.create({ note: { marginBottom: spacing.sm } });
