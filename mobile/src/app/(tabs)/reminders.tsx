import { Text } from 'react-native';

import { useReminders } from '@/api/hooks';
import { QueryState, Screen } from '@/components/Screen';
import { useColors } from '@/theme';

export default function RemindersScreen() {
  const colors = useColors();
  const reminders = useReminders();
  return (
    <Screen>
      <QueryState query={reminders}>
        {() =>
          reminders.data?.map((reminder) => (
            <Text key={reminder.id} style={{ color: colors.text }}>
              {reminder.title}: {reminder.status}
            </Text>
          ))
        }
      </QueryState>
    </Screen>
  );
}
