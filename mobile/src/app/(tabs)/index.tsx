import { Link } from 'expo-router';
import { Text } from 'react-native';

import { useReport } from '@/api/hooks';
import { QueryState, Screen } from '@/components/Screen';
import { useColors } from '@/theme';

export default function InsightsScreen() {
  const colors = useColors();
  const report = useReport();
  return (
    <Screen>
      <QueryState query={report}>
        {() => (
          <>
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '700' }}>
              {report.data?.headline}
            </Text>
            {report.data?.findings.map((finding) => (
              <Link key={finding.id} href={`/finding/${finding.id}`} style={{ color: colors.accent }}>
                {finding.title} ({finding.change})
              </Link>
            ))}
          </>
        )}
      </QueryState>
    </Screen>
  );
}
