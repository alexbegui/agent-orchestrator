import { Project, Task, Message } from '../types';

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

  // Messages
  async getMessages(taskId: string): Promise<Message[]> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/messages`);
    return handleResponse<Message[]>(res);
  },

  async sendMessage(taskId: string, content: string, auto_run = true): Promise<Message> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, auto_run }),
    });
    return handleResponse<Message>(res);
  },
};
