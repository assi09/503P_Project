import { httpClient } from './http';
import { mockClient } from './mock';
import type { ApiClient } from './types';

// Set EXPO_PUBLIC_API_URL to use the real backend; without it the app runs on mock data.
const apiUrl = process.env.EXPO_PUBLIC_API_URL;

export const api: ApiClient = apiUrl ? httpClient(apiUrl) : mockClient;
export const usingMock = !apiUrl;

export type * from './types';
