import { useReport } from '@/api/hooks';
import { FindingCard, QuestionCard } from '@/components/insights';
import { QueryState, Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { Card, SectionTitle } from '@/components/ui';
import { windowLabel } from '@/lib/format';

export default function TodayScreen() {
  const report = useReport();
  const period = report.data ? windowLabel(report.data.period) : undefined;

  return (
    <Screen
      title="Today"
      subtitle={period}
      refreshing={report.isRefetching}
      onRefresh={report.refetch}
    >
      <QueryState query={report}>
        {() => {
          const data = report.data!;
          const open = data.questions.filter((q) => !q.answer);
          const answered = data.questions.filter((q) => q.answer);
          return (
            <>
              <Text variant="title">{data.headline}</Text>

              {open.map((question) => (
                <QuestionCard key={question.id} question={question} />
              ))}

              <SectionTitle>What changed</SectionTitle>
              {data.findings.length === 0 ? (
                <Card>
                  <Text color="muted">
                    No metric differed clearly from the weeks before. You can still ask about any
                    metric in the Ask tab.
                  </Text>
                </Card>
              ) : (
                data.findings.map((finding) => <FindingCard key={finding.id} finding={finding} />)
              )}

              {answered.map((question) => (
                <QuestionCard key={question.id} question={question} />
              ))}

              <Text variant="caption" color="faint" style={{ textAlign: 'center', marginTop: 8 }}>
                Patterns in your own Fitbit data, not medical advice.
              </Text>
            </>
          );
        }}
      </QueryState>
    </Screen>
  );
}
