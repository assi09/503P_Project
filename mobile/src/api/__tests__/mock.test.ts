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

  it('serves every cited evidence by id', async () => {
    const report = await mockClient.getLatestReport();
    for (const id of Object.keys(report.evidence)) {
      expect(await mockClient.getEvidence(id)).toEqual(report.evidence[id]);
    }
    await expect(mockClient.getEvidence('missing')).rejects.toThrow();
  });

  it('refuses medical questions without citing evidence', async () => {
    const [, answer] = await mockClient.sendMessage('Do I have sleep apnea?');
    expect(answer.refused).toBe(true);
    expect(answer.evidenceIds).toEqual([]);
  });

  it('records which finding a question was about', async () => {
    const [question, answer] = await mockClient.sendMessage('Tell me more', 'f_eff');
    expect(question.findingId).toBe('f_eff');
    expect(answer.evidenceIds).toContain('ev_eff');
  });

  it('answers about the attached finding rather than keywords in the question', async () => {
    const [, steps] = await mockClient.sendMessage('Why did this happen?', 'f_steps');
    expect(steps.evidenceIds).toEqual(['ev_steps']);
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

  it('saves notification settings and rejects invalid limits', async () => {
    const saved = await mockClient.updateNotificationSettings({ quietHours: null, maxPerDay: 3 });
    expect(saved).toEqual({ quietHours: null, maxPerDay: 3 });
    expect(await mockClient.getNotificationSettings()).toEqual(saved);
    await expect(
      mockClient.updateNotificationSettings({ quietHours: null, maxPerDay: 0 }),
    ).rejects.toThrow('between 1 and 5');
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
