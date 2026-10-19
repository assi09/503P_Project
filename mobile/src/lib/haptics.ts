import * as Haptics from 'expo-haptics';
import { Platform } from 'react-native';

// Haptics only exist on phones; on the web these are no-ops.
const enabled = Platform.OS === 'ios' || Platform.OS === 'android';

/** A light tap for buttons, cards and chips. */
export function tap() {
  if (enabled) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
}

/** A selection tick for switches, segmented controls and scrubbing. */
export function select() {
  if (enabled) Haptics.selectionAsync().catch(() => {});
}

/** Confirms a completed action, e.g. approving a reminder. */
export function success() {
  if (enabled) Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
}
