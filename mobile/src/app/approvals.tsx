import { StyleSheet, View } from 'react-native';

import { useAccessRequests, useDecideAccessRequest } from '@/api/hooks';
import { QueryState, Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { Button, Card } from '@/components/ui';
import { timeAgo } from '@/lib/format';
import { spacing } from '@/theme';

/** The owner's list of sign-ups waiting for approval. */
export default function Approvals() {
  const requests = useAccessRequests();
  const decide = useDecideAccessRequest();

  return (
    <Screen refreshing={requests.isRefetching} onRefresh={requests.refetch}>
      <Text color="muted" style={styles.note}>
        Approving lets someone into the app. To let them connect their Fitbit, also add their email
        as a test user in the Google Cloud console (APIs & Services, OAuth consent screen).
      </Text>
      <QueryState query={requests}>
        {() =>
          requests.data!.length === 0 ? (
            <Card>
              <Text color="muted">No one is waiting.</Text>
            </Card>
          ) : (
            <View style={styles.list}>
              {requests.data!.map((request) => {
                const deciding = decide.isPending && decide.variables?.id === request.id;
                return (
                  <Card key={request.id}>
                    <Text variant="headline">{request.email}</Text>
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
                        label="Reject"
                        variant="secondary"
                        disabled={deciding}
                        onPress={() => decide.mutate({ id: request.id, approve: false })}
                      />
                    </View>
                  </Card>
                );
              })}
            </View>
          )
        }
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
  note: { marginBottom: spacing.sm },
  list: { gap: spacing.md },
  actions: { flexDirection: 'row', gap: spacing.xs, marginTop: spacing.sm },
});
