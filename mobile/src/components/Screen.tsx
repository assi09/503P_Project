import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { spacing, useColors } from '@/theme';

export function Screen({ children }: { children: ReactNode }) {
  return (
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      {children}
    </ScrollView>
  );
}

interface QueryLike {
  isPending: boolean;
  error: Error | null;
  refetch: () => unknown;
}

/** Shows a spinner while loading and a retryable message on error; renders children otherwise. */
export function QueryState({ query, children }: { query: QueryLike; children: () => ReactNode }) {
  const colors = useColors();
  if (query.isPending) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }
  if (query.error) {
    return (
      <View style={styles.center}>
        <Text style={[styles.message, { color: colors.text }]}>Could not load this.</Text>
        <Text style={[styles.detail, { color: colors.muted }]}>{query.error.message}</Text>
        <Pressable accessibilityRole="button" onPress={() => query.refetch()}>
          <Text style={[styles.retry, { color: colors.accent }]}>Try again</Text>
        </Pressable>
      </View>
    );
  }
  return <>{children()}</>;
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, gap: spacing.md, maxWidth: 720, width: '100%', alignSelf: 'center' },
  center: { padding: spacing.xl, alignItems: 'center', gap: spacing.sm },
  message: { fontSize: 16, fontWeight: '600' },
  detail: { fontSize: 13, textAlign: 'center' },
  retry: { fontSize: 15, fontWeight: '600', padding: spacing.sm },
});
