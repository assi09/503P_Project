import { BottomTabBarHeightContext } from 'expo-router/js-tabs';
import { useContext, type ReactNode } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { PressableScale } from '@/components/PressableScale';
import { floatingTabBar } from '@/lib/platform';
import { Skeleton } from '@/components/Skeleton';
import { Text } from '@/components/Text';
import { radius, spacing, useColors } from '@/theme';

interface ScreenProps {
  children: ReactNode;
  title?: string; // a large page title; tab screens use it instead of a header bar
  subtitle?: string;
  refreshing?: boolean;
  onRefresh?: () => unknown; // enables pull to refresh
}

export function Screen({ children, title, subtitle, refreshing = false, onRefresh }: ScreenProps) {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  // On iOS the tab bar floats over the content, so leave room for it.
  const barHeight = useContext(BottomTabBarHeightContext) ?? 0;
  const tabBarHeight = floatingTabBar ? barHeight : 0;

  return (
    <ScrollView
      contentContainerStyle={[
        styles.content,
        { paddingTop: title ? insets.top + spacing.md : spacing.lg },
        { paddingBottom: tabBarHeight + spacing.xl },
      ]}
      scrollIndicatorInsets={{ bottom: tabBarHeight }}
      keyboardShouldPersistTaps="handled"
      refreshControl={
        onRefresh && (
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.muted} />
        )
      }
    >
      {title && (
        <View style={styles.header}>
          {subtitle && (
            <Text variant="label" color="muted">
              {subtitle}
            </Text>
          )}
          <Text variant="display" accessibilityRole="header">
            {title}
          </Text>
        </View>
      )}
      {children}
    </ScrollView>
  );
}

interface QueryLike {
  isPending: boolean;
  error: Error | null;
  refetch: () => unknown;
}

/** Shows placeholders while loading and a retryable message on error; renders children otherwise. */
export function QueryState({
  query,
  children,
  loading,
}: {
  query: QueryLike;
  children: () => ReactNode;
  loading?: ReactNode; // placeholder shaped like the content
}) {
  const colors = useColors();
  if (query.isPending) {
    return (
      loading ?? (
        <View style={{ gap: spacing.md }}>
          <Skeleton height={120} radius={radius.lg} />
          <Skeleton height={120} radius={radius.lg} />
        </View>
      )
    );
  }
  if (query.error) {
    return (
      <View style={[styles.error, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text variant="headline">Could not load this</Text>
        <Text variant="caption" color="muted" style={{ textAlign: 'center' }}>
          {query.error.message}
        </Text>
        <PressableScale
          accessibilityRole="button"
          onPress={() => query.refetch()}
          style={[styles.retry, { backgroundColor: colors.accentSoft }]}
        >
          <Text variant="bodyStrong" color="accent">
            Try again
          </Text>
        </PressableScale>
      </View>
    );
  }
  return <>{children()}</>;
}

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: spacing.lg,
    gap: spacing.md,
    maxWidth: 720,
    width: '100%',
    alignSelf: 'center',
  },
  header: { gap: 2, marginBottom: spacing.sm },
  error: {
    padding: spacing.xl,
    alignItems: 'center',
    gap: spacing.sm,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
  },
  retry: {
    marginTop: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: 10,
    borderRadius: radius.pill,
  },
});
