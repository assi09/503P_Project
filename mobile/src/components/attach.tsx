import { Ionicons } from '@expo/vector-icons';
import { Modal, Pressable, ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import Animated, { FadeIn, SlideInDown } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { Attachment, Finding } from '@/api/types';
import { PressableScale } from '@/components/PressableScale';
import { Text } from '@/components/Text';
import { Chip, SectionTitle } from '@/components/ui';
import { EXPERTS, expertForMetric } from '@/lib/experts';
import { metricLabel } from '@/lib/format';
import { DURATION, EASE_OUT } from '@/lib/motion';
import { radius, spacing, useColors, useMetricColor } from '@/theme';

// Metrics worth asking about directly, grouped below by the expert that owns them.
const METRICS = [
  'sleep_minutes',
  'sleep_score',
  'deep_sleep_minutes',
  'bedtime_hour',
  'hrv_ms',
  'resting_hr',
  'respiratory_rate',
  'skin_temp_variation_c',
  'steps',
  'active_zone_minutes',
  'cardio_load',
];

/** A bottom sheet for attaching a recent finding or a metric to a question. */
export function AttachSheet({
  visible,
  findings,
  onPick,
  onClose,
}: {
  visible: boolean;
  findings: Finding[];
  onPick: (attachment: Attachment) => void;
  onClose: () => void;
}) {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();

  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={onClose}>
      <Animated.View entering={FadeIn.duration(180)} style={[StyleSheet.absoluteFill, styles.backdrop]}>
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
            Attach to your question
          </Text>
          <Pressable accessibilityRole="button" accessibilityLabel="Close" hitSlop={10} onPress={onClose}>
            <Ionicons name="close" size={20} color={colors.muted} />
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={styles.content}>
          {findings.length > 0 && (
            <View style={styles.section}>
              <SectionTitle>Recent findings</SectionTitle>
              {findings.map((finding) => (
                <FindingRow
                  key={finding.id}
                  finding={finding}
                  onPress={() => onPick({ kind: 'finding', id: finding.id })}
                />
              ))}
            </View>
          )}
          {EXPERTS.filter((expert) => expert.available && expert.id !== 'auto').map((expert) => {
            const metrics = METRICS.filter((metric) => expertForMetric(metric) === expert.id);
            return (
              <View key={expert.id} style={styles.section}>
                <SectionTitle>{expert.label}</SectionTitle>
                <View style={styles.chips}>
                  {metrics.map((metric) => (
                    <Chip
                      key={metric}
                      label={metricLabel(metric)}
                      onPress={() => onPick({ kind: 'metric', metric })}
                    />
                  ))}
                </View>
              </View>
            );
          })}
        </ScrollView>
      </Animated.View>
    </Modal>
  );
}

function FindingRow({ finding, onPress }: { finding: Finding; onPress: () => void }) {
  const colors = useColors();
  const color = useMetricColor(finding.metric);
  return (
    <PressableScale
      accessibilityRole="button"
      onPress={onPress}
      style={[styles.finding, { backgroundColor: colors.surfaceRaised, borderColor: colors.border }]}
    >
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text variant="bodyStrong" numberOfLines={1} style={{ flex: 1 }}>
        {finding.title}
      </Text>
      <Text variant="caption" color={color}>
        {finding.change}
      </Text>
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  backdrop: { backgroundColor: 'rgba(0,0,0,0.45)' },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    width: '100%',
    maxWidth: 720,
    alignSelf: 'center',
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    borderWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: 0,
  },
  grabber: { width: 36, height: 5, borderRadius: 3, alignSelf: 'center', marginTop: spacing.sm },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  content: { paddingHorizontal: spacing.lg, gap: spacing.lg, paddingBottom: spacing.md },
  section: { gap: spacing.sm },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  finding: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
});
