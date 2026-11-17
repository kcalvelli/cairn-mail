/**
 * MessageList component - List of messages
 */

import {
  Box,
  Typography,
  CircularProgress,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Pagination,
  Stack,
  IconButton,
  Tooltip,
  useTheme,
} from '@mui/material';
import { InboxOutlined, DeleteSweep, CheckBox, WifiOff, Refresh, CloudOff, ViewSidebar, ViewStream } from '@mui/icons-material';
import { useState, useEffect } from 'react';
import { MessageCard } from './MessageCard';
import { SwipeableMessageList } from './SwipeableMessageCard';
import { BulkActionBar } from './BulkActionBar';
import { ReadingPane } from './ReadingPane';
import { useOnlineStatus } from '../hooks/useOnlineStatus';
import { useIsMobile, useIsTouchDevice } from '../hooks/useIsMobile';
import {
  useMessages,
  useBulkDelete,
  useBulkMarkRead,
  useBulkRestore,
  useBulkPermanentDelete,
  useClearTrash,
  useMarkRead,
} from '../hooks/useMessages';
import { useAppStore } from '../store/appStore';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useToast } from '../hooks/useToast';
import { replyUrl } from '../utils/composeUrl';

export function MessageList() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isMobile = useIsMobile();
  const isTouchDevice = useIsTouchDevice();
  const {
    selectedAccount,
    selectedTags,
    searchQuery,
    isUnreadOnly,
    selectedMessageIds,
    clearSelection,
    selectAllMessages,
    selectionMode,
    exitSelectionMode,
    setSelectedMessageId,
    layoutMode,
    toggleLayoutMode,
  } = useAppStore();
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  const bulkDelete = useBulkDelete();
  const bulkMarkRead = useBulkMarkRead();
  const bulkRestore = useBulkRestore();
  const bulkPermanentDelete = useBulkPermanentDelete();
  const clearTrash = useClearTrash();
  const markReadMutation = useMarkRead();
  const toast = useToast();

  const [clearTrashDialogOpen, setClearTrashDialogOpen] = useState(false);
  const [permanentDeleteDialogOpen, setPermanentDeleteDialogOpen] = useState(false);
  const [page, setPage] = useState(1);

  // Get folder from URL query params (default to inbox)
  const folder = searchParams.get('folder') || 'inbox';
  const isTrash = folder === 'trash';

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [selectedAccount, selectedTags, isUnreadOnly, searchQuery, folder]);

  // Build filters
  const ITEMS_PER_PAGE = 50;
  const filters: any = {
    limit: ITEMS_PER_PAGE,
    offset: (page - 1) * ITEMS_PER_PAGE,
    folder: folder,
  };

  if (selectedAccount) {
    filters.account_id = selectedAccount;
  }

  if (selectedTags.length > 0) {
    // Pass all selected tags (backend uses OR logic - matches any tag)
    filters.tags = selectedTags;
  }

  if (isUnreadOnly) {
    filters.is_unread = true;
  }

  if (searchQuery) {
    filters.search = searchQuery;
  }

  // Check online status
  const isOnline = useOnlineStatus();

  // Fetch messages
  const { data, isLoading, error, dataUpdatedAt } = useMessages(filters);

  // Determine if we're showing cached data while offline
  const isShowingCachedData = !isOnline && data && !isLoading && dataUpdatedAt > 0;

  // Handle edge case: if current page is empty but there are still messages,
  // go back to the previous page (e.g., after deleting all messages on last page)
  useEffect(() => {
    if (
      !isLoading &&
      data &&
      data.messages.length === 0 &&
      data.total > 0 &&
      page > 1
    ) {
      // Calculate the correct page to go to
      const maxPage = Math.ceil(data.total / ITEMS_PER_PAGE);
      setPage(Math.min(page - 1, maxPage));
    }
  }, [data, isLoading, page]);

  // Bulk operation handlers
  const handleBulkDelete = () => {
    const messageIds = Array.from(selectedMessageIds);
    if (messageIds.length === 0) return;

    bulkDelete.mutate(messageIds, {
      onSuccess: () => {
        exitSelectionMode();
        toast.success(
          `Moved ${messageIds.length} ${messageIds.length === 1 ? 'message' : 'messages'} to trash`,
          {
            label: 'Undo',
            onClick: () => {
              bulkRestore.mutate(messageIds);
            },
          }
        );
      },
    });
  };

  const handleBulkMarkRead = () => {
    const messageIds = Array.from(selectedMessageIds);
    if (messageIds.length === 0) return;

    bulkMarkRead.mutate(
      { messageIds, isUnread: false },
      {
        onSuccess: () => {
          exitSelectionMode();
          toast.success(
            `Marked ${messageIds.length} ${messageIds.length === 1 ? 'message' : 'messages'} as read`
          );
        },
      }
    );
  };

  const handleBulkMarkUnread = () => {
    const messageIds = Array.from(selectedMessageIds);
    if (messageIds.length === 0) return;

    bulkMarkRead.mutate(
      { messageIds, isUnread: true },
      {
        onSuccess: () => {
          exitSelectionMode();
          toast.success(
            `Marked ${messageIds.length} ${messageIds.length === 1 ? 'message' : 'messages'} as unread`
          );
        },
      }
    );
  };

  const handleBulkRestore = () => {
    const messageIds = Array.from(selectedMessageIds);
    if (messageIds.length === 0) return;

    bulkRestore.mutate(messageIds, {
      onSuccess: () => {
        exitSelectionMode();
        toast.success(
          `Restored ${messageIds.length} ${messageIds.length === 1 ? 'message' : 'messages'}`
        );
      },
    });
  };

  const handleBulkPermanentDelete = () => {
    setPermanentDeleteDialogOpen(true);
  };

  const handlePermanentDeleteConfirm = () => {
    const messageIds = Array.from(selectedMessageIds);
    if (messageIds.length === 0) return;

    bulkPermanentDelete.mutate(messageIds, {
      onSuccess: () => {
        exitSelectionMode();
        setPermanentDeleteDialogOpen(false);
        toast.success(
          `Permanently deleted ${messageIds.length} ${messageIds.length === 1 ? 'message' : 'messages'}`
        );
      },
    });
  };

  const handleSelectAll = () => {
    if (!data) return;

    // If all messages are already selected, deselect them
    const allIds = data.messages.map((m) => m.id);
    const allSelected = allIds.every((id) => selectedMessageIds.has(id));

    if (allSelected) {
      clearSelection();
    } else {
      selectAllMessages(allIds);
    }
  };

  const handleClearTrash = () => {
    setClearTrashDialogOpen(true);
  };

  const handleClearTrashConfirm = () => {
    clearTrash.mutate(undefined, {
      onSuccess: (result) => {
        setClearTrashDialogOpen(false);
        const count = result.deleted || 0;
        toast.success(`${count} ${count === 1 ? 'message' : 'messages'} deleted`);
      },
    });
  };

  // Loading state
  if (isLoading) {
    return (
      <Box
        display="flex"
        justifyContent="center"
        alignItems="center"
        minHeight="400px"
      >
        <CircularProgress />
      </Box>
    );
  }

  // Error state - detect network errors
  if (error) {
    const isNetworkError =
      error.message.includes('Network') ||
      error.message.includes('fetch') ||
      error.message.includes('Failed to fetch') ||
      error.message.includes('net::') ||
      !navigator.onLine;

    return (
      <Box
        display="flex"
        flexDirection="column"
        alignItems="center"
        justifyContent="center"
        minHeight="400px"
        textAlign="center"
        p={4}
      >
        {isNetworkError ? (
          <>
            <WifiOff sx={{ fontSize: 64, color: 'warning.main', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              Unable to connect
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              Check your internet connection and try again.
            </Typography>
          </>
        ) : (
          <>
            <InboxOutlined sx={{ fontSize: 64, color: 'error.main', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              Failed to load messages
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              {error.message}
            </Typography>
          </>
        )}
        <Button
          variant="contained"
          startIcon={<Refresh />}
          onClick={() => window.location.reload()}
        >
          Retry
        </Button>
      </Box>
    );
  }

  // Empty state
  if (!data || data.messages.length === 0) {
    return (
      <Box
        display="flex"
        flexDirection="column"
        alignItems="center"
        justifyContent="center"
        minHeight="400px"
        textAlign="center"
        p={4}
      >
        <InboxOutlined sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
        <Typography variant="h6" color="text.secondary" gutterBottom>
          No messages found
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {searchQuery
            ? 'Try adjusting your search query'
            : 'Run a sync to fetch messages'}
        </Typography>
      </Box>
    );
  }

  // Check if all messages on current page are selected
  const allIds = data.messages.map((m) => m.id);
  const allSelected = allIds.length > 0 && allIds.every((id) => selectedMessageIds.has(id));

  // Format relative time for cache indicator
  const formatCacheTime = (timestamp: number) => {
    const diffMs = Date.now() - timestamp;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${Math.floor(diffHours / 24)}d ago`;
  };

  // Handle message click - in split mode, select for reading pane; otherwise navigate
  const handleMessageClick = (messageId: string) => {
    if (layoutMode === 'split') {
      setSelectedMessageId(messageId);
    } else {
      navigate(`/messages/${messageId}`);
    }
  };

  // Callbacks for ReadingPane keyboard navigation
  const handleReply = (messageId: string) => {
    const message = data?.messages.find((m) => m.id === messageId);
    if (message) navigate(replyUrl(message));
  };

  const handleDelete = (messageId: string) => {
    bulkDelete.mutate([messageId], {
      onSuccess: () => {
        toast.success('Moved to trash', {
          label: 'Undo',
          onClick: () => {
            bulkRestore.mutate([messageId]);
          },
        });
      },
    });
  };

  const handleToggleRead = (messageId: string) => {
    const message = data?.messages.find((m) => m.id === messageId);
    if (message) {
      markReadMutation.mutate({
        id: messageId,
        data: { is_unread: !message.is_unread },
      });
    } else {
      // Message not in current list - fetch current status and toggle
      // This can happen if the list was refreshed or message is on another page
      console.warn(`Message ${messageId} not found in current list, attempting direct toggle`);
      // Default to marking as read if we can't determine current state
      markReadMutation.mutate({
        id: messageId,
        data: { is_unread: false },
      });
    }
  };

  // Message list content (shared between mobile and desktop)
  const messageListContent = (
    <>
      {/* Offline cached data banner */}
      {isShowingCachedData && (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            p: 1.5,
            backgroundColor: 'warning.main',
            color: 'warning.contrastText',
          }}
        >
          <CloudOff fontSize="small" />
          <Typography variant="body2">
            You're offline. Showing cached messages from {formatCacheTime(dataUpdatedAt)}.
          </Typography>
        </Box>
      )}

      <Box sx={{ py: 1, px: 1, backgroundColor: theme.palette.background.default }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
          {/* Left side: message count, Select All, Clear Trash */}
          <Box display="flex" gap={2} alignItems="center" flexWrap="wrap">
            <Typography variant="body2" color="text.secondary">
              {data.total} {data.total === 1 ? 'message' : 'messages'}
            </Typography>

            {/* Select All button (only shown when in selection mode or has selections) */}
            {data.total > 0 && (selectionMode || selectedMessageIds.size > 0) && (
              <Button
                size="small"
                color="primary"
                startIcon={<CheckBox />}
                onClick={handleSelectAll}
                variant="outlined"
              >
                {allSelected ? 'Deselect All' : 'Select All'}
              </Button>
            )}

            {/* Clear Trash button - in trash folder, after Select All area */}
            {isTrash && data.total > 0 && (
              <Button
                size="small"
                color="error"
                startIcon={<DeleteSweep />}
                onClick={handleClearTrash}
                variant="outlined"
              >
                Clear Trash
              </Button>
            )}
          </Box>

          {/* Right side: Layout toggle (desktop only) */}
          {!isMobile && (
            <Tooltip title={layoutMode === 'split' ? 'Switch to list-only view (o)' : 'Switch to split view (o)'}>
              <IconButton
                onClick={toggleLayoutMode}
                size="small"
                sx={{
                  backgroundColor: 'transparent',
                  '&:hover': {
                    backgroundColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.04)',
                  },
                }}
              >
                {layoutMode === 'split' ? <ViewStream /> : <ViewSidebar />}
              </IconButton>
            </Tooltip>
          )}
        </Box>

        {/* Swipeable cards on mobile touch devices, regular cards on desktop */}
        {isMobile && isTouchDevice ? (
          <SwipeableMessageList
            messages={data.messages}
            onMessageClick={(message) => handleMessageClick(message.id)}
            onDelete={(messageId) => handleDelete(messageId)}
          />
        ) : (
          data.messages.map((message) => (
            <MessageCard
              key={message.id}
              message={message}
              onClick={() => handleMessageClick(message.id)}
              compact={isMobile}
              selectionMode={selectionMode}
            />
          ))
        )}

        {/* Pagination */}
        {data.total > ITEMS_PER_PAGE && (
          <Stack spacing={2} alignItems="center" mt={3} mb={2}>
            <Pagination
              count={Math.ceil(data.total / ITEMS_PER_PAGE)}
              page={page}
              onChange={(_event, value) => {
                setPage(value);
                clearSelection(); // Clear selections when changing pages
                window.scrollTo({ top: 0, behavior: 'smooth' }); // Scroll to top
              }}
              color="primary"
              showFirstButton
              showLastButton
            />
            <Typography variant="caption" color="text.secondary">
              Showing {data.offset + 1}-{Math.min(data.offset + ITEMS_PER_PAGE, data.total)} of {data.total}
            </Typography>
          </Stack>
        )}
      </Box>
    </>
  );

  // Render with ReadingPane on desktop, plain list on mobile
  const renderedContent = isMobile ? (
    messageListContent
  ) : (
    <ReadingPane
      messages={data.messages}
      onReply={handleReply}
      onDelete={handleDelete}
      onToggleRead={handleToggleRead}
    >
      {messageListContent}
    </ReadingPane>
  );

  return (
    <>
      {renderedContent}

      {/* Bulk Action Bar */}
      <BulkActionBar
        onDelete={handleBulkDelete}
        onMarkRead={handleBulkMarkRead}
        onMarkUnread={handleBulkMarkUnread}
        onRestore={handleBulkRestore}
        onPermanentDelete={handleBulkPermanentDelete}
        isTrash={isTrash}
      />

      {/* Clear Trash Confirmation Dialog */}
      <Dialog open={clearTrashDialogOpen} onClose={() => setClearTrashDialogOpen(false)}>
        <DialogTitle>Permanently Delete All?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to permanently delete all {data.total} {data.total === 1 ? 'message' : 'messages'} in Trash?
            This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setClearTrashDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleClearTrashConfirm}
            color="error"
            variant="contained"
            disabled={clearTrash.isPending}
          >
            {clearTrash.isPending ? 'Deleting...' : 'Permanently Delete'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Permanent Delete Selected Confirmation Dialog */}
      <Dialog open={permanentDeleteDialogOpen} onClose={() => setPermanentDeleteDialogOpen(false)}>
        <DialogTitle>Permanently Delete Selected?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to permanently delete {selectedMessageIds.size} selected {selectedMessageIds.size === 1 ? 'message' : 'messages'}?
            This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPermanentDeleteDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handlePermanentDeleteConfirm}
            color="error"
            variant="contained"
            disabled={bulkPermanentDelete.isPending}
          >
            {bulkPermanentDelete.isPending ? 'Deleting...' : 'Permanently Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
