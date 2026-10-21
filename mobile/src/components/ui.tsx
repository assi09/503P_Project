import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import type { ReactNode } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import type { Direction } from '@/api/types';
import { PressableScale } from '@/components/PressableScale';
import { Text } from '@/components/Text';
import { radius, spacing, useColors, useScheme } from '@/theme';

/** A surface for grouped content. `glow` tints the top corner with a color, e.g. the metric's. */
export function Card({
  children,
  style,
  glow,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  glow?: string;
}) {
  const colors = useColors();
  const scheme = useScheme();
  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }, style]}>
      {glow && (
        <LinearGradient
          pointerEvents="none"
          colors={[`${glow}${scheme === 'dark' ? '26' : '14'}`, `${glow}00`]}
          start={{ x: 0, y: 0 }}
          end={{ x: 0.8, y: 0.9 }}
          style={StyleSheet.absoluteFill}
        />
      )}
      {children}
    </View>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <View style={styles.sectionRow}>
      <Text variant="label" color="muted" accessibilityRole="header">
        {children}
      </Text>
      {action}
    </View>
  );
}

const ARROWS = { up: 'arrow-up', down: 'arrow-down', none: 'remove' } as const;

/**
 * Direction and size of a change. Never green/red: the app does not judge changes as good or bad.
 * `color` is usually the metric's color.
 */
export function ChangeBadge({
  direction,
  label,
  color,
}: {
  direction: Direction;
  label: string;
  color?: string;
}) {
  const colors = useColors();
  const tint = color ?? colors.accent;
  return (
    <View style={[styles.badge, { backgroundColor: `${tint}22` }]}>
      <Ionicons name={ARROWS[direction]} size={12} color={tint} />
      <Text variant="caption" color={tint} style={{ fontVariant: ['tabular-nums'] }}>
        {label}
      </Text>
    </View>
  );
}

export function Chip({
  label,
  selected = false,
  onPress,
  disabled = false,
}: {
  label: string;
  selected?: boolean;
  onPress: () => void;
  disabled?: boolean;
}) {
  const colors = useColors();
  return (
    <PressableScale
      accessibilityRole="button"
      accessibilityState={{ selected, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.chip,
        {
          borderColor: selected ? colors.accent : colors.border,
          backgroundColor: selected ? colors.accentSoft : colors.surfaceRaised,
        },
      ]}
    >
      <Text variant="caption" color={selected ? 'accent' : 'text'}>
        {label}
      </Text>
    </PressableScale>
  );
}

export function Button({
  label,
  icon,
  onPress,
}: {
  label: string;
  icon?: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
}) {
  const colors = useColors();
  return (
    <PressableScale
      accessibilityRole="button"
      onPress={onPress}
      style={[styles.button, { backgroundColor: colors.text }]}
    >
      {icon && <Ionicons name={icon} size={18} color={colors.background} />}
      <Text variant="bodyStrong" color="background">
        {label}
      </Text>
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: spacing.lg,
    gap: spacing.sm,
    overflow: 'hidden',
  },
  sectionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.md,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  chip: { paddingHorizontal: 14, paddingVertical: 9, borderRadius: radius.pill, borderWidth: 1 },
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: 15,
    borderRadius: radius.pill,
  },
});
