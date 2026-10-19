import { Ionicons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import type { ComponentProps } from 'react';

import { useColors } from '@/theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

const TABS: { name: string; title: string; icon: IconName }[] = [
  { name: 'index', title: 'Insights', icon: 'analytics-outline' },
  { name: 'ask', title: 'Ask', icon: 'chatbubble-ellipses-outline' },
  { name: 'reminders', title: 'Reminders', icon: 'notifications-outline' },
  { name: 'data', title: 'Data', icon: 'cloud-upload-outline' },
];

export default function TabLayout() {
  const colors = useColors();
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
        headerStyle: { backgroundColor: colors.surface },
        headerShadowVisible: false,
        headerTintColor: colors.text,
        sceneStyle: { backgroundColor: colors.background },
      }}
    >
      {TABS.map(({ name, title, icon }) => (
        <Tabs.Screen
          key={name}
          name={name}
          options={{
            title,
            tabBarIcon: ({ focused, size }) => (
              <Ionicons name={icon} size={size} color={focused ? colors.accent : colors.muted} />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}
