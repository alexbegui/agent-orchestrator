import { useState, useEffect, useRef } from 'react';

interface WebSocketMessage {
  type: 'LOG' | 'STATUS' | 'ERROR';
  content?: string;
  status?: string;
}

export function useTaskWebSocket(taskId: string | null) {
  const [logs, setLogs] = useState<string[]>([]);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!taskId) {
      setLogs([]);
      setTaskStatus(null);
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/tasks/${taskId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data);
        if (msg.type === 'LOG' && msg.content) {
          setLogs((prev) => [...prev, msg.content!]);
        } else if (msg.type === 'STATUS' && msg.status) {
          setTaskStatus(msg.status);
        }
      } catch (err) {
        console.error('Failed to parse WS message', err);
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [taskId]);

  return { logs, taskStatus };
}
