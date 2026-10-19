import { Text } from 'react-native';

import { useDataStatus } from '@/api/hooks';
import { QueryState, Screen } from '@/components/Screen';
import { useColors } from '@/theme';

export default function DataScreen() {
  const colors = useColors();
  const status = useDataStatus();
  return (
    <Screen>
      <QueryState query={status}>
        {() => (
          <Text style={{ color: colors.text }}>
            Source: {status.data?.source}, {status.data?.coverage.length} metrics
          </Text>
        )}
      </QueryState>
    </Screen>
  );
}
