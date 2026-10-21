import { Platform } from 'react-native';

/** iOS gets the blurred tab bar floating over content; elsewhere the bar is solid and in layout. */
export const floatingTabBar = Platform.OS === 'ios';
