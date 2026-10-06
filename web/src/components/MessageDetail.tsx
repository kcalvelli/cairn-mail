/**
 * MessageDetail component - Reusable message detail view
 * Used in both the full-page MessageDetailPage and the ReadingPane split view
 */

import { useState, useEffect, useMemo, useRef } from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  Stack,
  IconButton,
  CircularProgress,
  Alert,
  Autocomplete,
  TextField,
  Button,
  Divider,
  Tooltip,
  useTheme,
  Dialog,
  DialogContent,
  DialogTitle,
} from '@mui/material';
import {
  Mail,
  MailOutline,
  Delete,
  Reply,
  Forward,
  AttachFile,
  Download,
  Print,
  ArrowBack,
  Close,
  Visibility,
  Image as ImageIcon,
} from '@mui/icons-material';
import DOMPurify from 'dompurify';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { SenderAvatar, extractSenderName } from './SenderAvatar';
import { QuotedText, processHtmlQuotes } from './QuotedText';
import { TagChip } from './TagChip';
import { ConfidenceBadgeAlways } from './ConfidenceBadge';
import { SmartReplies } from './SmartReplies';
import { ThreadView } from './ThreadView';
import { EmailContent } from './EmailContent';
import {
  useMessage,
  useUpdateTags,
  useMarkRead,
  useMessageBody,
} from '../hooks/useMessages';
import { useAvailableTags, useActionTagNames } from '../hooks/useStats';
import { useIsMobile } from '../hooks/useIsMobile';
import { useAppStore } from '../store/appStore';

interface Attachment {
  id: string;
  filename: string;
  content_type: string;
  size: number;
}

interface MessageDetailProps {
  messageId: string;
  /** Compact mode for reading pane (less padding) */
  compact?: boolean;
  /** Show back button */
  showBackButton?: boolean;
  /** Custom back handler */
  onBack?: () => void;
  /** Delete handler (if not provided, uses default) */
  onDelete?: () => void;
}

export function MessageDetail({
  messageId,
  compact = false,
  showBackButton = true,
  onBack,
  onDelete,
}: MessageDetailProps) {
  const navigate = useNavigate();
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const isMobile = useIsMobile();

  // Mobile touch target size (48px minimum for accessibility)
  const mobileButtonSize = isMobile ? 'medium' : 'small';

  const { data: message, isLoading, error } = useMessage(messageId);
  const { data: body, isLoading: bodyLoading } = useMessageBody(messageId);
  const { data: availableTagsData } = useAvailableTags();
  const actionTagNames = useActionTagNames();
  const updateTags = useUpdateTags();
  const markRead = useMarkRead();

  // Plain text preference from store
  const preferPlainTextInCompact = useAppStore((state) => state.preferPlainTextInCompact);
  // Local toggle to override preference for this email
  const [forceHtml, setForceHtml] = useState(false);

  const [editingTags, setEditingTags] = useState(false);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagInputValue, setTagInputValue] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [attachmentsLoading, setAttachmentsLoading] = useState(false);
  const [showQuotedHtml, setShowQuotedHtml] = useState(false);
  // Attachment preview state
  const [previewAttachment, setPreviewAttachment] = useState<Attachment | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Track which messages we've already marked as read to prevent loops
  const markedAsReadRef = useRef<Set<string>>(new Set());

  // Auto-mark as read when message is opened (with guard against repeated calls)
  useEffect(() => {
    if (message && message.is_unread && !markedAsReadRef.current.has(message.id)) {
      markedAsReadRef.current.add(message.id);
      markRead.mutate({
        id: message.id,
        data: { is_unread: false },
      });
    }
  }, [message?.id, message?.is_unread]);

  // Fetch attachments when message loads
  useEffect(() => {
    const fetchAttachments = async () => {
      if (!messageId || !message?.has_attachments) {
        setAttachments([]);
        return;
      }
      setAttachmentsLoading(true);
      try {
        const response = await axios.get(`/api/attachments/messages/${messageId}/attachments`);
        setAttachments(response.data);
      } catch (err) {
        console.error('Failed to fetch attachments:', err);
        setAttachments([]);
      } finally {
        setAttachmentsLoading(false);
      }
    };
    fetchAttachments();
  }, [messageId, message?.has_attachments]);

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleDownloadAttachment = async (attachment: Attachment) => {
    try {
      const response = await axios.get(
        `/api/attachments/${attachment.id}/download?message_id=${messageId}`,
        { responseType: 'blob' }
      );
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', attachment.filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to download attachment:', err);
    }
  };

  // Check if attachment is previewable (images)
  const isPreviewable = (contentType: string): boolean => {
    const previewableTypes = [
      'image/jpeg',
      'image/jpg',
      'image/png',
      'image/gif',
      'image/webp',
      'image/svg+xml',
      'image/bmp',
    ];
    return previewableTypes.includes(contentType.toLowerCase());
  };

  // Handle preview attachment
  const handlePreviewAttachment = async (attachment: Attachment) => {
    setPreviewAttachment(attachment);
    setPreviewLoading(true);

    try {
      const response = await axios.get(
        `/api/attachments/${attachment.id}/download?message_id=${messageId}`,
        { responseType: 'blob' }
      );
      const url = window.URL.createObjectURL(new Blob([response.data], { type: attachment.content_type }));
      setPreviewUrl(url);
    } catch (err) {
      console.error('Failed to load attachment preview:', err);
      setPreviewAttachment(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // Close preview and cleanup
  const handleClosePreview = () => {
    if (previewUrl) {
      window.URL.revokeObjectURL(previewUrl);
    }
    setPreviewAttachment(null);
    setPreviewUrl(null);
  };

  const handleMarkRead = () => {
    if (message) {
      markRead.mutate({
        id: message.id,
        data: { is_unread: !message.is_unread },
      });
    }
  };

  const handleEditTags = () => {
    if (message) {
      setSelectedTags(message.tags);
      setEditingTags(true);
    }
  };

  const handleSaveTags = () => {
    if (message) {
      // Include any pending input value that hasn't been added yet
      let tagsToSave = [...selectedTags];
      if (tagInputValue.trim()) {
        const newTag = tagInputValue.toLowerCase().trim();
        if (!tagsToSave.includes(newTag)) {
          tagsToSave.push(newTag);
        }
      }
      updateTags.mutate(
        { id: message.id, data: { tags: tagsToSave } },
        {
          onSuccess: () => {
            setEditingTags(false);
            setTagInputValue('');
          }
        }
      );
    }
  };

  const handleRemoveTag = (tagToRemove: string) => {
    if (message) {
      updateTags.mutate({
        id: message.id,
        data: { tags: message.tags.filter((t) => t !== tagToRemove) },
      });
    }
  };

  const handleReply = () => {
    if (message) {
      const params = new URLSearchParams({
        reply_to: message.id,
        to: message.from_email,
        subject: message.subject.startsWith('Re: ') ? message.subject : `Re: ${message.subject}`,
        thread_id: message.thread_id || '',
        account_id: message.account_id,
        quote_from: message.from_email,
        quote_date: message.date,
      });
      navigate(`/compose?${params.toString()}`);
    }
  };

  const handleForward = () => {
    if (message) {
      const params = new URLSearchParams({
        forward_from: message.id,
        subject: message.subject.startsWith('Fwd: ') ? message.subject : `Fwd: ${message.subject}`,
        account_id: message.account_id,
      });
      navigate(`/compose?${params.toString()}`);
    }
  };

  const handleSelectSmartReply = (replyText: string) => {
    if (message) {
      const params = new URLSearchParams({
        reply_to: message.id,
        to: message.from_email,
        subject: message.subject.startsWith('Re: ') ? message.subject : `Re: ${message.subject}`,
        thread_id: message.thread_id || '',
        account_id: message.account_id,
        quote_from: message.from_email,
        quote_date: message.date,
        body: replyText,
      });
      navigate(`/compose?${params.toString()}`);
    }
  };

  const handlePrint = () => {
    // Create a new window with just the email content for clean printing
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      // Fallback if popup blocked
      window.print();
      return;
    }

    const { name: sName, email: sEmail } = extractSenderName(message?.from_email || '');
    const printDate = message ? new Date(message.date).toLocaleString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }) : '';

    // Get the email content HTML
    const emailBody = body?.body_html
      ? DOMPurify.sanitize(body.body_html, {
          ALLOWED_TAGS: [
            'p', 'br', 'strong', 'em', 'u', 'b', 'i', 's',
            'a', 'ul', 'ol', 'li',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'blockquote', 'div', 'span', 'pre', 'code',
            'table', 'tr', 'td', 'th', 'thead', 'tbody',
            'img',
          ],
          ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'style', 'src', 'alt', 'width', 'height'],
        })
      : body?.body_text
        ? `<pre style="white-space: pre-wrap; font-family: inherit;">${body.body_text}</pre>`
        : message?.snippet || '';

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>${message?.subject || 'Email'}</title>
        <style>
          body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 12pt;
            line-height: 1.5;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #000;
          }
          .header {
            border-bottom: 1px solid #ddd;
            padding-bottom: 16px;
            margin-bottom: 16px;
          }
          .subject {
            font-size: 18pt;
            font-weight: 600;
            margin-bottom: 12px;
          }
          .meta {
            font-size: 10pt;
            color: #666;
            line-height: 1.8;
          }
          .meta strong {
            color: #333;
          }
          .content {
            margin-top: 16px;
          }
          .content img {
            max-width: 100%;
            height: auto;
          }
          .content a {
            color: #1976d2;
          }
          .content pre, .content code {
            background: #f5f5f5;
            padding: 8px;
            border-radius: 4px;
            font-size: 10pt;
          }
          .content blockquote {
            border-left: 3px solid #ddd;
            padding-left: 12px;
            margin-left: 0;
            color: #666;
          }
          @media print {
            body { padding: 0; }
            @page { margin: 1cm; }
          }
        </style>
      </head>
      <body>
        <div class="header">
          <div class="subject">${message?.subject || ''}</div>
          <div class="meta">
            <div><strong>From:</strong> ${sName ? `${sName} <${sEmail}>` : sEmail}</div>
            <div><strong>To:</strong> ${message?.to_emails.join(', ') || ''}</div>
            <div><strong>Date:</strong> ${printDate}</div>
          </div>
        </div>
        <div class="content">
          ${emailBody}
        </div>
      </body>
      </html>
    `);
    printWindow.document.close();

    // Wait for content to load then print
    printWindow.onload = () => {
      printWindow.print();
      printWindow.close();
    };

    // Fallback if onload doesn't fire
    setTimeout(() => {
      if (!printWindow.closed) {
        printWindow.print();
        printWindow.close();
      }
    }, 500);
  };

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      navigate(-1);
    }
  };

  // Sanitize HTML first, then process for quote collapsing
  // IMPORTANT: These hooks MUST be called before any early returns to satisfy React's rules of hooks
  const sanitizedHtml = useMemo(() => {
    if (!body?.body_html) return '';
    return DOMPurify.sanitize(body.body_html, {
      ALLOWED_TAGS: [
        'p', 'br', 'strong', 'em', 'u', 'b', 'i', 's',
        'a', 'ul', 'ol', 'li',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'blockquote', 'div', 'span', 'pre', 'code',
        'table', 'tr', 'td', 'th', 'thead', 'tbody',
        'img',
      ],
      ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'style', 'src', 'alt', 'width', 'height'],
    });
  }, [body?.body_html]);

  const { mainHtml, quotedHtml } = useMemo(() => {
    if (!sanitizedHtml) return { mainHtml: '', quotedHtml: '' };
    return processHtmlQuotes(sanitizedHtml);
  }, [sanitizedHtml]);

  // Get all available tags from taxonomy (not just tags in use)
  // Sort so action tags appear in their own group at the end
  // IMPORTANT: These hooks MUST be called before any early returns
  const allTags = useMemo(() => {
    if (!availableTagsData?.tags) return [];
    return [...availableTagsData.tags]
      .sort((a, b) => {
        if (a.category === 'action' && b.category !== 'action') return 1;
        if (a.category !== 'action' && b.category === 'action') return -1;
        return a.name.localeCompare(b.name);
      })
      .map((t) => t.name);
  }, [availableTagsData]);

  // Build a map from tag name to category for groupBy
  const tagCategoryMap = useMemo(() => {
    if (!availableTagsData?.tags) return new Map<string, string>();
    return new Map(availableTagsData.tags.map((t) => [t.name, t.category]));
  }, [availableTagsData]);

  // Early returns AFTER all hooks
  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight={200}>
        <CircularProgress />
      </Box>
    );
  }

  if (error || !message) {
    return (
      <Box p={2}>
        <Alert severity="error">Failed to load message</Alert>
      </Box>
    );
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  const { name: senderName, email: senderEmail } = extractSenderName(message.from_email);

  return (
    <Box sx={{ height: '100%', overflow: 'auto' }} className="message-detail-print">
      {/* Header Actions - No background on desktop, sticky bar on mobile */}
      <Box
        display="flex"
        alignItems="center"
        gap={isMobile ? 0.5 : compact ? 0.5 : 1}
        mb={isMobile ? 2 : compact ? 0.5 : 1}
        sx={{
          // Mobile: sticky with background for visibility
          ...(isMobile && {
            position: 'sticky',
            top: 0,
            bgcolor: isDark ? '#121212' : 'background.default',
            zIndex: 10,
            py: 1.5,
            px: 1,
            mx: -2,
            borderBottom: `1px solid ${isDark ? '#333' : '#e0e0e0'}`,
          }),
        }}
        className="no-print"
      >
        {showBackButton && (
          <Tooltip title="Back (Escape)">
            <IconButton
              onClick={handleBack}
              size={mobileButtonSize}
              sx={{ minWidth: isMobile ? 48 : 'auto' }}
            >
              <ArrowBack />
            </IconButton>
          </Tooltip>
        )}

        <Box flex={1} />

        <Tooltip title="Reply (r)">
          <IconButton onClick={handleReply} size={mobileButtonSize}>
            <Reply />
          </IconButton>
        </Tooltip>

        <Tooltip title="Forward (f)">
          <IconButton onClick={handleForward} size={mobileButtonSize}>
            <Forward />
          </IconButton>
        </Tooltip>

        <Tooltip title="Toggle read/unread (u)">
          <IconButton onClick={handleMarkRead} size={mobileButtonSize}>
            {message.is_unread ? <Mail color="primary" /> : <MailOutline />}
          </IconButton>
        </Tooltip>

        {/* Print button - hide on mobile (not practical) */}
        {!isMobile && (
          <Tooltip title="Print">
            <IconButton onClick={handlePrint} size={mobileButtonSize}>
              <Print />
            </IconButton>
          </Tooltip>
        )}

        {onDelete && (
          <Tooltip title="Delete (#)">
            <IconButton onClick={onDelete} size={mobileButtonSize} color="error">
              <Delete />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* Message Content */}
      <Paper sx={{ p: compact ? 2 : 3, bgcolor: isDark ? '#1E1E1E' : 'background.paper' }}>
        {/* Sender with Avatar */}
        <Box display="flex" alignItems="flex-start" gap={compact ? 1.5 : 2} mb={compact ? 1 : 2}>
          <SenderAvatar email={senderEmail} name={senderName} size={compact ? 36 : 48} />
          <Box flex={1} minWidth={0}>
            <Typography variant={compact ? 'body1' : 'subtitle1'} fontWeight={600}>
              {senderName || senderEmail}
            </Typography>
            {senderName && (
              <Typography variant="body2" color="text.secondary" sx={{ fontSize: compact ? '0.8rem' : undefined }}>
                {senderEmail}
              </Typography>
            )}
            <Typography variant="caption" color="text.secondary">
              {formatDate(message.date)}
            </Typography>
          </Box>
        </Box>

        {/* Subject */}
        <Typography variant={compact ? 'subtitle1' : 'h6'} gutterBottom sx={{ fontWeight: 600 }}>
          {message.subject}
        </Typography>

        {/* To */}
        <Typography variant="body2" color="text.secondary" gutterBottom sx={{ fontSize: compact ? '0.8rem' : undefined }}>
          <strong>To:</strong> {message.to_emails.join(', ')}
        </Typography>

        {/* Tags Section */}
        <Box mt={compact ? 1 : 2} mb={compact ? 1 : 2}>
          {editingTags ? (
            <Box>
              <Autocomplete
                multiple
                freeSolo
                options={allTags}
                groupBy={(option) => {
                  const cat = tagCategoryMap.get(option);
                  return cat === 'action' ? 'Actions' : 'Tags';
                }}
                value={selectedTags}
                inputValue={tagInputValue}
                onInputChange={(_, newInputValue) => {
                  setTagInputValue(newInputValue);
                }}
                onChange={(_, newValue) => {
                  // Handle both selected options and free-form text
                  const tags = newValue.map(v => typeof v === 'string' ? v.toLowerCase().trim() : v);
                  // Filter out empty strings and duplicates
                  const uniqueTags = [...new Set(tags.filter(t => t.length > 0))];
                  setSelectedTags(uniqueTags);
                  setTagInputValue(''); // Clear input after selection
                }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    variant="outlined"
                    placeholder="Select or type tags..."
                    size="small"
                    helperText="Select from list or type custom tags (press Enter to add)"
                  />
                )}
                sx={{ mb: 1 }}
              />
              <Stack direction="row" spacing={1}>
                <Chip label="Save" color="primary" onClick={handleSaveTags} size="small" />
                <Chip label="Cancel" variant="outlined" onClick={() => setEditingTags(false)} size="small" />
              </Stack>
            </Box>
          ) : (
            <Stack direction="row" spacing={0.5} flexWrap="wrap" gap={0.5} alignItems="center">
              {message.tags.map((tag) => (
                <TagChip key={tag} tag={tag} onDelete={() => handleRemoveTag(tag)} size="small" isActionTag={actionTagNames.has(tag)} />
              ))}
              <Chip label="+ Edit" variant="outlined" size="small" onClick={handleEditTags} />
            </Stack>
          )}
        </Box>

        {/* Attachments */}
        {(attachments.length > 0 || attachmentsLoading) && (
          <Box mt={compact ? 1 : 2} mb={compact ? 1 : 2}>
            <Typography variant="subtitle2" gutterBottom sx={{ fontSize: compact ? '0.8rem' : undefined }}>
              <AttachFile fontSize="small" sx={{ verticalAlign: 'middle', mr: 0.5 }} />
              Attachments ({attachments.length})
            </Typography>
            {attachmentsLoading ? (
              <CircularProgress size={20} />
            ) : (
              <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                {attachments.map((att) => (
                  <Box key={att.id} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    {/* Preview button for images */}
                    {isPreviewable(att.content_type) && (
                      <Tooltip title="Preview">
                        <IconButton
                          size="small"
                          onClick={() => handlePreviewAttachment(att)}
                          sx={{ p: 0.5 }}
                        >
                          <Visibility fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                    {/* Download chip */}
                    <Chip
                      label={`${att.filename} (${formatFileSize(att.size)})`}
                      icon={isPreviewable(att.content_type) ? <ImageIcon /> : <Download />}
                      onClick={() => handleDownloadAttachment(att)}
                      variant="outlined"
                      sx={{ cursor: 'pointer' }}
                    />
                  </Box>
                ))}
              </Stack>
            )}
          </Box>
        )}

        {/* Image Preview Modal */}
        <Dialog
          open={!!previewAttachment}
          onClose={handleClosePreview}
          maxWidth="lg"
          fullWidth
        >
          <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="subtitle1" noWrap sx={{ flex: 1, mr: 2 }}>
              {previewAttachment?.filename}
            </Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Tooltip title="Download">
                <IconButton
                  size="small"
                  onClick={() => previewAttachment && handleDownloadAttachment(previewAttachment)}
                >
                  <Download />
                </IconButton>
              </Tooltip>
              <IconButton size="small" onClick={handleClosePreview}>
                <Close />
              </IconButton>
            </Box>
          </DialogTitle>
          <DialogContent sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
            {previewLoading ? (
              <CircularProgress />
            ) : previewUrl ? (
              <Box
                component="img"
                src={previewUrl}
                alt={previewAttachment?.filename}
                sx={{
                  maxWidth: '100%',
                  maxHeight: '70vh',
                  objectFit: 'contain',
                }}
              />
            ) : (
              <Typography color="text.secondary">Failed to load preview</Typography>
            )}
          </DialogContent>
        </Dialog>

        <Divider sx={{ my: compact ? 1.5 : 2 }} />

        {/* Message Body */}
        <Box mt={compact ? 1 : 2}>
          {bodyLoading ? (
            <Box display="flex" justifyContent="center" p={2}>
              <CircularProgress size={24} />
            </Box>
          ) : (() => {
            // Determine if we should show plain text
            const shouldShowPlainText = compact && preferPlainTextInCompact && body?.body_text && !forceHtml;
            const hasHtmlAndText = mainHtml && body?.body_text;

            if (shouldShowPlainText) {
              return (
                <>
                  {/* Toggle to view HTML */}
                  {hasHtmlAndText && (
                    <Box sx={{ mb: 1, display: 'flex', justifyContent: 'flex-end' }}>
                      <Button
                        size="small"
                        onClick={() => setForceHtml(true)}
                        sx={{ textTransform: 'none', fontSize: '0.75rem', color: 'text.secondary' }}
                      >
                        View HTML version
                      </Button>
                    </Box>
                  )}
                  <QuotedText text={body.body_text!} />
                </>
              );
            }

            if (mainHtml) {
              return (
                <>
                  {/* Toggle to view plain text (if preference is enabled but user forced HTML) */}
                  {compact && forceHtml && body?.body_text && (
                    <Box sx={{ mb: 1, display: 'flex', justifyContent: 'flex-end' }}>
                      <Button
                        size="small"
                        onClick={() => setForceHtml(false)}
                        sx={{ textTransform: 'none', fontSize: '0.75rem', color: 'text.secondary' }}
                      >
                        View plain text
                      </Button>
                    </Box>
                  )}

                  {/* Main HTML content with enhanced rendering */}
                  <EmailContent
                    html={mainHtml}
                    compact={compact}
                    inlineAttachments={body?.inline_attachments}
                    accountId={message.account_id}
                    senderEmail={senderEmail}
                  />

                  {/* Quoted HTML toggle */}
                  {quotedHtml && (
                    <Box mt={2}>
                      <Button
                        size="small"
                        onClick={() => setShowQuotedHtml(!showQuotedHtml)}
                        sx={{ textTransform: 'none', color: 'text.secondary', fontSize: '0.75rem' }}
                      >
                        {showQuotedHtml ? '▼ Hide quoted text' : '▶ Show quoted text'}
                      </Button>
                      {showQuotedHtml && (
                        <Box
                          sx={{
                            pl: 2,
                            borderLeft: `3px solid ${isDark ? '#444' : '#ddd'}`,
                            mt: 1,
                            color: 'text.secondary',
                          }}
                        >
                          <EmailContent
                            html={quotedHtml}
                            compact={compact}
                            inlineAttachments={body?.inline_attachments}
                            accountId={message.account_id}
                            senderEmail={senderEmail}
                          />
                        </Box>
                      )}
                    </Box>
                  )}
                </>
              );
            }

            if (body?.body_text) {
              return <QuotedText text={body.body_text} />;
            }

            return (
              <Typography variant="body1" color="text.secondary">
                {message.snippet}
              </Typography>
            );
          })()}
        </Box>

        {/* Smart Replies */}
        <SmartReplies
          messageId={message.id}
          onSelectReply={handleSelectSmartReply}
          folder={message.provider_labels.includes('SENT') ? 'sent' : undefined}
          tags={message.tags}
        />

        {/* Metadata - more compact in reading pane mode */}
        {message.classified_at && !compact && (
          <Box mt={3} display="flex" alignItems="center" gap={1} className="no-print">
            <Typography variant="caption" color="text.secondary">
              Classified on {new Date(message.classified_at).toLocaleString()}
            </Typography>
            {message.confidence !== undefined && message.confidence !== null && (
              <>
                <Typography variant="caption" color="text.secondary">•</Typography>
                <Box display="flex" alignItems="center" gap={0.5}>
                  <Typography variant="caption" color="text.secondary">Confidence:</Typography>
                  <ConfidenceBadgeAlways confidence={message.confidence} size="small" showLabel />
                </Box>
              </>
            )}
          </Box>
        )}
        {/* Compact mode: just show confidence inline */}
        {message.classified_at && compact && message.confidence !== undefined && message.confidence !== null && (
          <Box mt={1.5} display="flex" alignItems="center" gap={0.5} className="no-print">
            <ConfidenceBadgeAlways confidence={message.confidence} size="small" />
          </Box>
        )}

        {/* Thread/Conversation View */}
        {message.thread_id && (
          <ThreadView threadId={message.thread_id} currentMessageId={message.id} />
        )}
      </Paper>

      {/* Print Styles */}
      <style>{`
        @media print {
          /* Hide non-printable elements */
          .no-print,
          header,
          nav,
          aside,
          .MuiDrawer-root,
          .MuiAppBar-root {
            display: none !important;
          }

          /* Reset container for print */
          .message-detail-print {
            overflow: visible !important;
            height: auto !important;
            width: 100% !important;
            max-width: none !important;
            padding: 0 !important;
            margin: 0 !important;
          }

          /* Page settings */
          @page {
            margin: 1cm;
            size: A4;
          }

          /* Email content styling */
          .email-content {
            font-size: 12pt !important;
            line-height: 1.5 !important;
          }

          /* Ensure images don't break pages */
          img {
            max-width: 100% !important;
            page-break-inside: avoid;
          }

          /* Keep paragraphs together */
          p {
            orphans: 3;
            widows: 3;
          }

          /* Print headers */
          h1, h2, h3, h4, h5, h6 {
            page-break-after: avoid;
          }

          /* Links - show URLs */
          a[href^="http"]:after {
            content: " (" attr(href) ")";
            font-size: 0.8em;
            color: #666;
          }

          /* Hide interactive elements */
          button, .MuiIconButton-root, .MuiChip-root[onclick] {
            display: none !important;
          }
        }
      `}</style>
    </Box>
  );
}
