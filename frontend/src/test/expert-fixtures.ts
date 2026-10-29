import { makeForecastTask } from './forecast-fixtures';

export function makeExpertTask() {
  const task = makeForecastTask();
  const metrics = { status: 'succeeded' as const, model_calls: 1, tool_calls: 0, usage: null,
    actual_model: 'controlled-test', elapsed_ms: 1, failure_code: null };
  const advice = (role: 'comfort' | 'energy', id: string) => ({ role, outcome: 'recommend' as const,
    preferred_candidate_id: id, evidence_refs: ['goal', `candidate:${id}`],
    public_summary: role === 'comfort' ? '推荐更早观测达标的候选。' : '推荐按期达标且范围能耗更低的候选。' });
  const role_runs = [
    { ...metrics, role: 'coordinator_goal' as const, advice: null },
    { ...metrics, role: 'comfort' as const, advice: advice('comfort', 'c2') },
    { ...metrics, role: 'energy' as const, advice: advice('energy', 'c1') },
    { ...metrics, role: 'coordinator_plan' as const, advice: null },
  ];
  return { ...task, mode: 'multi_agent' as const,
    request: { ...task.request, strategy: 'expert_forecast' as const },
    agent_run: { ...task.agent_run, strategy: 'expert_forecast' as const, pipeline_version: 'd3-experts-v1',
      role_runs, model_calls: 4, tool_calls: 0, actual_model: 'controlled-test',
      rounds: [{ turn: 0, model_calls: 4, tool_calls: 0, usage: null, elapsed_ms: 4,
        roles: role_runs.map((record) => ({ ...metrics, role: record.role })) }] },
  };
}
