import { useLocalSearchParams } from 'expo-router';
import { Text } from 'react-native';

import { useReport } from '@/api/hooks';
import { QueryState, Screen } from '@/components/Screen';
import { useColors } from '@/theme';

export default function FindingScreen() {
  const colors = useColors();
  const { id } = useLocalSearchParams<{ id: string }>();
  const report = useReport();
  const finding = report.data?.findings.find((f) => f.id === id);
  return (
    <Screen>
      <QueryState query={report}>
        {() => (
          <Text style={{ color: colors.text }}>{finding ? finding.summary : 'Finding not found.'}</Text>
        )}
      </QueryState>
    </Screen>
  );
}
