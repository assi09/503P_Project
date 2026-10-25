import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ConversationList } from '@/components/conversations';
import { column, spacing, useColors } from '@/theme';

/** On phones, the list of chats is its own page; picking one goes back to Ask with it open. */
export default function Chats() {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  // dismissTo returns to the existing Ask tab; push would stack a second set of tabs.
  const open = (c: string) => router.dismissTo({ pathname: '/ask', params: { c } });
  return (
    <View
      style={[
        styles.page,
        { backgroundColor: colors.background, paddingBottom: insets.bottom + spacing.md },
      ]}
    >
      <ConversationList newOpen={false} onSelect={open} onNew={() => open('new')} />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, ...column, paddingHorizontal: spacing.lg, paddingTop: spacing.md },
});
