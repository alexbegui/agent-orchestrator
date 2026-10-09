import { useState, useEffect, useRef } from 'react';
import { Message } from '../types';

interface WebSocketPayload {
  type: 'LOG' | 'STATUS' | 'ERROR' | 'MESSAGE';
  content?: string;
  status?: string;
  message?: Message;
}

export function useTaskWebSocket(taskId: string | null, onNewMessage?: (msg: Message) => void) {
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
        const payload: WebSocketPayload = JSON.parse(event.data);
        if (payload.type === 'LOG' && payload.content) {
          setLogs((prev) => [...prev, payload.content!]);
        } else if (payload.type === 'STATUS' && payload.status) {
          setTaskStatus(payload.status);
        } else if (payload.type === 'MESSAGE' && payload.message) {
          if (onNewMessage) {
            onNewMessage(payload.message);
          }
        }
      } catch (err) {
        console.error('Failed to parse WS message', err);
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [taskId, onNewMessage]);

  return { logs, taskStatus };
}
