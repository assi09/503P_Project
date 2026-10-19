import { Ionicons } from '@expo/vector-icons';
import { Link } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useAnswerQuestion } from '@/api/hooks';
import type { ContextQuestion, Finding } from '@/api/types';
import { LineChart } from '@/components/LineChart';
import { Card, ChangeBadge, Chip } from '@/components/ui';
import { metricLabel } from '@/lib/format';
import { spacing, useColors } from '@/theme';

export function FindingCard({ finding }: { finding: Finding }) {
  const colors = useColors();
  return (
    <Link href={`/finding/${finding.id}`} asChild>
      <Pressable accessibilityRole="button" accessibilityHint="Opens the evidence for this finding">
        {({ pressed }) => (
          <Card style={{ opacity: pressed ? 0.85 : 1 }}>
            <View style={styles.row}>
              <Text style={[styles.metric, { color: colors.muted }]}>{metricLabel(finding.metric)}</Text>
              <ChangeBadge direction={finding.direction} label={finding.change} />
            </View>
            <Text style={[styles.title, { color: colors.text }]}>{finding.title}</Text>
            <Text style={[styles.summary, { color: colors.muted }]} numberOfLines={2}>
              {finding.summary}
            </Text>
            <LineChart points={finding.series} metric={finding.metric} highlight={finding.highlight} />
            <View style={styles.row}>
              <Text style={[styles.evidence, { color: colors.accent }]}>
                {finding.evidenceIds.length === 1
                  ? 'Based on 1 computation'
                  : `Based on ${finding.evidenceIds.length} computations`}
              </Text>
              <Ionicons name="chevron-forward" size={16} color={colors.accent} />
            </View>
          </Card>
        )}
      </Pressable>
    </Link>
  );
}

export function QuestionCard({ question }: { question: ContextQuestion }) {
  const colors = useColors();
  const answer = useAnswerQuestion();
  const chosen = answer.isPending ? answer.variables?.answer : question.answer;

  return (
    <Card style={{ borderColor: colors.accent }}>
      <View style={styles.questionHeader}>
        <Ionicons name="help-circle-outline" size={20} color={colors.accent} />
        <Text style={[styles.questionTitle, { color: colors.text }]}>{question.prompt}</Text>
      </View>
      <Text style={[styles.summary, { color: colors.muted }]}>
        Your answer helps explain the change. It is only used for your own analysis.
      </Text>
      <View style={styles.chips}>
        {question.options.map((option) => (
          <Chip
            key={option}
            label={option}
            selected={chosen === option}
            disabled={answer.isPending}
            onPress={() => answer.mutate({ id: question.id, answer: option })}
          />
        ))}
      </View>
      {answer.error && (
        <Text style={{ color: colors.down }}>Could not save your answer. Please try again.</Text>
      )}
      {question.answer && !answer.isPending && (
        <Text style={[styles.summary, { color: colors.muted }]}>
          Noted: {question.answer}. Tap another option to change it.
        </Text>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  metric: { fontSize: 13, fontWeight: '500' },
  title: { fontSize: 18, fontWeight: '700' },
  summary: { fontSize: 14, lineHeight: 20 },
  evidence: { fontSize: 13, fontWeight: '600' },
  questionHeader: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
  questionTitle: { flex: 1, fontSize: 16, fontWeight: '600', lineHeight: 22 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
});
