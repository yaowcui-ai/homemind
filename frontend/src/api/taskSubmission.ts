import { ApiError, isObject, isText } from './client';
import { tasksApi } from './tasks';
import type { AdvanceRequest, AgentRequest, ConfirmRequest, ReplyRequest, RuleRequest, TaskDetail } from './tasks.types';

export type PendingOperation =
  | { kind: 'rule'; key: string; body: RuleRequest }
  | { kind: 'agent'; key: string; body: AgentRequest }
  | { kind: 'reply'; key: string; taskId: string; body: ReplyRequest }
  | { kind: 'confirm'; key: string; taskId: string; body: ConfirmRequest }
  | { kind: 'advance'; key: string; taskId: string; body: AdvanceRequest };
export interface AgentDraft { text: string; keep_entity_ids: string[]; protected_room_ids: string[] }
export interface TaskSessionState {
  selectedId: string | null; pending: PendingOperation | null; busy: boolean; restorePending: boolean;
  agentDraft: AgentDraft; ruleDraft: Partial<RuleRequest> | null;
}
const emptyState = (): TaskSessionState => ({ selectedId: null, pending: null, busy: false, restorePending: false,
  agentDraft: { text: '', keep_entity_ids: [], protected_room_ids: [] }, ruleDraft: null });
const ids = (v: unknown) => v === undefined || (Array.isArray(v) && v.every(isText));
function validPending(v: unknown): v is PendingOperation {
  if (!isObject(v) || !isText(v.key) || !/^[A-Za-z0-9._:-]{8,128}$/.test(v.key) || !isObject(v.body)) return false;
  const b = v.body;
  if (v.kind === 'rule') return ['homecoming', 'sleep', 'away'].includes(String(b.scenario))
    && Array.isArray(b.room_ids) && b.room_ids.every(isText) && ids(b.keep_entity_ids) && ids(b.protected_room_ids)
    && (b.expected_world_id === undefined || isText(b.expected_world_id));
  if (v.kind === 'agent') return isText(b.text) && b.text.length <= 2000 && isText(b.expected_world_id) && ids(b.keep_entity_ids) && ids(b.protected_room_ids);
  if (v.kind === 'advance') return isText(v.taskId) && isText(b.expected_world_id) && Number.isSafeInteger(b.expected_simulated_minutes) && Number(b.expected_simulated_minutes) >= 0;
  if (!isText(v.taskId) || !Number.isInteger(b.expected_turn) || Number(b.expected_turn) < 0 || Number(b.expected_turn) > 3) return false;
  return v.kind === 'confirm' || (v.kind === 'reply' && isText(b.text) && b.text.length <= 2000);
}
function fingerprint(operation: Omit<PendingOperation, 'key'>) {
  // Sort recursively: property insertion order must not change an intent's retry identity.
  return JSON.stringify(operation, (_key, value) => isObject(value)
    ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, value[key]])) : value);
}

/** Only task locators and public user input are saved; cookies/CSRF remain in the client. */
export class TaskSubmission {
  private state = emptyState();
  private listeners = new Set<() => void>();
  private storageKey: string | null;
  private selectionVersion = 0;
  private writeEpoch = 0;
  constructor(homeId?: string) {
    this.storageKey = homeId ? `homemind.tasks.v1:${homeId}` : null;
    if (!this.storageKey) return;
    try {
      const raw = window.sessionStorage.getItem(this.storageKey);
      if (!raw || raw.length > 100000) return;
      const saved: unknown = JSON.parse(raw);
      if (!isObject(saved) || saved.version !== 1) return;
      this.state.restorePending = true;
      if (isText(saved.selectedId)) this.state.selectedId = saved.selectedId;
      if (validPending(saved.pending)) this.state.pending = saved.pending;
      if (isObject(saved.agentDraft) && typeof saved.agentDraft.text === 'string' && saved.agentDraft.text.length <= 2000
        && Array.isArray(saved.agentDraft.keep_entity_ids) && saved.agentDraft.keep_entity_ids.every(isText)
        && Array.isArray(saved.agentDraft.protected_room_ids) && saved.agentDraft.protected_room_ids.every(isText)) {
        this.state.agentDraft = saved.agentDraft as unknown as AgentDraft;
      }
      if (isObject(saved.ruleDraft) && ['homecoming', 'sleep', 'away'].includes(String(saved.ruleDraft.scenario))
        && ids(saved.ruleDraft.room_ids) && ids(saved.ruleDraft.keep_entity_ids) && ids(saved.ruleDraft.protected_room_ids)) {
        this.state.ruleDraft = saved.ruleDraft as Partial<RuleRequest>;
      }
    } catch { /* Storage may be disabled or contain obsolete data; keep an isolated memory session. */ }
  }
  getSnapshot = () => this.state;
  getWriteEpoch = () => this.writeEpoch;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(patch: Partial<TaskSessionState>) {
    this.state = { ...this.state, ...patch };
    try {
      if (this.storageKey) window.sessionStorage.setItem(this.storageKey, JSON.stringify({ ...this.state, version: 1, busy: undefined, restorePending: undefined }));
    } catch { /* The current tab still retains the original key if persistent storage is unavailable. */ }
    this.listeners.forEach((listener) => listener());
  }
  select(id: string) { this.selectionVersion += 1; this.update({ selectedId: id }); }
  saveAgentDraft(draft: AgentDraft) { this.update({ agentDraft: draft }); }
  saveRuleDraft(draft: Partial<RuleRequest>) { this.update({ ruleDraft: draft }); }
  beginNew() {
    if (this.state.busy) return;
    this.update({ pending: null, agentDraft: emptyState().agentDraft, ruleDraft: null });
  }
  submit(body: RuleRequest) { return this.start({ kind: 'rule', body }); }
  submitAgent(body: AgentRequest) { return this.start({ kind: 'agent', body }); }
  reply(taskId: string, body: ReplyRequest) { return this.start({ kind: 'reply', taskId, body }); }
  confirm(taskId: string, body: ConfirmRequest) { return this.start({ kind: 'confirm', taskId, body }); }
  verify(taskId: string) { return this.runTaskAction(() => tasksApi.verify(taskId)); }
  advance(taskId: string, body: AdvanceRequest) { return this.start({ kind: 'advance', taskId, body }); }
  private async runTaskAction(action: () => Promise<TaskDetail>): Promise<TaskDetail> {
    if (this.state.busy) throw new Error('正在处理任务，请先等待结果并读取当前状态。');
    this.writeEpoch += 1;
    this.update({ busy: true });
    try { return await action(); }
    finally { this.update({ busy: false }); }
  }
  private start(operation: Omit<PendingOperation, 'key'> & { taskId?: string }): Promise<TaskDetail> {
    const current = this.state.pending;
    if (current) {
      const prior = { kind: current.kind, body: current.body, ...('taskId' in current ? { taskId: current.taskId } : {}) };
      if (fingerprint(prior) !== fingerprint(operation)) return Promise.reject(new Error('原提交结果尚未确认，请先读取原任务、同键重试，或明确开始新任务。'));
      return this.send(current);
    }
    // Deep-copy before the asynchronous request; later form/world updates cannot alter a retry.
    const pending = JSON.parse(JSON.stringify({ ...operation, key: crypto.randomUUID() })) as PendingOperation;
    return this.send(pending);
  }
  retryPending(): Promise<TaskDetail> {
    return this.state.pending ? this.send(this.state.pending) : Promise.reject(new Error('没有待确认的原提交，请开始新任务。'));
  }
  private async send(operation: PendingOperation): Promise<TaskDetail> {
    if (this.state.busy) throw new Error('正在处理原提交，请等待结果后读取。');
    this.writeEpoch += 1;
    const selectedVersion = this.selectionVersion;
    this.update({ pending: operation, busy: true, restorePending: false, ...('taskId' in operation ? { selectedId: operation.taskId } : {}) });
    try {
      let task: TaskDetail;
      switch (operation.kind) {
        case 'rule': task = await tasksApi.create(operation.body, operation.key); break;
        case 'agent': task = await tasksApi.createAgent(operation.body, operation.key); break;
        case 'reply': task = await tasksApi.reply(operation.taskId, operation.body, operation.key); break;
        case 'confirm': task = await tasksApi.confirm(operation.taskId, operation.body, operation.key); break;
        case 'advance': task = await tasksApi.advance(operation.taskId, operation.body, operation.key); break;
      }
      this.update({ pending: null, ...(this.selectionVersion === selectedVersion ? { selectedId: task.id } : {}) });
      return task;
    } catch (error) {
      // An explicit rejection has a known result. Transport/invalid-response failures remain unknown.
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) this.update({ pending: null });
      throw error;
    } finally { this.update({ busy: false }); }
  }
  async recover(): Promise<TaskDetail | null> {
    if (this.state.busy) return null;
    // A new controller may auto-read once after refresh/login. Later navigation must
    // preserve a new unknown submission until the user explicitly reads or retries it.
    this.update({ restorePending: false });
    const selectedVersion = this.selectionVersion;
    const writeEpoch = this.writeEpoch;
    const pending = this.state.pending;
    const selected = this.state.selectedId;
    let id = selected;
    if (pending && (pending.kind === 'rule' || pending.kind === 'agent')) {
      id = (await tasksApi.list(pending.key))[0]?.id ?? null;
      if (!id) return null;
    } else if (pending) id = pending.taskId;
    if (!id) return null;
    const task = await tasksApi.get(id);
    if (this.state.busy || this.state.pending !== pending || this.writeEpoch !== writeEpoch) return null;
    let unresolved = false;
    if (pending?.kind === 'reply') unresolved = task.mode === 'single_agent' && task.status === 'waiting_input' && task.agent_run.turn === pending.body.expected_turn;
    if (pending?.kind === 'confirm') unresolved = task.mode === 'single_agent' && task.status === 'waiting_confirmation' && task.agent_run.turn === pending.body.expected_turn;
    if (pending?.kind === 'advance') unresolved = !(task.advance_records ?? []).some((record) => record.key === pending.key
      && record.request.expected_world_id === pending.body.expected_world_id
      && record.request.expected_simulated_minutes === pending.body.expected_simulated_minutes);
    this.update({ pending: unresolved ? pending : null, ...(this.selectionVersion === selectedVersion ? { selectedId: task.id } : {}) });
    return task;
  }
}
