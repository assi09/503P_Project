import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { Tabs } from 'expo-router';
import type { ComponentProps } from 'react';
import { StyleSheet, useWindowDimensions } from 'react-native';

import { select } from '@/lib/haptics';
import { floatingTabBar as glass } from '@/lib/platform';
import { CONTENT_WIDTH, fonts, useColors, useScheme } from '@/theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

const TABS: { name: string; title: string; icon: IconName; iconActive: IconName }[] = [
  { name: 'index', title: 'Today', icon: 'pulse-outline', iconActive: 'pulse' },
  { name: 'ask', title: 'Ask', icon: 'chatbubble-outline', iconActive: 'chatbubble' },
  {
    name: 'reminders',
    title: 'Reminders',
    icon: 'notifications-outline',
    iconActive: 'notifications',
  },
  { name: 'settings', title: 'Settings', icon: 'settings-outline', iconActive: 'settings' },
];

export default function TabLayout() {
  const colors = useColors();
  const scheme = useScheme();
  // On wide screens keep the tabs within the content column instead of spread edge to edge.
  const { width } = useWindowDimensions();
  const inset = Math.max(0, (width - CONTENT_WIDTH) / 2);
  return (
    <Tabs
      screenListeners={{ tabPress: () => select() }}
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.text,
        tabBarInactiveTintColor: colors.faint,
        tabBarLabelStyle: { fontFamily: fonts.medium, fontSize: 11, lineHeight: 15, flexShrink: 0 },
        tabBarStyle: {
          backgroundColor: glass ? 'transparent' : colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: StyleSheet.hairlineWidth,
          paddingHorizontal: inset,
          // iOS adds the home-indicator inset below the bar; elsewhere give the labels room.
          ...(glass ? { position: 'absolute' } : { height: 62, paddingTop: 6, paddingBottom: 8 }),
        },
        tabBarBackground: glass
          ? () => (
              <BlurView
                tint={scheme === 'dark' ? 'systemChromeMaterialDark' : 'systemChromeMaterialLight'}
                intensity={90}
                style={StyleSheet.absoluteFill}
              />
            )
          : undefined,
        sceneStyle: { backgroundColor: colors.background },
      }}
    >
      {TABS.map(({ name, title, icon, iconActive }) => (
        <Tabs.Screen
          key={name}
          name={name}
          options={{
            title,
            tabBarIcon: ({ focused, size }) => (
              <Ionicons
                name={focused ? iconActive : icon}
                size={size - 2}
                color={focused ? colors.text : colors.faint}
              />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}
