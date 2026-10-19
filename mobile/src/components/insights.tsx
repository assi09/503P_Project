import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { useAnswerQuestion } from '@/api/hooks';
import type { ContextQuestion, Finding } from '@/api/types';
import { LineChart } from '@/components/LineChart';
import { PressableScale } from '@/components/PressableScale';
import { Text } from '@/components/Text';
import { Card, ChangeBadge, Chip } from '@/components/ui';
import { metricLabel } from '@/lib/format';
import { spacing, useColors, useMetricColor } from '@/theme';

export function FindingCard({ finding }: { finding: Finding }) {
  const colors = useColors();
  const color = useMetricColor(finding.metric);
  const computations = finding.evidenceIds.length;
  return (
    <PressableScale
      accessibilityRole="link"
      accessibilityHint="Opens the evidence for this finding"
      onPress={() => router.push(`/finding/${finding.id}`)}
    >
      <Card glow={color}>
        <View style={styles.row}>
          <View style={styles.metric}>
            <View style={[styles.dot, { backgroundColor: color }]} />
            <Text variant="caption" color="muted">
              {metricLabel(finding.metric)}
            </Text>
          </View>
          <ChangeBadge direction={finding.direction} label={finding.change} color={color} />
        </View>
        <Text variant="headline">{finding.title}</Text>
        <Text color="muted" numberOfLines={2}>
          {finding.summary}
        </Text>
        <View style={styles.chart}>
          <LineChart
            points={finding.series}
            metric={finding.metric}
            highlight={finding.highlight}
            height={64}
          />
        </View>
        <View style={styles.row}>
          <Text variant="caption" color="faint">
            {computations === 1 ? 'Based on 1 computation' : `Based on ${computations} computations`}
          </Text>
          <Ionicons name="chevron-forward" size={16} color={colors.faint} />
        </View>
      </Card>
    </PressableScale>
  );
}

export function QuestionCard({ question }: { question: ContextQuestion }) {
  const colors = useColors();
  const answer = useAnswerQuestion();
  const chosen = answer.isPending ? answer.variables?.answer : question.answer;

  return (
    <Card glow={colors.accent}>
      <View style={styles.questionHeader}>
        <View style={[styles.questionIcon, { backgroundColor: colors.accentSoft }]}>
          <Ionicons name="sparkles" size={14} color={colors.accent} />
        </View>
        <Text variant="headline" style={{ flex: 1 }}>
          {question.prompt}
        </Text>
      </View>
      <Text variant="caption" color="muted">
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
        <Text variant="caption" color="danger">
          Could not save your answer. Please try again.
        </Text>
      )}
      {question.answer && !answer.isPending && (
        <Text variant="caption" color="muted">
          Noted: {question.answer}. Tap another option to change it.
        </Text>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  metric: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  chart: { marginVertical: spacing.xs },
  questionHeader: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
  questionIcon: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: -2,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
});
