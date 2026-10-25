import { mockClient, routeQuestion } from '../mock';
import type { SendOptions } from '../types';

const AUTO: SendOptions = { expert: 'auto', depth: 'quick' };
const DEEP: SendOptions = { expert: 'auto', depth: 'deep' };

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
    const [, answer] = await mockClient.sendMessage('Why is my sleep worse?', DEEP);
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
    const [, answer] = await mockClient.sendMessage('Do I have sleep apnea?', AUTO);
    expect(answer.refused).toBe(true);
    expect(answer.evidenceIds).toEqual([]);
  });

  it('records which finding a question was about', async () => {
    const attachment = { kind: 'finding', id: 'f_eff' } as const;
    const [question, answer] = await mockClient.sendMessage('Tell me more', { ...AUTO, attachment });
    expect(question.attachment).toEqual(attachment);
    expect(answer.evidenceIds).toContain('ev_eff');
  });

  it('answers about the attached finding rather than keywords in the question', async () => {
    const [, steps] = await mockClient.sendMessage('Why did this happen?', {
      ...AUTO,
      attachment: { kind: 'finding', id: 'f_steps' },
    });
    expect(steps.evidenceIds).toEqual(['ev_steps']);
  });

  it('keeps chat history across calls', async () => {
    const before = (await mockClient.getChat()).length;
    await mockClient.sendMessage('How are my steps?', AUTO);
    expect(await mockClient.getChat()).toHaveLength(before + 2);
  });

  it('routes a question to the expert that owns its topic', async () => {
    const [, answer] = await mockClient.sendMessage('How is my HRV?', AUTO);
    expect(answer.answeredBy).toBe('recovery');
    expect(answer.routed).toBe(true);
  });

  it('lets a cross-domain question be led by one expert that consults the other', async () => {
    expect(routeQuestion('Did my late nights affect my recovery?')).toEqual(['recovery', 'sleep']);
    const [, deep] = await mockClient.sendMessage('Did my late nights affect my recovery?', DEEP);
    expect(deep.answeredBy).toBe('recovery');
    expect(deep.consulted).toEqual(['sleep']);
    const [, quick] = await mockClient.sendMessage('Did my late nights affect my recovery?', AUTO);
    expect(quick.consulted).toBeUndefined();
  });

  it('sends the question to the chosen expert without routing', async () => {
    const [, answer] = await mockClient.sendMessage('How is my sleep?', {
      expert: 'sleep',
      depth: 'quick',
    });
    expect(answer.answeredBy).toBe('sleep');
    expect(answer.routed).toBe(false);
  });

  it('has a chosen expert consult the owner when asked about other metrics', async () => {
    const [, answer] = await mockClient.sendMessage('How are my steps?', {
      expert: 'sleep',
      depth: 'quick',
    });
    expect(answer.answeredBy).toBe('sleep');
    expect(answer.consulted).toEqual(['activity']);
    expect(answer.evidenceIds).toEqual(['ev_steps']);
  });

  it('still refuses medical questions when an expert is chosen', async () => {
    const [, answer] = await mockClient.sendMessage('Do I have sleep apnea?', {
      expert: 'sleep',
      depth: 'deep',
    });
    expect(answer.refused).toBe(true);
    expect(answer.answeredBy).toBeUndefined();
  });

  it('cites less evidence in a quick answer than a deep one', async () => {
    const [, quick] = await mockClient.sendMessage('Why is my sleep worse?', AUTO);
    const [, deep] = await mockClient.sendMessage('Why is my sleep worse?', DEEP);
    expect(quick.evidenceIds.length).toBeLessThan(deep.evidenceIds.length);
  });

  it('routes by an attached metric', async () => {
    const [, answer] = await mockClient.sendMessage('What happened here?', {
      ...AUTO,
      attachment: { kind: 'metric', metric: 'resting_hr' },
    });
    expect(answer.answeredBy).toBe('recovery');
  });

  it('rejects the nutrition expert while it is unavailable', async () => {
    await expect(
      mockClient.sendMessage('How much protein do I eat?', { expert: 'nutrition', depth: 'quick' }),
    ).rejects.toThrow('not available');
  });

  it('answers questions without a topic generally', async () => {
    const [, answer] = await mockClient.sendMessage('Hello', AUTO);
    expect(answer.answeredBy).toBe('general');
    expect(answer.evidenceIds).toEqual([]);
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

describe('days', () => {
  it('serves the latest day with a usual range and two weeks for each metric', async () => {
    const day = await mockClient.getDay('latest');
    expect(day.date).toBe(day.last);
    expect(day.partial).toBe(true);
    const steps = day.metrics.find((m) => m.metric === 'steps')!;
    expect(steps.usual!.low).toBeLessThanOrEqual(steps.usual!.high);
    expect(steps.recent).toHaveLength(14);
    const earlier = await mockClient.getDay(day.first);
    expect(earlier.partial).toBe(false);
    expect(earlier.metrics[0].usual).toBeNull(); // nothing before the first day
    await expect(mockClient.getDay('2000-01-01')).rejects.toMatchObject({ status: 404 });
  });

  it('serves a metric for the days asked for, ending on the day asked for', async () => {
    const { last } = await mockClient.getDay('latest');
    const series = await mockClient.getMetricSeries('resting_hr', { days: 7 });
    expect(series.points).toHaveLength(7);
    expect(series.points.at(-1)!.date).toBe(last);
    await expect(mockClient.getMetricSeries('made_up', { days: 7 })).rejects.toMatchObject({
      status: 404,
    });
  });
});
