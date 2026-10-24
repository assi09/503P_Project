import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
  type TextInputProps,
} from 'react-native';

import { ApiError } from '@/api/http';
import { Text } from '@/components/Text';
import { Button } from '@/components/ui';
import { useSession } from '@/lib/session';
import { fonts, radius, spacing, useColors } from '@/theme';

type Mode = 'signUp' | 'logIn';

const COPY = {
  signUp: {
    title: 'Create your account',
    lead: 'Patterns is in testing, so each new account is approved by hand. You can connect your Fitbit once you are in.',
    submit: 'Create account',
    switchPrompt: 'Already have an account?',
    switchLabel: 'Sign in',
    switchTo: '/sign-in',
  },
  logIn: {
    title: 'Welcome back',
    lead: 'Sign in to see what changed in your data.',
    submit: 'Sign in',
    switchPrompt: 'New to Patterns?',
    switchLabel: 'Create an account',
    switchTo: '/sign-up',
  },
} as const;

/** Email and password, for both creating an account and signing in. */
export function AuthForm({ mode }: { mode: Mode }) {
  const colors = useColors();
  const session = useSession();
  const copy = COPY[mode];
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = email.trim().length > 0 && password.length > 0 && !busy;

  async function submit() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const credentials = { email: email.trim(), password };
      await (mode === 'signUp' ? session.signUp(credentials) : session.logIn(credentials));
      // The routes switch on the session, so there is nowhere to navigate to here.
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Something went wrong. Try again.');
      setBusy(false);
    }
  }

  const inputStyle = [
    styles.input,
    { backgroundColor: colors.surface, borderColor: colors.border, color: colors.text },
  ];
  const shared: TextInputProps = {
    autoCapitalize: 'none',
    autoCorrect: false,
    placeholderTextColor: colors.faint,
    editable: !busy,
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={{ flex: 1, backgroundColor: colors.background }}
    >
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.form}>
          <Text variant="title">{copy.title}</Text>
          <Text color="muted" style={styles.lead}>
            {copy.lead}
          </Text>

          <View style={styles.field}>
            <Text variant="caption" color="muted">
              Email
            </Text>
            <TextInput
              {...shared}
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              keyboardType="email-address"
              autoComplete="email"
              textContentType="emailAddress"
              returnKeyType="next"
              accessibilityLabel="Email"
              style={inputStyle}
            />
          </View>

          <View style={styles.field}>
            <Text variant="caption" color="muted">
              Password
            </Text>
            <View>
              <TextInput
                {...shared}
                value={password}
                onChangeText={setPassword}
                placeholder={mode === 'signUp' ? 'At least 10 characters' : ''}
                secureTextEntry={!showPassword}
                autoComplete={mode === 'signUp' ? 'new-password' : 'current-password'}
                textContentType={mode === 'signUp' ? 'newPassword' : 'password'}
                returnKeyType="go"
                onSubmitEditing={submit}
                accessibilityLabel="Password"
                style={[inputStyle, styles.passwordInput]}
              />
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={showPassword ? 'Hide password' : 'Show password'}
                onPress={() => setShowPassword((shown) => !shown)}
                hitSlop={8}
                style={styles.eye}
              >
                <Ionicons
                  name={showPassword ? 'eye-off-outline' : 'eye-outline'}
                  size={18}
                  color={colors.muted}
                />
              </Pressable>
            </View>
          </View>

          {error && (
            <View
              accessibilityRole="alert"
              style={[styles.error, { backgroundColor: colors.accentSoft }]}
            >
              <Ionicons name="alert-circle-outline" size={16} color={colors.danger} />
              <Text variant="caption" style={{ flex: 1, color: colors.danger }}>
                {error}
              </Text>
            </View>
          )}

          <View style={styles.actions}>
            <Button
              label={busy ? 'One moment…' : copy.submit}
              onPress={submit}
              disabled={!canSubmit}
            />
          </View>

          <View style={styles.switchRow}>
            <Text variant="caption" color="muted">
              {copy.switchPrompt}
            </Text>
            <Pressable accessibilityRole="link" onPress={() => router.replace(copy.switchTo)}>
              <Text variant="caption" style={{ fontFamily: fonts.semibold }}>
                {copy.switchLabel}
              </Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  scroll: { flexGrow: 1, padding: spacing.xl, paddingTop: spacing.lg },
  form: { width: '100%', maxWidth: 420, alignSelf: 'center', gap: spacing.md },
  lead: { marginBottom: spacing.sm },
  field: { gap: spacing.xs },
  input: {
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontFamily: fonts.regular,
    fontSize: 15,
  },
  passwordInput: { paddingRight: 44 },
  eye: { position: 'absolute', right: 14, top: 0, bottom: 0, justifyContent: 'center' },
  error: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
  },
  actions: { flexDirection: 'row', marginTop: spacing.sm },
  switchRow: { flexDirection: 'row', gap: 6, marginTop: spacing.sm, flexWrap: 'wrap' },
});
