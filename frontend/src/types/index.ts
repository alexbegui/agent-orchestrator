export type TaskStatus = 
  | 'DRAFT' 
  | 'SPEC_READY' 
  | 'QUEUED' 
  | 'RUNNING' 
  | 'REVIEW_READY' 
  | 'DONE' 
  | 'FAILED';

export type RunnerType = 'SUBPROCESS_CLI' | 'DIRECT_API';

export interface Project {
  id: string;
  name: string;
  root_path: string;
  default_branch: string;
  active_tasks_count: number;
}

export interface Task {
  id: string;
  project_id: string;
  title: string;
  raw_prompt: string;
  refined_spec?: string;
  status: TaskStatus;
  runner_type: RunnerType;
  runner_config: Record<string, any>;
  worktree_path?: string;
  git_branch?: string;
  /** Derivado no backend: a bola está com você (agente falou por último, diff pronto ou falha). */
  awaiting_you?: boolean;
  /** Preenchido para a visão "Todos os projetos". */
  project_name?: string;
  /** O processo do agente existe neste momento (apurado, não lido do banco). */
  is_alive?: boolean;
  /** Marcada como rodando, mas o processo não existe mais. */
  stalled?: boolean;
  /** Epoch em segundos de quando a execução começou. */
  started_at?: number;
  /** Estado único e explícito, escrito no card. */
  card_state?: CardState;
  changed_files?: number;
  lines_added?: number;
  lines_removed?: number;
}

export type CardState =
  | 'EXECUTANDO'
  | 'TE_PERGUNTOU'
  | 'ENTREGOU'
  | 'PAROU'
  | 'CONCLUIDO'
  | 'NA_FILA';

/** `null` em activeProjectId significa "Todos os projetos". */
export const ALL_PROJECTS = null;

export interface Attachment {
  filename: string;
  original_name: string;
  file_path: string;
  file_url: string;
  content_type: string;
  size: number;
}

export interface Message {
  id: string;
  task_id: string;
  role: 'USER' | 'ASSISTANT' | 'SYSTEM';
  content: string;
  attachments?: Attachment[];
  created_at?: string;
}
