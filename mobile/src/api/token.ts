// The session token: kept in memory for requests and stored so the app stays signed in.
// Phones keep it in the system keychain/keystore; the web build has only localStorage.
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const KEY = 'patterns.session';
let current: string | null = null;

export function getToken(): string | null {
  return current;
}

/** Reads the stored token at launch; a storage failure means signed out, not a crash. */
export async function loadToken(): Promise<string | null> {
  try {
    current =
      Platform.OS === 'web'
        ? (globalThis.localStorage?.getItem(KEY) ?? null)
        : await SecureStore.getItemAsync(KEY);
  } catch {
    current = null;
  }
  return current;
}

export async function saveToken(token: string | null): Promise<void> {
  current = token;
  try {
    if (Platform.OS === 'web') {
      if (token) globalThis.localStorage?.setItem(KEY, token);
      else globalThis.localStorage?.removeItem(KEY);
    } else if (token) {
      await SecureStore.setItemAsync(KEY, token);
    } else {
      await SecureStore.deleteItemAsync(KEY);
    }
  } catch {
    // Blocked storage: the session lasts until the app closes.
  }
}
