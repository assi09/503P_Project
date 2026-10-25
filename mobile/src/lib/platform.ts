import { Platform, type PressableStateCallbackType } from 'react-native';

/** iOS gets the blurred tab bar floating over content; elsewhere the bar is solid and in layout. */
export const floatingTabBar = Platform.OS === 'ios';

/**
 * Whether this device can hover: a mouse or trackpad on the web. Touch screens, including phones
 * in a browser, cannot, so anything shown on hover must be shown there all the time.
 */
export function canHover(): boolean {
  if (Platform.OS !== 'web') return false;
  try {
    return globalThis.matchMedia?.('(hover: hover)').matches ?? false;
  } catch {
    return false;
  }
}

/** Whether the pointer is over a Pressable. Only react-native-web reports it; it is not in the types. */
export function isHovered(state: PressableStateCallbackType): boolean {
  return (state as PressableStateCallbackType & { hovered?: boolean }).hovered === true;
}
