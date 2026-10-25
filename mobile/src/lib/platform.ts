import { Platform, type PressableStateCallbackType } from 'react-native';

/** iOS gets the blurred tab bar floating over content; elsewhere the bar is solid and in layout. */
export const floatingTabBar = Platform.OS === 'ios';

/** Whether the pointer is over a Pressable. Only react-native-web reports it; it is not in the types. */
export function isHovered(state: PressableStateCallbackType): boolean {
  return (state as PressableStateCallbackType & { hovered?: boolean }).hovered === true;
}
