import { useLocalSearchParams } from 'expo-router';

import { useEvidence } from '@/api/hooks';
import { EvidenceView } from '@/components/evidence';
import { QueryState, Screen } from '@/components/Screen';

export default function EvidenceScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const evidence = useEvidence(id);
  return (
    <Screen>
      <QueryState query={evidence}>{() => <EvidenceView evidence={evidence.data!} />}</QueryState>
    </Screen>
  );
}
