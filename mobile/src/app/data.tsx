import { Redirect, useLocalSearchParams } from 'expo-router';

/** The old Data tab, now part of Settings; kept so earlier links and Google's return still land. */
export default function DataRedirect() {
  const { google } = useLocalSearchParams<{ google?: string }>();
  return <Redirect href={{ pathname: '/settings', params: google ? { google } : {} }} />;
}
