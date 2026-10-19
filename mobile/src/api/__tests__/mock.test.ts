import { mockClient } from '../mock';

describe('mock API', () => {
  it('backs every finding with evidence included in the report', async () => {
    const report = await mockClient.getLatestReport();
    for (const finding of report.findings) {
      expect(finding.evidenceIds.length).toBeGreaterThan(0);
      for (const id of finding.evidenceIds) {
        expect(report.evidence[id]).toBeDefined();
      }
    }
  });

  it('only cites evidence that exists in chat answers', async () => {
    const report = await mockClient.getLatestReport();
    const [, answer] = await mockClient.sendMessage('Why is my sleep worse?');
    expect(answer.role).toBe('assistant');
    expect(answer.evidenceIds.length).toBeGreaterThan(0);
    for (const id of answer.evidenceIds) {
      expect(report.evidence[id]).toBeDefined();
    }
  });

  it('refuses medical questions without citing evidence', async () => {
    const [, answer] = await mockClient.sendMessage('Do I have sleep apnea?');
    expect(answer.refused).toBe(true);
    expect(answer.evidenceIds).toEqual([]);
  });

  it('keeps chat history across calls', async () => {
    const before = (await mockClient.getChat()).length;
    await mockClient.sendMessage('How are my steps?');
    expect(await mockClient.getChat()).toHaveLength(before + 2);
  });

  it('remembers reminder decisions', async () => {
    await mockClient.setReminderStatus('r_wind', 'active');
    const reminders = await mockClient.getReminders();
    expect(reminders.find((r) => r.id === 'r_wind')?.status).toBe('active');
  });

  it('remembers answers to context questions', async () => {
    await mockClient.answerQuestion('q_shift', 'Exams');
    const report = await mockClient.getLatestReport();
    expect(report.questions.find((q) => q.id === 'q_shift')?.answer).toBe('Exams');
  });

  it('returns copies so callers cannot change stored data', async () => {
    const first = await mockClient.getReminders();
    first[0].status = 'muted';
    const second = await mockClient.getReminders();
    expect(second[0].status).not.toBe('muted');
  });
});
