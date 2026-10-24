import { Ionicons } from '@expo/vector-icons';
import { memo, useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  FadeInDown,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

import type { ChatMessage, Evidence, ExpertChoice } from '@/api/types';
import { EvidenceChip } from '@/components/evidence';
import { LogDraftCard } from '@/components/LogDraftCard';
import { Text } from '@/components/Text';
import { expertInfo, useExpertColor } from '@/lib/experts';
import { metricLabel, toolLabel } from '@/lib/format';
import { radius, spacing, useColors } from '@/theme';

const ENTER = FadeInDown.duration(260);

/** Short label for an evidence chip, e.g. "Compared two periods · Bedtime". */
function chipLabel(id: string, known: Record<string, Evidence>): string {
  const evidence = known[id];
  if (!evidence) return 'Evidence';
  return `${toolLabel(evidence.tool)} · ${evidence.metrics.map(metricLabel).join(', ')}`;
}

export const MessageBubble = memo(function MessageBubble({
  message,
  knownEvidence,
  findingTitles,
}: {
  message: ChatMessage;
  knownEvidence: Record<string, Evidence>;
  findingTitles: Record<string, string>;
}) {
  const colors = useColors();

  if (message.role === 'user') {
    return (
      <Animated.View
        entering={ENTER}
        style={[styles.mine, { backgroundColor: colors.surfaceRaised, borderColor: colors.border }]}
      >
        {message.attachment && (
          <Text variant="caption" color="accent" style={{ marginBottom: 2 }}>
            About:{' '}
            {message.attachment.kind === 'finding'
              ? (findingTitles[message.attachment.id] ?? 'a finding')
              : metricLabel(message.attachment.metric)}
          </Text>
        )}
        <Text>{message.text}</Text>
      </Animated.View>
    );
  }

  return (
    <Animated.View entering={ENTER} style={styles.theirs}>
      <Avatar expert={message.refused ? undefined : (message.answeredBy ?? 'general')} />
      <View style={styles.theirsBody}>
        {message.answeredBy && !message.refused && <AnswerHeader message={message} />}
        {message.refused ? (
          <View
            style={[
              styles.refused,
              { backgroundColor: `${colors.warning}14`, borderColor: `${colors.warning}55` },
            ]}
          >
            <View style={styles.refusedHeader}>
              <Ionicons name="shield-checkmark" size={14} color={colors.warning} />
              <Text variant="caption" color="warning">
                Outside what I can answer
              </Text>
            </View>
            <Text>{message.text}</Text>
          </View>
        ) : (
          <Text>{message.text}</Text>
        )}
        {message.actionIds?.map((id) => (
          <LogDraftCard key={id} id={id} />
        ))}
        {message.evidenceIds.length > 0 && (
          <View style={styles.chips}>
            {message.evidenceIds.map((id) => (
              <EvidenceChip
                key={id}
                id={id}
                label={chipLabel(id, knownEvidence)}
                metric={knownEvidence[id]?.metrics[0]}
              />
            ))}
          </View>
        )}
      </View>
    </Animated.View>
  );
});

/** The answering expert's icon; a shield for refusals. */
function Avatar({ expert }: { expert?: ExpertChoice | 'general' }) {
  const colors = useColors();
  const expertColor = useExpertColor(expert ?? 'general');
  const color = expert ? expertColor : colors.warning;
  return (
    <View style={[styles.avatar, { backgroundColor: `${color}22` }]}>
      <Ionicons name={expert ? expertInfo(expert).icon : 'shield-checkmark'} size={13} color={color} />
    </View>
  );
}

/** "Recovery · auto · asked Sleep": who answered, whether the router chose them, whom they asked. */
function AnswerHeader({ message }: { message: ChatMessage }) {
  const answeredBy = message.answeredBy ?? 'general';
  const color = useExpertColor(answeredBy);
  const label = answeredBy === 'general' ? 'General' : expertInfo(answeredBy).label;
  const details = [
    message.routed ? 'auto' : 'chosen',
    ...(message.consulted?.length
      ? [`asked ${message.consulted.map((e) => expertInfo(e).label).join(', ')}`]
      : []),
  ];
  return (
    <Text variant="caption" color="faint" style={{ fontSize: 12 }}>
      <Text variant="caption" color={color} style={{ fontSize: 12 }}>
        {label}
      </Text>
      {details.map((detail) => ` · ${detail}`).join('')}
    </Text>
  );
}

function Dot({ delay }: { delay: number }) {
  const colors = useColors();
  const opacity = useSharedValue(0.25);
  useEffect(() => {
    opacity.set(
      withDelay(
        delay,
        withRepeat(withSequence(withTiming(1, { duration: 350 }), withTiming(0.25, { duration: 350 })), -1),
      ),
    );
  }, [delay, opacity]);
  const style = useAnimatedStyle(() => ({ opacity: opacity.value }));
  return <Animated.View style={[styles.dot, { backgroundColor: colors.muted }, style]} />;
}

/** Shown while an answer is being worked on, by the chosen expert or the router. */
export function Thinking({ expert }: { expert: ExpertChoice }) {
  const label =
    expert === 'auto' ? 'Finding the right expert' : `${expertInfo(expert).label} is looking at your data`;
  return (
    <Animated.View entering={ENTER} style={styles.theirs} accessibilityLabel={label}>
      <Avatar expert={expert} />
      <View style={styles.dots}>
        <Dot delay={0} />
        <Dot delay={150} />
        <Dot delay={300} />
        <Text variant="caption" color="muted" style={{ marginLeft: spacing.sm }}>
          {label}
        </Text>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  mine: {
    alignSelf: 'flex-end',
    maxWidth: '82%',
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.lg,
    borderBottomRightRadius: 6,
    borderWidth: StyleSheet.hairlineWidth,
  },
  theirs: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start', maxWidth: '94%' },
  theirsBody: { flex: 1, gap: 6, paddingTop: 4 },
  avatar: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  refused: { padding: spacing.md, borderRadius: radius.md, borderWidth: 1, gap: 4 },
  refusedHeader: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  dots: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingTop: 6 },
  dot: { width: 6, height: 6, borderRadius: 3 },
});
