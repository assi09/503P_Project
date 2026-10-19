import { Text } from 'react-native';

import { useChat } from '@/api/hooks';
import { QueryState, Screen } from '@/components/Screen';
import { useColors } from '@/theme';

export default function AskScreen() {
  const colors = useColors();
  const chat = useChat();
  return (
    <Screen>
      <QueryState query={chat}>
        {() => <Text style={{ color: colors.muted }}>{chat.data?.length ?? 0} messages</Text>}
      </QueryState>
    </Screen>
  );
}
