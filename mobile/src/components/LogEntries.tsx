import { useQuery } from '@tanstack/react-query';

import { api } from '@/api';
import { Row, Section } from '@/components/list';
import { LogDraftCard } from '@/components/LogDraftCard';

const CLOSED = ['cancelled', 'undone'];

/** Every food and workout entry, so one stays reachable after its chat message scrolls away. */
export function LogEntries() {
  const query = useQuery({ queryKey: ['health-actions'], queryFn: api.getActions });

  if (query.isPending) {
    return (
      <Section>
        <Row title="Loading your entries…" />
      </Section>
    );
  }
  if (query.isError) {
    return (
      <Section>
        <Row
          icon="alert-circle-outline"
          title="Could not load your entries"
          detail="Tap to try again"
          onPress={() => query.refetch()}
        />
      </Section>
    );
  }
  if (!query.data.length) {
    return (
      <Section>
        <Row
          title="Nothing logged yet"
          detail="Tell Patterns what you ate or a workout you did, and it prepares an entry for you to check."
        />
      </Section>
    );
  }
  // Tapping an entry shows its actions in place. Cancelled and removed ones go last.
  const open = query.data.filter((entry) => !CLOSED.includes(entry.status));
  const closed = query.data.filter((entry) => CLOSED.includes(entry.status));
  return (
    <>
      {open.length > 0 && (
        <Section title="Drafts and logged">
          {open.map((entry) => (
            <LogDraftCard key={entry.id} id={entry.id} initial={entry} collapsible />
          ))}
        </Section>
      )}
      {closed.length > 0 && (
        <Section title="Cancelled and removed">
          {closed.map((entry) => (
            <LogDraftCard key={entry.id} id={entry.id} initial={entry} collapsible />
          ))}
        </Section>
      )}
    </>
  );
}
