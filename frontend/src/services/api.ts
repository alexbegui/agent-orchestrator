import { Project, Task, Message, Attachment } from '../types';

const BASE_URL = '/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errDetail = 'Erro na requisição';
    try {
      const errJson = await res.json();
      if (errJson && errJson.detail) {
        errDetail = errJson.detail;
      }
    } catch (_) {}
    throw new Error(errDetail);
  }
  return res.json();
}

export const api = {
  // Projects
  async getProjects(): Promise<Project[]> {
    const res = await fetch(`${BASE_URL}/projects`);
    return handleResponse<Project[]>(res);
  },

  async createProject(name: string, root_path: string, default_branch = 'main'): Promise<Project> {
    const res = await fetch(`${BASE_URL}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, root_path, default_branch }),
    });
    return handleResponse<Project>(res);
  },

  async updateProject(id: string, data: { name?: string; default_branch?: string }): Promise<Project> {
    const res = await fetch(`${BASE_URL}/projects/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return handleResponse<Project>(res);
  },

  // Tasks
  async getTasks(projectId: string): Promise<Task[]> {
    const res = await fetch(`${BASE_URL}/tasks/project/${projectId}`);
    return handleResponse<Task[]>(res);
  },

  async createTask(
    projectId: string,
    title: string,
    raw_prompt: string,
    runner_type = 'SUBPROCESS_CLI',
    runner_config: Record<string, any> = {}
  ): Promise<Task> {
    const res = await fetch(`${BASE_URL}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, title, raw_prompt, runner_type, runner_config }),
    });
    return handleResponse<Task>(res);
  },

  async refineTask(taskId: string): Promise<Task> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/refine`, { method: 'POST' });
    return handleResponse<Task>(res);
  },

  async runTask(taskId: string): Promise<Task> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/run`, { method: 'POST' });
    return handleResponse<Task>(res);
  },

  async stopTask(taskId: string): Promise<{ stopped: boolean; status: string }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/stop`, { method: 'POST' });
    return handleResponse<{ stopped: boolean; status: string }>(res);
  },

  async getDiff(taskId: string): Promise<{ diff: string }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/diff`);
    return handleResponse<{ diff: string }>(res);
  },

  async mergeTask(taskId: string): Promise<{ merged: boolean; status: string }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/merge`, { method: 'POST' });
    return handleResponse<{ merged: boolean; status: string }>(res);
  },

  async deleteTask(taskId: string): Promise<{ deleted: boolean; task_id: string; antigravity_cleaned: boolean }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}`, { method: 'DELETE' });
    return handleResponse<{ deleted: boolean; task_id: string; antigravity_cleaned: boolean }>(res);
  },

  // Messages
  async getMessages(taskId: string): Promise<Message[]> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/messages`);
    return handleResponse<Message[]>(res);
  },

  async sendMessage(taskId: string, content: string, attachments?: Attachment[], auto_run = true): Promise<Message> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, auto_run, attachments }),
    });
    return handleResponse<Message>(res);
  },

  async uploadTaskFile(taskId: string, file: File): Promise<Attachment> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/upload`, {
      method: 'POST',
      body: formData,
    });
    return handleResponse<Attachment>(res);
  },

  // Settings & IA Keys
  async getSettings(): Promise<{
    has_gemini_key: boolean;
    has_anthropic_key: boolean;
    has_antigravity?: boolean;
    antigravity_status?: string;
    gemini_key_preview?: string;
    anthropic_key_preview?: string;
  }> {
    const res = await fetch(`${BASE_URL}/settings`);
    return handleResponse(res);
  },

  async updateSettings(data: { gemini_api_key?: string; anthropic_api_key?: string }): Promise<{ has_gemini_key: boolean; has_anthropic_key: boolean }> {
    const res = await fetch(`${BASE_URL}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  // Antigravity Conversations
  async getAntigravityConversations(projectId?: string): Promise<{
    conversation_id: string;
    title: string;
    preview: string;
    step_count: number;
    last_modified: string;
    workspace: string;
    status: string;
    already_imported: boolean;
  }[]> {
    const url = projectId
      ? `${BASE_URL}/tasks/antigravity/conversations?project_id=${projectId}`
      : `${BASE_URL}/tasks/antigravity/conversations`;
    const res = await fetch(url);
    return handleResponse(res);
  },

  async importAntigravityConversation(data: {
    project_id: string;
    conversation_id: string;
    title?: string;
  }): Promise<Task> {
    const res = await fetch(`${BASE_URL}/tasks/import-antigravity`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return handleResponse<Task>(res);
  },

  async syncTaskAntigravity(taskId: string): Promise<{ synced: number; task_id: string; total_antigravity: number }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/sync-antigravity`, {
      method: 'POST',
    });
    return handleResponse(res);
  },

  async syncAntigravityConversation(conversationId: string): Promise<{ synced: number; task_id: string; total_antigravity: number }> {
    const res = await fetch(`${BASE_URL}/tasks/antigravity/${conversationId}/sync`, {
      method: 'POST',
    });
    return handleResponse(res);
  },

  async syncAllTasks(projectId?: string): Promise<{
    tasks_checked: number;
    tasks_updated: number;
    total_messages_synced: number;
    details: Array<{ task_id: string; title: string; synced: number }>;
  }> {
    const url = projectId
      ? `${BASE_URL}/tasks/sync-all?project_id=${projectId}`
      : `${BASE_URL}/tasks/sync-all`;
    const res = await fetch(url, { method: 'POST' });
    return handleResponse(res);
  },
};


