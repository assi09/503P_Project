import { StyleSheet, View } from 'react-native';

import { useAccessRequests, useDecideAccessRequest } from '@/api/hooks';
import { Section } from '@/components/list';
import { QueryState, Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { Button } from '@/components/ui';
import { timeAgo } from '@/lib/format';
import { spacing } from '@/theme';

/** The owner's list of sign-ups waiting for approval, as members or as supervisors. */
export default function Approvals() {
  const requests = useAccessRequests();
  const decide = useDecideAccessRequest();

  return (
    <Screen refreshing={requests.isRefetching} onRefresh={requests.refetch}>
      <QueryState query={requests}>
        {() => (
          <Section
            title="Waiting"
            footer="Approving lets someone into the app; a supervisor can also create a team and see its weekly report. To let them connect their Fitbit, also add their email as a test user in the Google Cloud console (APIs & Services, OAuth consent screen)."
          >
            {requests.data!.length === 0 ? (
              <View style={styles.request}>
                <Text color="muted">No one is waiting.</Text>
              </View>
            ) : (
              requests.data!.map((request) => {
                const deciding = decide.isPending && decide.variables?.id === request.id;
                return (
                  <View key={request.id} style={styles.request}>
                    <Text variant="bodyStrong">{request.email}</Text>
                    <Text variant="caption" color="muted">
                      Asked {timeAgo(request.requestedAt)}
                    </Text>
                    <View style={styles.actions}>
                      <Button
                        label="Approve"
                        disabled={deciding}
                        onPress={() => decide.mutate({ id: request.id, approve: true })}
                      />
                      <Button
                        label="Approve as supervisor"
                        variant="secondary"
                        disabled={deciding}
                        onPress={() =>
                          decide.mutate({ id: request.id, approve: true, role: 'supervisor' })
                        }
                      />
                      <Button
                        label="Reject"
                        variant="secondary"
                        disabled={deciding}
                        onPress={() => decide.mutate({ id: request.id, approve: false })}
                      />
                    </View>
                  </View>
                );
              })
            )}
          </Section>
        )}
      </QueryState>
      {decide.error && (
        <Text variant="caption" color="danger">
          {decide.error.message}
        </Text>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  request: { gap: 2, paddingVertical: spacing.md },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.sm },
});
