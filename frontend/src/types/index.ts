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
}

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
