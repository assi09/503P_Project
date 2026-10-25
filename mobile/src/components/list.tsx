import { Ionicons } from '@expo/vector-icons';
import { Children, Fragment, isValidElement, type ReactNode } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { PressableScale } from '@/components/PressableScale';
import { Text } from '@/components/Text';
import { fonts, spacing, type as typeScale, useColors } from '@/theme';

/**
 * A titled group of rows with hairlines between them and no panel behind: spacing and the title
 * do the grouping. Panels are kept for things a person acts on (drafts, suggestions).
 */
export function Section({
  title,
  action,
  footer,
  children,
  style,
}: {
  title?: string;
  action?: ReactNode; // e.g. a small text button at the right of the title
  footer?: string; // a quiet note under the rows
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const colors = useColors();
  const rows = Children.toArray(children).filter(isValidElement);
  return (
    <View style={[styles.section, style]}>
      {(title || action) && (
        <View style={styles.header}>
          {title && (
            <Text variant="label" color="muted" accessibilityRole="header">
              {title}
            </Text>
          )}
          {action}
        </View>
      )}
      <View style={[styles.rows, { borderColor: colors.border }]}>
        {rows.map((row, index) => (
          <Fragment key={row.key ?? index}>
            {index > 0 && <View style={[styles.divider, { backgroundColor: colors.border }]} />}
            {row}
          </Fragment>
        ))}
      </View>
      {footer && (
        <Text variant="caption" color="faint" style={styles.footer}>
          {footer}
        </Text>
      )}
    </View>
  );
}

/** One line of a section: an optional icon, a title and detail, and a value or chevron. */
export function Row({
  icon,
  iconColor,
  title,
  detail,
  value,
  accessory,
  onPress,
  tone = 'default',
  accessibilityLabel,
}: {
  icon?: keyof typeof Ionicons.glyphMap;
  iconColor?: string;
  title: string;
  detail?: string;
  value?: string;
  accessory?: ReactNode; // anything at the right instead of a value, e.g. a switch
  onPress?: () => void;
  tone?: 'default' | 'danger';
  accessibilityLabel?: string;
}) {
  const colors = useColors();
  const titleColor = tone === 'danger' ? colors.danger : colors.text;
  const content = (
    <>
      {icon && <Ionicons name={icon} size={20} color={iconColor ?? titleColor} />}
      <View style={styles.text}>
        <Text style={{ color: titleColor }}>{title}</Text>
        {detail && (
          <Text variant="caption" color="muted">
            {detail}
          </Text>
        )}
      </View>
      {value && (
        <Text color="muted" style={styles.value}>
          {value}
        </Text>
      )}
      {accessory}
      {onPress && <Ionicons name="chevron-forward" size={16} color={colors.faint} />}
    </>
  );
  if (!onPress) {
    return (
      <View
        style={styles.row}
        accessible={!!accessibilityLabel}
        accessibilityLabel={accessibilityLabel}
      >
        {content}
      </View>
    );
  }
  return (
    <PressableScale
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? title}
      onPress={onPress}
      style={styles.row}
    >
      {content}
    </PressableScale>
  );
}

/** A value read at arm's length: large figures, a small unit, and a quiet label under it. */
export function Stat({
  value,
  unit,
  label,
  color,
  size = 'large',
}: {
  value: string;
  unit?: string;
  label: string;
  color?: string; // usually the metric's color
  size?: 'large' | 'medium';
}) {
  const figures = size === 'large' ? typeScale.hero : typeScale.number;
  return (
    <View style={styles.stat} accessible accessibilityLabel={`${label}: ${value} ${unit ?? ''}`}>
      <View style={styles.statValue}>
        <Text style={[figures, color ? { color } : null]}>{value}</Text>
        {unit && (
          <Text variant="caption" color="muted" style={styles.unit}>
            {unit}
          </Text>
        )}
      </View>
      <Text variant="caption" color="muted">
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.sm, marginTop: spacing.lg },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rows: { borderTopWidth: StyleSheet.hairlineWidth, borderBottomWidth: StyleSheet.hairlineWidth },
  divider: { height: StyleSheet.hairlineWidth },
  footer: { marginTop: 2 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    minHeight: 48,
  },
  text: { flex: 1, gap: 2 },
  value: { fontVariant: ['tabular-nums'], fontFamily: fonts.medium },
  stat: { gap: 2 },
  statValue: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
  unit: { fontFamily: fonts.semibold },
});
