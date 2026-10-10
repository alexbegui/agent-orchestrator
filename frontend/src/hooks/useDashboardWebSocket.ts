import { useEffect, useRef, useState } from 'react';

/**
 * Canal global de eventos do painel.
 *
 * O backend sempre teve o /ws/dashboard; o frontend nunca escutou e fazia
 * polling de 20s. Resultado: o card demorava até 20 segundos para mostrar
 * que o agente terminou. Com o canal ligado, muda na hora.
 */
export function useDashboardWebSocket(onChange: () => void) {
  const [connected, setConnected] = useState(false);
  const onChangeRef = useRef(onChange);
  const debounceRef = useRef<number | null>(null);

  // Guarda a última versão do callback sem reconectar o socket a cada render.
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let fechadoDeProposito = false;
    let tentativas = 0;

    const conectar = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${protocol}//${window.location.host}/ws/dashboard`);

      ws.onopen = () => {
        tentativas = 0;
        setConnected(true);
      };

      ws.onmessage = () => {
        // Vários agentes podem terminar quase juntos: agrupa as recargas
        // para não disparar uma requisição por evento.
        if (debounceRef.current) window.clearTimeout(debounceRef.current);
        debounceRef.current = window.setTimeout(() => onChangeRef.current(), 250);
      };

      ws.onclose = () => {
        setConnected(false);
        if (fechadoDeProposito) return;
        // O servidor reinicia com frequência durante o desenvolvimento;
        // reconectar com espera crescente evita martelar a porta.
        tentativas += 1;
        const espera = Math.min(1000 * 2 ** (tentativas - 1), 15000);
        reconnectTimer = window.setTimeout(conectar, espera);
      };

      ws.onerror = () => ws?.close();
    };

    conectar();

    return () => {
      fechadoDeProposito = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
      ws?.close();
    };
  }, []);

  return { connected };
}
