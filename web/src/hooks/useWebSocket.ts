/**
 * WebSocket hook for real-time updates
 */

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAppStore } from '../store/appStore';
import { messageKeys } from './useMessages';
import { statsKeys } from './useStats';
import { useNotifications } from './useNotifications';
import { useToastStore } from './useToast';
import { withWsToken } from '../api/token';
import type { WebSocketMessage } from '../api/types';

// Human-readable labels for action tags
const ACTION_LABELS: Record<string, { success: string; failure: string }> = {
  'add-contact': { success: 'Contact Added', failure: "Couldn't add contact" },
  'create-reminder': { success: 'Event Created', failure: "Couldn't create event" },
};

export function useWebSocket() {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();
  const { setSyncStatus } = useAppStore();
  const { showNewMessageNotification } = useNotifications();
  const addToast = useToastStore((state) => state.addToast);

  useEffect(() => {
    // Determine WebSocket URL based on current location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = withWsToken(`${protocol}//${host}/ws`);

    // Create WebSocket connection
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);

      // Subscribe to all topics
      ws.send(
        JSON.stringify({
          type: 'subscribe',
          topics: ['sync_events', 'classification_updates'],
        })
      );
    };

    ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        console.log('WebSocket message:', message);

        // Handle different message types
        switch (message.type) {
          case 'sync_started':
            setSyncStatus('syncing');
            break;

          case 'sync_completed':
            setSyncStatus('idle');
            // Invalidate queries to refresh data
            queryClient.invalidateQueries({ queryKey: messageKeys.lists() });
            queryClient.invalidateQueries({ queryKey: statsKeys.stats });
            queryClient.invalidateQueries({ queryKey: statsKeys.tags });
            queryClient.invalidateQueries({ queryKey: statsKeys.unreadCount });
            queryClient.invalidateQueries({ queryKey: statsKeys.draftCount });
            break;

          case 'message_classified':
            // Invalidate specific message
            if (message.message_id) {
              queryClient.invalidateQueries({
                queryKey: messageKeys.detail(message.message_id),
              });
            }
            queryClient.invalidateQueries({ queryKey: messageKeys.lists() });
            break;

          case 'messages_updated':
            // Another client updated messages (read status, tags, etc.)
            console.log('Messages updated by another client:', message.message_ids, message.action);
            // Invalidate the specific messages and lists
            if (message.message_ids && Array.isArray(message.message_ids)) {
              message.message_ids.forEach((id: string) => {
                queryClient.invalidateQueries({
                  queryKey: messageKeys.detail(id),
                });
              });
            }
            queryClient.invalidateQueries({ queryKey: messageKeys.lists() });
            queryClient.invalidateQueries({ queryKey: statsKeys.tags });
            // Update unread count when read status changes
            queryClient.invalidateQueries({ queryKey: statsKeys.unreadCount });
            break;

          case 'messages_deleted':
            // Another client deleted/trashed messages
            console.log('Messages deleted by another client:', message.message_ids, message.permanent ? '(permanent)' : '(to trash)');
            // Invalidate lists and stats
            queryClient.invalidateQueries({ queryKey: messageKeys.lists() });
            queryClient.invalidateQueries({ queryKey: statsKeys.tags });
            queryClient.invalidateQueries({ queryKey: statsKeys.stats });
            queryClient.invalidateQueries({ queryKey: statsKeys.unreadCount });
            break;

          case 'messages_restored':
            // Another client restored messages from trash
            console.log('Messages restored by another client:', message.message_ids);
            // Invalidate lists
            queryClient.invalidateQueries({ queryKey: messageKeys.lists() });
            queryClient.invalidateQueries({ queryKey: statsKeys.unreadCount });
            break;

          case 'error':
            setSyncStatus('error');
            console.error('WebSocket error:', message.message);
            break;

          case 'action_completed': {
            const actionName = message.action_name || 'unknown';
            const labels = ACTION_LABELS[actionName] || {
              success: `Action "${actionName}" completed`,
              failure: `Action "${actionName}" failed`,
            };

            if (message.status === 'success') {
              addToast({ message: labels.success, severity: 'success' });
            } else if (message.status === 'failed') {
              addToast({ message: labels.failure, severity: 'error' });
            }
            // Skip 'skipped' status — no toast needed
            break;
          }

          case 'new_messages':
            // Show browser notification for new messages
            if (message.messages && Array.isArray(message.messages)) {
              showNewMessageNotification(message.messages);
            }
            break;
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
    };

    // Cleanup on unmount
    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [queryClient, setSyncStatus, showNewMessageNotification, addToast]);

  const sendMessage = (message: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  };

  return {
    isConnected,
    sendMessage,
  };
}
