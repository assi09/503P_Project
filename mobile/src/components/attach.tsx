import { Ionicons } from '@expo/vector-icons';
import type { ReactNode } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import Animated, { FadeIn, SlideInDown } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { Attachment, Finding } from '@/api/types';
import { Text } from '@/components/Text';
import { EXPERTS, expertForMetric } from '@/lib/experts';
import { metricLabel } from '@/lib/format';
import { useWide } from '@/lib/layout';
import { DURATION, EASE_OUT } from '@/lib/motion';
import { isHovered } from '@/lib/platform';
import { radius, spacing, useColors, useMetricColor } from '@/theme';

/** Where the + button is on screen, so a popup can open right above it. */
export interface Anchor {
  x: number;
  y: number;
  width: number;
  height: number;
}

// Metrics worth asking about directly, grouped by the expert that owns them. Only the ones the
// person has data for are offered: attaching any other is refused.
const METRICS = [
  'sleep_minutes',
  'sleep_efficiency',
  'deep_sleep_minutes',
  'bedtime_hour',
  'hrv_ms',
  'resting_hr',
  'respiratory_rate',
  'skin_temp_variation_c',
  'steps',
  'active_zone_minutes',
  'distance_km',
];
const POPUP_WIDTH = 340;

/**
 * Attaching a recent finding or a metric to a question: a popup above the + button on wide
 * screens, a bottom sheet on phones.
 */
export function AttachSheet({
  visible,
  findings,
  available,
  anchor,
  onPick,
  onClose,
}: {
  visible: boolean;
  findings: Finding[];
  available?: string[]; // metrics with data; all are offered until it is known
  anchor?: Anchor;
  onPick: (attachment: Attachment) => void;
  onClose: () => void;
}) {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const wide = useWide();
  const { height, width } = useWindowDimensions();
  const metrics = METRICS.filter((m) => !available || available.includes(m));

  const content = (
    <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      {findings.length > 0 && (
        <Group title="Recent findings">
          {findings.map((finding) => (
            <FindingRow
              key={finding.id}
              finding={finding}
              onPress={() => onPick({ kind: 'finding', id: finding.id })}
            />
          ))}
        </Group>
      )}
      {EXPERTS.filter((expert) => expert.available && expert.id !== 'auto').map((expert) => {
        const owned = metrics.filter((metric) => expertForMetric(metric) === expert.id);
        if (!owned.length) return null;
        return (
          <Group key={expert.id} title={expert.label}>
            {owned.map((metric) => (
              <MetricRow
                key={metric}
                metric={metric}
                onPress={() => onPick({ kind: 'metric', metric })}
              />
            ))}
          </Group>
        );
      })}
    </ScrollView>
  );

  if (wide && anchor) {
    // Opens upward from the button, its right edge on the button's, kept on screen.
    const right = Math.max(spacing.md, width - (anchor.x + anchor.width));
    const bottom = height - anchor.y + spacing.sm;
    return (
      <Modal visible={visible} transparent animationType="none" onRequestClose={onClose}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close" />
        <Animated.View
          entering={FadeIn.duration(DURATION.fast)}
          style={[
            styles.popup,
            {
              right,
              bottom,
              maxHeight: Math.min(440, anchor.y - spacing.xl),
              backgroundColor: colors.surface,
              borderColor: colors.border,
            },
          ]}
        >
          <Text variant="label" color="muted" style={styles.popupTitle}>
            Ask about
          </Text>
          {content}
        </Animated.View>
      </Modal>
    );
  }

  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={onClose}>
      <Animated.View
        entering={FadeIn.duration(180)}
        style={[StyleSheet.absoluteFill, styles.backdrop]}
      >
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close" />
      </Animated.View>
      <Animated.View
        entering={SlideInDown.duration(DURATION.normal).easing(EASE_OUT)}
        style={[
          styles.sheet,
          {
            maxHeight: height * 0.75,
            paddingBottom: insets.bottom + spacing.lg,
            backgroundColor: colors.surface,
            borderColor: colors.border,
          },
        ]}
      >
        <View style={[styles.grabber, { backgroundColor: colors.border }]} />
        <View style={styles.header}>
          <Text variant="headline" accessibilityRole="header">
            Ask about
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close"
            hitSlop={10}
            onPress={onClose}
          >
            <Ionicons name="close" size={20} color={colors.muted} />
          </Pressable>
        </View>
        {content}
      </Animated.View>
    </Modal>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <View style={styles.group}>
      <Text variant="label" color="faint" style={styles.groupTitle}>
        {title}
      </Text>
      {children}
    </View>
  );
}

function MetricRow({ metric, onPress }: { metric: string; onPress: () => void }) {
  const colors = useColors();
  const color = useMetricColor(metric);
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={(state) => [
        styles.row,
        (isHovered(state) || state.pressed) && { backgroundColor: colors.track },
      ]}
    >
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={{ flex: 1 }}>{metricLabel(metric)}</Text>
    </Pressable>
  );
}

function FindingRow({ finding, onPress }: { finding: Finding; onPress: () => void }) {
  const colors = useColors();
  const color = useMetricColor(finding.metric);
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={(state) => [
        styles.row,
        (isHovered(state) || state.pressed) && { backgroundColor: colors.track },
      ]}
    >
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text numberOfLines={1} style={{ flex: 1 }}>
        {finding.title}
      </Text>
      <Text variant="caption" color="muted">
        {finding.change}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: { backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    borderWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: 0,
  },
  popup: {
    position: 'absolute',
    width: POPUP_WIDTH,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingTop: spacing.md,
    // A soft lift, so it reads as floating above the conversation.
    shadowColor: '#000',
    shadowOpacity: 0.12,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
  },
  popupTitle: { paddingHorizontal: spacing.lg, marginBottom: spacing.xs },
  grabber: { width: 36, height: 5, borderRadius: 3, alignSelf: 'center', marginTop: spacing.sm },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  content: { paddingHorizontal: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm },
  group: { gap: 2 },
  groupTitle: { paddingHorizontal: spacing.sm, paddingTop: spacing.sm, paddingBottom: 2 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.sm,
    paddingVertical: 10,
    borderRadius: radius.sm,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
});
