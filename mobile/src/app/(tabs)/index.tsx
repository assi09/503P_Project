import { StyleSheet, Text } from 'react-native';

import { useReport } from '@/api/hooks';
import { FindingCard, QuestionCard } from '@/components/insights';
import { QueryState, Screen } from '@/components/Screen';
import { SectionTitle } from '@/components/ui';
import { windowLabel } from '@/lib/format';
import { useColors } from '@/theme';

export default function InsightsScreen() {
  const colors = useColors();
  const report = useReport();

  return (
    <Screen refreshing={report.isRefetching} onRefresh={report.refetch}>
      <QueryState query={report}>
        {() => {
          const data = report.data!;
          const open = data.questions.filter((q) => !q.answer);
          const answered = data.questions.filter((q) => q.answer);
          return (
            <>
              <Text style={[styles.period, { color: colors.muted }]}>{windowLabel(data.period)}</Text>
              <Text style={[styles.headline, { color: colors.text }]}>{data.headline}</Text>

              {open.map((question) => (
                <QuestionCard key={question.id} question={question} />
              ))}

              <SectionTitle>What changed</SectionTitle>
              {data.findings.length === 0 ? (
                <Text style={{ color: colors.muted, lineHeight: 20 }}>
                  No metric differed clearly from the weeks before. You can still ask about any
                  metric in the Ask tab.
                </Text>
              ) : (
                data.findings.map((finding) => <FindingCard key={finding.id} finding={finding} />)
              )}

              {answered.map((question) => (
                <QuestionCard key={question.id} question={question} />
              ))}

              <Text style={[styles.footer, { color: colors.muted }]}>
                Patterns in your own Fitbit data, not medical advice.
              </Text>
            </>
          );
        }}
      </QueryState>
    </Screen>
  );
}

const styles = StyleSheet.create({
  period: { fontSize: 13, fontWeight: '600' },
  headline: { fontSize: 22, fontWeight: '700', lineHeight: 28 },
  footer: { fontSize: 12, textAlign: 'center', marginTop: 8 },
});
