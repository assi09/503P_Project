import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { memo, useEffect, useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';
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
import { useEvidence } from '@/api/hooks';
import { EvidenceChip } from '@/components/evidence';
import { LogDraftCard } from '@/components/LogDraftCard';
import { Text } from '@/components/Text';
import { expertInfo, useExpertColor } from '@/lib/experts';
import { evidenceLabel, metricLabel } from '@/lib/format';
import { isHovered } from '@/lib/platform';
import { fonts, radius, spacing, useColors } from '@/theme';

const ENTER = FadeInDown.duration(260);

/** A chip for evidence the report may not hold (a chat answer's): fetched to name it. */
function AnswerEvidenceChip({ id, known }: { id: string; known?: Evidence }) {
  const fetched = useEvidence(id, !known);
  const evidence = known ?? fetched.data;
  // Evidence about many metrics takes the accent color rather than its first metric's.
  const metric = evidence && evidence.metrics.length <= 2 ? evidence.metrics[0] : undefined;
  return <EvidenceChip id={id} label={evidenceLabel(evidence)} metric={metric} />;
}

export const MessageBubble = memo(function MessageBubble({
  message,
  knownEvidence,
  findingTitles,
  onEdit,
  onRetry,
  busy = false,
}: {
  message: ChatMessage;
  knownEvidence: Record<string, Evidence>;
  findingTitles: Record<string, string>;
  onEdit?: (text: string) => void; // sends the edited question in place of this one
  onRetry?: () => void; // asks the question this answers again
  busy?: boolean; // an answer is on its way: no edits or retries meanwhile
}) {
  const colors = useColors();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.text);

  if (message.role === 'user' && editing) {
    const send = () => {
      const text = draft.trim();
      if (!text || busy) return;
      setEditing(false);
      if (text !== message.text) onEdit?.(text);
    };
    return (
      <View style={styles.editing}>
        <TextInput
          accessibilityLabel="Edit your message"
          value={draft}
          onChangeText={setDraft}
          multiline
          autoFocus
          maxLength={500}
          style={[
            styles.editInput,
            { color: colors.text, borderColor: colors.accent, backgroundColor: colors.surface },
          ]}
        />
        <Text variant="caption" color="muted">
          Sending replaces this message and the replies after it.
        </Text>
        <View style={styles.editActions}>
          <Pressable
            accessibilityRole="button"
            onPress={() => {
              setDraft(message.text);
              setEditing(false);
            }}
            style={styles.editButton}
          >
            <Text variant="caption" color="muted" style={{ fontFamily: fonts.semibold }}>
              Cancel
            </Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={send}
            disabled={busy || !draft.trim()}
            style={[styles.editButton, { backgroundColor: colors.text }]}
          >
            <Text
              variant="caption"
              style={{ fontFamily: fonts.semibold, color: colors.background }}
            >
              Send
            </Text>
          </Pressable>
        </View>
      </View>
    );
  }

  if (message.role === 'user') {
    return (
      <Animated.View entering={ENTER} style={styles.mineColumn}>
        <View
          style={[
            styles.mine,
            { backgroundColor: colors.surfaceRaised, borderColor: colors.border },
          ]}
        >
          {message.attachment && (
            <Text variant="caption" color="accent" style={{ marginBottom: 2 }}>
              About:{' '}
              {message.attachment.kind === 'finding'
                ? (findingTitles[message.attachment.id] ?? 'a finding')
                : metricLabel(message.attachment.metric)}
            </Text>
          )}
          <Text selectable>{message.text}</Text>
        </View>
        <View style={[styles.actions, styles.actionsMine]}>
          <CopyButton text={message.text} />
          {onEdit && (
            <ActionButton
              icon="pencil-outline"
              label="Edit"
              disabled={busy}
              onPress={() => {
                setDraft(message.text);
                setEditing(true);
              }}
            />
          )}
        </View>
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
              <AnswerEvidenceChip key={id} id={id} known={knownEvidence[id]} />
            ))}
          </View>
        )}
        <View style={styles.actions}>
          <CopyButton text={message.text} />
          {onRetry && (
            <ActionButton icon="refresh" label="Retry" disabled={busy} onPress={onRetry} />
          )}
        </View>
      </View>
    </Animated.View>
  );
});

/** Copies a message's text, and says so for a moment. */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);
  return (
    <ActionButton
      icon={copied ? 'checkmark' : 'copy-outline'}
      label={copied ? 'Copied' : 'Copy'}
      onPress={() => {
        Clipboard.setStringAsync(text).then(() => setCopied(true));
      }}
    />
  );
}

function ActionButton({
  icon,
  label,
  onPress,
  disabled = false,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  const colors = useColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      hitSlop={4}
      style={(state) => [
        styles.action,
        (isHovered(state) || state.pressed) && !disabled && { backgroundColor: colors.track },
        disabled && { opacity: 0.4 },
      ]}
    >
      <Ionicons name={icon} size={14} color={colors.muted} />
      <Text variant="caption" color="muted">
        {label}
      </Text>
    </Pressable>
  );
}

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
  mineColumn: { alignSelf: 'flex-end', alignItems: 'flex-end', maxWidth: '82%', gap: 2 },
  actions: { flexDirection: 'row', gap: 2, marginLeft: -6 },
  actionsMine: { marginLeft: 0, marginRight: -6 },
  action: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 6,
    paddingVertical: 4,
    borderRadius: radius.sm,
  },
  editing: { alignSelf: 'stretch', gap: spacing.xs },
  editInput: {
    borderWidth: 1,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    minHeight: 64,
    fontFamily: fonts.regular,
    fontSize: 15,
    outlineWidth: 0, // the accent border already shows focus; no second ring on the web
  },
  editActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: spacing.sm },
  editButton: { paddingHorizontal: spacing.md, paddingVertical: 7, borderRadius: radius.pill },
  mine: {
    alignSelf: 'flex-end',
    maxWidth: '100%', // the column around it sets the width
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
