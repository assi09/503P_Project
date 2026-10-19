import { Ionicons } from '@expo/vector-icons';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native';

import type { Direction } from '@/api/types';
import { radius, spacing, useColors } from '@/theme';

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  const colors = useColors();
  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }, style]}>
      {children}
    </View>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  const colors = useColors();
  return <Text style={[styles.section, { color: colors.muted }]}>{children}</Text>;
}

const ARROWS = { up: 'arrow-up', down: 'arrow-down', none: 'remove' } as const;

/** Direction of a change. Deliberately neutral in color: the app does not judge changes as good or bad. */
export function ChangeBadge({ direction, label }: { direction: Direction; label: string }) {
  const colors = useColors();
  return (
    <View style={[styles.badge, { backgroundColor: colors.accentSoft }]}>
      <Ionicons name={ARROWS[direction]} size={12} color={colors.accent} />
      <Text style={[styles.badgeText, { color: colors.accent }]}>{label}</Text>
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
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.chip,
        {
          borderColor: selected ? colors.accent : colors.border,
          backgroundColor: selected ? colors.accentSoft : colors.surface,
          opacity: pressed || disabled ? 0.6 : 1,
        },
      ]}
    >
      <Text style={{ color: selected ? colors.accent : colors.text, fontSize: 14 }}>{label}</Text>
    </Pressable>
  );
}

export function Button({ label, icon, onPress }: { label: string; icon?: keyof typeof Ionicons.glyphMap; onPress: () => void }) {
  const colors = useColors();
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [styles.button, { backgroundColor: colors.accent, opacity: pressed ? 0.8 : 1 }]}
    >
      {icon && <Ionicons name={icon} size={18} color="#FFFFFF" />}
      <Text style={styles.buttonText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.lg, borderWidth: StyleSheet.hairlineWidth, padding: spacing.lg, gap: spacing.sm },
  section: { fontSize: 13, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: spacing.sm },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 2, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 },
  badgeText: { fontSize: 13, fontWeight: '600', fontVariant: ['tabular-nums'] },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1 },
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: 14,
    borderRadius: radius.md,
  },
  buttonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '600' },
});
