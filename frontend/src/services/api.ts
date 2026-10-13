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

  /** Todas as tarefas de todos os projetos — a visão cross-projeto. */
  async getAllTasks(): Promise<Task[]> {
    const res = await fetch(`${BASE_URL}/tasks/all`);
    return handleResponse<Task[]>(res);
  },

  /** Importa várias conversas do Antigravity de uma vez. Lista vazia = todas as pendentes. */
  async importAntigravityBulk(
    projectId: string,
    conversationIds?: string[]
  ): Promise<{ imported: number; skipped: number; failed: { conversation_id: string; error: string }[]; task_ids: string[] }> {
    const res = await fetch(`${BASE_URL}/tasks/import-antigravity-bulk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, conversation_ids: conversationIds }),
    });
    return handleResponse(res);
  },

  /** Artefatos visíveis desta tarefa (worktree enquanto aberta, projeto depois do merge). */
  async getTaskArtifacts(taskId: string): Promise<{
    base: string | null;
    artifacts: {
      name: string;
      kind: 'markdown' | 'html' | 'mermaid' | 'other';
      category: 'documento' | 'mockup' | 'diagrama' | 'imagem' | 'dados' | 'outro';
      preview: string;
      size: number;
      modified_at: number;
      path: string;
      outside_task?: boolean;
      /** Caminho a partir da raiz do projeto — é por ele que a leitura acha
       *  o arquivo. `name` é só o rótulo curto mostrado na tela. */
      rel_path?: string | null;
    }[];
  }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/artifacts`);
    return handleResponse(res);
  },

  /** Linhas de conhecimento que o agente propôs registrar nesta tarefa. */
  async getKnowledgeProposals(taskId: string): Promise<{ proposals: string[] }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/knowledge-proposals`);
    return handleResponse(res);
  },

  /** Aprova as linhas escolhidas. Lista vazia descarta tudo. */
  async approveKnowledge(taskId: string, lines: string[]): Promise<{ registered: number }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/knowledge-proposals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines }),
    });
    return handleResponse(res);
  },

  /**
   * O artefato mora em subpasta (`docs/mapa.md`), então as barras precisam
   * chegar ao servidor como barras — é o que o conversor `{nome:path}` casa.
   * Codificar o caminho inteiro transformaria `/` em `%2F`; codificamos
   * segmento a segmento, o que ainda protege espaço, `#` e `?`.
   */
  artifactPath(nome: string): string {
    return nome.split('/').map(encodeURIComponent).join('/');
  },

  /** URL servida pelo backend — o navegador bloqueia file:// vindo de http. */
  artifactUrl(taskId: string, nome: string): string {
    return `${BASE_URL}/tasks/${taskId}/artifacts/${this.artifactPath(nome)}/raw`;
  },

  async readTaskArtifact(taskId: string, nome: string): Promise<{ name: string; content: string }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/artifacts/${this.artifactPath(nome)}`);
    return handleResponse(res);
  },

  /** Confere todos os agentes neste instante e corrige estados errados. */
  async refreshStates(): Promise<{
    checked: number;
    fixed: { id: string; title: string; novo_status: string }[];
    tasks: Task[];
  }> {
    const res = await fetch(`${BASE_URL}/tasks/refresh-states`, { method: 'POST' });
    return handleResponse(res);
  },

  /** Abre um terminal nativo na pasta do projeto. */
  async openProjectTerminal(projectId: string): Promise<{ opened_at: string }> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/terminal`, { method: 'POST' });
    return handleResponse<{ opened_at: string }>(res);
  },

  /** Abre um terminal no worktree da tarefa (ou na pasta do projeto, se ainda não houver). */
  async openTaskTerminal(taskId: string): Promise<{ opened_at: string }> {
    const res = await fetch(`${BASE_URL}/tasks/${taskId}/terminal`, { method: 'POST' });
    return handleResponse<{ opened_at: string }>(res);
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



