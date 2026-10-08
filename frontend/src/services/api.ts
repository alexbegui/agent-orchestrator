import { Project, Task, Message } from '../types';

const BASE_URL = '/api';

export const api = {
  // Projects
  async getProjects(): Promise<Project[]> {
    const res = await fetch(`${BASE_URL}/projects`);
    return res.json();
  },

  async createProject(name: string, root_path: string, default_branch = 'main'): Promise<Project> {
    const res = await fetch(`${BASE_URL}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, root_path, default_branch }),
    });
    return res.json();
  },

  // Tasks
  async getTasks(projectId: string): Promise<Task[]> {
    const res = await fetch(`${BASE_URL}/tasks/project/${projectId}`);
    return res.json();
  },

  async createTask(projectId: string, title: string, raw_prompt: string, runner_type = 'SUBPROCESS_CLI'): Promise<Task> {
    const res = await fetch(`${BASE_URL}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, title, raw_prompt, runner_type }),
    });
    return res.json();
  },

  async refineTask(taskId: string): Promise<Task> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/refine`, { method: 'POST' });
    return res.json();
  },

  async runTask(taskId: string): Promise<Task> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/run`, { method: 'POST' });
    return res.json();
  },

  async stopTask(taskId: string): Promise<{ stopped: boolean }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/stop`, { method: 'POST' });
    return res.json();
  },

  async getDiff(taskId: string): Promise<{ diff: string }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/diff`);
    return res.json();
  },

  async mergeTask(taskId: string): Promise<{ merged: boolean }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/merge`, { method: 'POST' });
    return res.json();
  },

  // Messages
  async getMessages(taskId: string): Promise<Message[]> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/messages`);
    return res.json();
  },

  async sendMessage(taskId: string, content: string): Promise<Message> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    return res.json();
  },
};
