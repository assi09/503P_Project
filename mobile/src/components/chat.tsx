import { Ionicons } from '@expo/vector-icons';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import type { ChatMessage, Evidence } from '@/api/types';
import { EvidenceChip } from '@/components/evidence';
import { metricLabel, toolLabel } from '@/lib/format';
import { radius, spacing, useColors } from '@/theme';

/** Short label for an evidence chip, e.g. "Compared two periods · Bedtime". */
function chipLabel(id: string, known: Record<string, Evidence>): string {
  const evidence = known[id];
  if (!evidence) return 'Evidence';
  return `${toolLabel(evidence.tool)} · ${evidence.metrics.map(metricLabel).join(', ')}`;
}

export function MessageBubble({
  message,
  knownEvidence,
}: {
  message: ChatMessage;
  knownEvidence: Record<string, Evidence>;
}) {
  const colors = useColors();
  const mine = message.role === 'user';

  if (mine) {
    return (
      <View style={[styles.bubble, styles.mine, { backgroundColor: colors.accent }]}>
        <Text style={[styles.text, { color: colors.onAccent }]}>{message.text}</Text>
      </View>
    );
  }

  return (
    <View style={styles.theirsColumn}>
      <View
        style={[
          styles.bubble,
          styles.theirs,
          {
            backgroundColor: colors.surface,
            borderColor: message.refused ? colors.warning : colors.border,
          },
        ]}
      >
        {message.refused && (
          <View style={styles.refusedHeader}>
            <Ionicons name="shield-checkmark-outline" size={14} color={colors.warning} />
            <Text style={[styles.refusedLabel, { color: colors.warning }]}>Outside what I can answer</Text>
          </View>
        )}
        <Text style={[styles.text, { color: colors.text }]}>{message.text}</Text>
      </View>
      {message.evidenceIds.length > 0 && (
        <View style={styles.chips}>
          {message.evidenceIds.map((id) => (
            <EvidenceChip key={id} id={id} label={chipLabel(id, knownEvidence)} />
          ))}
        </View>
      )}
    </View>
  );
}

export function Thinking() {
  const colors = useColors();
  return (
    <View
      style={[styles.bubble, styles.theirs, styles.thinking, { backgroundColor: colors.surface, borderColor: colors.border }]}
      accessibilityLabel="Working on an answer"
    >
      <ActivityIndicator size="small" color={colors.muted} />
      <Text style={{ color: colors.muted }}>Looking at your data…</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bubble: {
    maxWidth: '85%',
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.lg,
  },
  mine: { alignSelf: 'flex-end', borderBottomRightRadius: 4 },
  theirs: { alignSelf: 'flex-start', borderWidth: StyleSheet.hairlineWidth, borderBottomLeftRadius: 4 },
  theirsColumn: { gap: 6, alignItems: 'flex-start' },
  text: { fontSize: 15, lineHeight: 21 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, maxWidth: '90%' },
  refusedHeader: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 },
  refusedLabel: { fontSize: 12, fontWeight: '600' },
  thinking: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
});
