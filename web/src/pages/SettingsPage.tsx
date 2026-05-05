/**
 * SettingsPage - Configuration and settings management
 */

import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Tabs,
  Tab,
  Grid,
  TextField,
  Stack,
  Chip,
  Divider,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Card,
  CardContent,
  CardActions,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  LinearProgress,
  FormControlLabel,
  Checkbox,
  CircularProgress,
  Switch,
} from '@mui/material';
import {
  SmartToy,
  Sync,
  Label,
  Build,
  Refresh,
  PlayArrow,
  Stop,
  CheckCircle,
  Error as ErrorIcon,
  DisplaySettings,
  Notifications,
} from '@mui/icons-material';
import { useAppStore } from '../store/appStore';
import { usePushSubscription } from '../hooks/usePushSubscription';
import axios from 'axios';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel({ children, value, index }: TabPanelProps) {
  return (
    <div role="tabpanel" hidden={value !== index}>
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState(0);

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Settings
      </Typography>

      <Paper sx={{ mt: 3 }}>
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => setActiveTab(newValue)}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab icon={<DisplaySettings />} label="Display" />
          <Tab icon={<Notifications />} label="Notifications" />
          <Tab icon={<SmartToy />} label="AI Configuration" />
          <Tab icon={<Sync />} label="Sync Settings" />
          <Tab icon={<Label />} label="Tag Taxonomy" />
          <Tab icon={<Build />} label="Maintenance" />
        </Tabs>

        <TabPanel value={activeTab} index={0}>
          <DisplaySettingsPanel />
        </TabPanel>

        <TabPanel value={activeTab} index={1}>
          <NotificationsPanel />
        </TabPanel>

        <TabPanel value={activeTab} index={2}>
          <AIConfigPanel />
        </TabPanel>

        <TabPanel value={activeTab} index={3}>
          <SyncSettingsPanel />
        </TabPanel>

        <TabPanel value={activeTab} index={4}>
          <TagTaxonomyPanel />
        </TabPanel>

        <TabPanel value={activeTab} index={5}>
          <MaintenancePanel />
        </TabPanel>
      </Paper>
    </Box>
  );
}

function DisplaySettingsPanel() {
  const preferPlainTextInCompact = useAppStore((state) => state.preferPlainTextInCompact);
  const setPreferPlainTextInCompact = useAppStore((state) => state.setPreferPlainTextInCompact);

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Reading Pane Settings
      </Typography>

      <Stack spacing={3}>
        <Box>
          <FormControlLabel
            control={
              <Checkbox
                checked={preferPlainTextInCompact}
                onChange={(e) => setPreferPlainTextInCompact(e.target.checked)}
              />
            }
            label="Prefer plain text in compact mode"
          />
          <Typography variant="body2" color="text.secondary" sx={{ ml: 4 }}>
            When viewing emails in the reading pane (split view), show plain text instead of HTML
            when available. This can improve readability for marketing emails and newsletters.
            You can still switch to HTML view on a per-email basis.
          </Typography>
        </Box>

        <Divider />

        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Compact Mode Features
          </Typography>
          <Typography variant="body2" color="text.secondary">
            When viewing emails in the reading pane, the following optimizations are applied:
          </Typography>
          <ul style={{ margin: '8px 0', paddingLeft: '20px' }}>
            <li>
              <Typography variant="body2" color="text.secondary">
                Smaller font size and reduced spacing for better content density
              </Typography>
            </li>
            <li>
              <Typography variant="body2" color="text.secondary">
                Table linearization to fit wide email layouts in narrow panes
              </Typography>
            </li>
            <li>
              <Typography variant="body2" color="text.secondary">
                Automatic scaling for emails that overflow the available width
              </Typography>
            </li>
          </ul>
        </Box>
      </Stack>
    </Box>
  );
}

function NotificationsPanel() {
  const push = usePushSubscription();

  const handleToggle = async () => {
    try {
      if (push.isSubscribed) {
        await push.unsubscribe();
      } else {
        await push.subscribe();
      }
    } catch (err) {
      console.error('Push toggle error:', err);
    }
  };

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Push Notifications
      </Typography>

      {!push.supported ? (
        <Alert severity="warning" sx={{ mb: 3 }}>
          Push notifications are not supported in this browser. Try using a
          Chromium-based browser or Firefox.
        </Alert>
      ) : (
        <Stack spacing={3}>
          <Box>
            <FormControlLabel
              control={
                <Switch
                  checked={push.isSubscribed}
                  onChange={handleToggle}
                  disabled={push.loading || push.permission === 'denied'}
                />
              }
              label={push.isSubscribed ? 'Push notifications enabled' : 'Enable push notifications'}
            />
            {push.loading && (
              <CircularProgress size={20} sx={{ ml: 2 }} />
            )}
            <Typography variant="body2" color="text.secondary" sx={{ ml: 4 }}>
              Receive push notifications on this device when new emails arrive,
              even when the app is closed.
            </Typography>
          </Box>

          {push.permission === 'denied' && (
            <Alert severity="error">
              Notification permission has been blocked. To enable push
              notifications, update the notification setting for this site in
              your browser settings.
            </Alert>
          )}

          {push.error && (
            <Alert severity="error">
              {push.error}
            </Alert>
          )}

          <Divider />

          <Box>
            <Typography variant="subtitle2" gutterBottom>
              How it works
            </Typography>
            <Typography variant="body2" color="text.secondary">
              When push notifications are enabled, you'll receive a notification
              each time new emails are synced. Notifications show the sender and
              subject. Tapping a notification opens the email in the app.
            </Typography>
          </Box>
        </Stack>
      )}
    </Box>
  );
}

function AIConfigPanel() {
  // These values are read-only in the web UI
  // Configuration is managed through Nix config
  const defaultConfig = {
    provider: 'ollama',
    model: 'mistral:latest',
    endpoint: 'http://localhost:11434',
    temperature: 0.7,
    max_tokens: 500,
  };

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 3 }}>
        AI configuration is managed through your Nix configuration file. Changes
        here are for reference only.
      </Alert>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <TextField
            label="Provider"
            value={defaultConfig.provider}
            fullWidth
            disabled
            helperText="AI provider (ollama, openai, anthropic)"
          />
        </Grid>

        <Grid item xs={12} md={6}>
          <TextField
            label="Model"
            value={defaultConfig.model}
            fullWidth
            disabled
            helperText="Model name to use for classification"
          />
        </Grid>

        <Grid item xs={12}>
          <TextField
            label="Endpoint"
            value={defaultConfig.endpoint}
            fullWidth
            disabled
            helperText="API endpoint URL"
          />
        </Grid>

        <Grid item xs={12} md={6}>
          <TextField
            label="Temperature"
            value={defaultConfig.temperature}
            type="number"
            fullWidth
            disabled
            helperText="0.0 (deterministic) to 1.0 (creative)"
          />
        </Grid>

        <Grid item xs={12} md={6}>
          <TextField
            label="Max Tokens"
            value={defaultConfig.max_tokens}
            type="number"
            fullWidth
            disabled
            helperText="Maximum tokens for AI response"
          />
        </Grid>
      </Grid>

      <Divider sx={{ my: 3 }} />

      <Typography variant="h6" gutterBottom>
        Model Capabilities
      </Typography>

      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Feature</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableRow>
              <TableCell>Email Classification</TableCell>
              <TableCell>
                <Chip label="Enabled" color="success" size="small" />
              </TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Priority Detection</TableCell>
              <TableCell>
                <Chip label="Enabled" color="success" size="small" />
              </TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Auto Classification</TableCell>
              <TableCell>
                <Chip label="Enabled" color="success" size="small" />
              </TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Action Detection</TableCell>
              <TableCell>
                <Chip label="Enabled" color="success" size="small" />
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

function SyncSettingsPanel() {
  return (
    <Box>
      <Alert severity="info" sx={{ mb: 3 }}>
        Sync settings are managed through your Nix configuration and systemd
        timers.
      </Alert>

      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" gutterBottom>
            Sync Frequency
          </Typography>
          <Typography variant="body2" color="text.secondary" paragraph>
            Email sync runs automatically via systemd timer. Default: every 5
            minutes.
          </Typography>
          <TextField
            label="Sync Interval"
            value="5 minutes"
            fullWidth
            disabled
            helperText="Configured in Nix: programs.cairn-mail.sync.frequency"
          />
        </Box>

        <Divider />

        <Box>
          <Typography variant="h6" gutterBottom>
            Sync Behavior
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <TextField
                label="Max Messages Per Sync"
                value="50"
                type="number"
                fullWidth
                disabled
                helperText="Maximum new messages to fetch per sync"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                label="Classification Batch Size"
                value="10"
                type="number"
                fullWidth
                disabled
                helperText="Messages classified per AI request"
              />
            </Grid>
          </Grid>
        </Box>

        <Divider />

        <Box>
          <Typography variant="h6" gutterBottom>
            Webhook Integration
          </Typography>
          <Typography variant="body2" color="text.secondary" paragraph>
            Configure webhooks to receive notifications about sync events.
          </Typography>
          <TextField
            label="Webhook URL"
            placeholder="https://example.com/webhook"
            fullWidth
            disabled
            helperText="Configured in Nix: programs.cairn-mail.webhook.url"
          />
        </Box>
      </Stack>
    </Box>
  );
}

interface TagConfig {
  tags: Array<{
    name: string;
    description: string;
    category?: string;
    source: 'default' | 'custom' | 'unknown';
  }>;
  use_default_tags: boolean;
  excluded_tags: string[];
  total_count: number;
  default_count: number;
  custom_count: number;
}

const CATEGORY_COLORS: Record<string, 'error' | 'primary' | 'secondary' | 'success' | 'info' | 'warning' | 'default'> = {
  priority: 'error',
  work: 'primary',
  personal: 'secondary',
  finance: 'success',
  shopping: 'warning',
  travel: 'info',
  developer: 'info',
  marketing: 'warning',
  social: 'default',
  system: 'default',
};

function TagTaxonomyPanel() {
  const [tagConfig, setTagConfig] = useState<TagConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTagConfig = async () => {
      try {
        setLoading(true);
        const response = await axios.get('/api/maintenance/tag-config');
        setTagConfig(response.data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch tag config:', err);
        setError('Failed to load tag configuration');
      } finally {
        setLoading(false);
      }
    };

    fetchTagConfig();
  }, []);

  // Group tags by category
  const groupedTags = tagConfig?.tags.reduce((acc, tag) => {
    const category = tag.category || 'other';
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(tag);
    return acc;
  }, {} as Record<string, typeof tagConfig.tags>) || {};

  // Sort categories in a specific order
  const categoryOrder = ['priority', 'work', 'personal', 'finance', 'shopping', 'travel', 'developer', 'marketing', 'social', 'system', 'other'];
  const sortedCategories = Object.keys(groupedTags).sort(
    (a, b) => categoryOrder.indexOf(a) - categoryOrder.indexOf(b)
  );

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={4}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 3 }}>
        Tag taxonomy defines the categories and labels used by the AI for email
        classification. Configured in Nix.
      </Alert>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {tagConfig && (
        <>
          {/* Config Status */}
          <Paper sx={{ p: 2, mb: 3 }}>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <Typography variant="body2" color="text.secondary">
                  Use Default Tags
                </Typography>
                <Chip
                  label={tagConfig.use_default_tags ? 'Enabled' : 'Disabled'}
                  color={tagConfig.use_default_tags ? 'success' : 'default'}
                  size="small"
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <Typography variant="body2" color="text.secondary">
                  Total Tags
                </Typography>
                <Typography variant="h6">{tagConfig.total_count}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {tagConfig.default_count} default, {tagConfig.custom_count} custom
                </Typography>
              </Grid>
              {tagConfig.excluded_tags.length > 0 && (
                <Grid item xs={12} md={4}>
                  <Typography variant="body2" color="text.secondary">
                    Excluded Tags
                  </Typography>
                  <Typography variant="body2">
                    {tagConfig.excluded_tags.join(', ')}
                  </Typography>
                </Grid>
              )}
            </Grid>
          </Paper>

          {/* Tags by Category */}
          <Stack spacing={3}>
            {sortedCategories.map((category) => (
              <Box key={category}>
                <Typography variant="h6" gutterBottom sx={{ textTransform: 'capitalize' }}>
                  {category}
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                  {groupedTags[category].map((tag) => (
                    <Box key={tag.name} position="relative">
                      <Chip
                        label={
                          <Box display="flex" alignItems="center" gap={0.5}>
                            {tag.name}
                            {tag.source === 'custom' && (
                              <Chip
                                label="Custom"
                                size="small"
                                sx={{
                                  height: 16,
                                  fontSize: '0.6rem',
                                  ml: 0.5,
                                }}
                              />
                            )}
                          </Box>
                        }
                        color={CATEGORY_COLORS[category] || 'default'}
                        variant={tag.source === 'custom' ? 'filled' : 'outlined'}
                        title={tag.description}
                      />
                    </Box>
                  ))}
                </Stack>
              </Box>
            ))}
          </Stack>
        </>
      )}

      <Divider sx={{ my: 3 }} />

      <Box>
        <Typography variant="h6" gutterBottom>
          Custom Tags
        </Typography>
        <Typography variant="body2" color="text.secondary" paragraph>
          Configure your tags in your NixOS/home-manager configuration. The AI
          uses these tags to classify incoming emails automatically.
        </Typography>
        <Alert severity="info">
          <Typography variant="body2">
            <strong>AI Classification:</strong> Emails are classified using the
            configured tags above. Run a sync to classify new messages.
          </Typography>
        </Alert>
      </Box>
    </Box>
  );
}

interface JobStatus {
  job_id: string;
  operation: string;
  status: 'pending' | 'running' | 'completed' | 'cancelled' | 'failed';
  progress: number;
  total: number;
  errors: string[];
  error_count: number;
  started_at: string | null;
  completed_at: string | null;
}

function MaintenancePanel() {
  const [activeJob, setActiveJob] = useState<JobStatus | null>(null);
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    operation: 'reclassify-all' | 'reclassify-unclassified' | null;
    overrideUserEdits: boolean;
  }>({ open: false, operation: null, overrideUserEdits: false });
  const [refreshingStats, setRefreshingStats] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<{
    operation: string;
    status: string;
    timestamp: Date;
    errors: number;
  } | null>(null);

  // Poll for job status when there's an active job
  useEffect(() => {
    if (!activeJob || ['completed', 'cancelled', 'failed'].includes(activeJob.status)) {
      return;
    }

    const pollInterval = setInterval(async () => {
      try {
        const response = await axios.get(`/api/maintenance/jobs/${activeJob.job_id}`);
        const job = response.data as JobStatus;
        setActiveJob(job);

        if (['completed', 'cancelled', 'failed'].includes(job.status)) {
          setLastResult({
            operation: job.operation,
            status: job.status,
            timestamp: new Date(),
            errors: job.error_count,
          });
        }
      } catch (err) {
        console.error('Failed to poll job status:', err);
      }
    }, 1000);

    return () => clearInterval(pollInterval);
  }, [activeJob]);

  const startReclassifyAll = async (overrideUserEdits: boolean) => {
    setError(null);
    try {
      const response = await axios.post('/api/maintenance/reclassify-all', {
        override_user_edits: overrideUserEdits,
      });
      setActiveJob(response.data);
      setConfirmDialog({ open: false, operation: null, overrideUserEdits: false });
    } catch (err: any) {
      console.error('Failed to start reclassify all:', err);
      const message = err.response?.data?.detail || err.message || 'Failed to start reclassification';
      setError(message);
      setConfirmDialog({ open: false, operation: null, overrideUserEdits: false });
    }
  };

  const startReclassifyUnclassified = async () => {
    setError(null);
    try {
      const response = await axios.post('/api/maintenance/reclassify-unclassified');
      setActiveJob(response.data);
      setConfirmDialog({ open: false, operation: null, overrideUserEdits: false });
    } catch (err: any) {
      console.error('Failed to start reclassify unclassified:', err);
      const message = err.response?.data?.detail || err.message || 'Failed to start reclassification';
      setError(message);
      setConfirmDialog({ open: false, operation: null, overrideUserEdits: false });
    }
  };

  const cancelJob = async () => {
    if (!activeJob) return;
    try {
      await axios.post(`/api/maintenance/jobs/${activeJob.job_id}/cancel`);
    } catch (err) {
      console.error('Failed to cancel job:', err);
    }
  };

  const refreshStats = async () => {
    setRefreshingStats(true);
    try {
      await axios.post('/api/maintenance/refresh-stats');
      setLastResult({
        operation: 'refresh-stats',
        status: 'completed',
        timestamp: new Date(),
        errors: 0,
      });
    } catch (err) {
      console.error('Failed to refresh stats:', err);
      setLastResult({
        operation: 'refresh-stats',
        status: 'failed',
        timestamp: new Date(),
        errors: 1,
      });
    } finally {
      setRefreshingStats(false);
    }
  };

  const isJobRunning = activeJob && ['pending', 'running'].includes(activeJob.status);
  const progressPercent = activeJob && activeJob.total > 0
    ? Math.round((activeJob.progress / activeJob.total) * 100)
    : 0;

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 3 }}>
        Maintenance operations help keep your email database and classifications
        up to date. Use these tools to reclassify messages or refresh statistics.
      </Alert>

      {/* Error Display */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Active Job Progress */}
      {isJobRunning && activeJob && (
        <Paper sx={{ p: 2, mb: 3 }}>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
            <Typography variant="h6">
              {activeJob.operation === 'reclassify-all'
                ? 'Reclassifying All Messages'
                : 'Reclassifying Unclassified Messages'}
            </Typography>
            <Button
              variant="outlined"
              color="error"
              startIcon={<Stop />}
              onClick={cancelJob}
              size="small"
            >
              Cancel
            </Button>
          </Box>
          <LinearProgress variant="determinate" value={progressPercent} sx={{ mb: 1 }} />
          <Typography variant="body2" color="text.secondary">
            Progress: {activeJob.progress} / {activeJob.total} ({progressPercent}%)
            {activeJob.error_count > 0 && (
              <span style={{ color: 'red', marginLeft: 8 }}>
                {activeJob.error_count} error(s)
              </span>
            )}
          </Typography>
        </Paper>
      )}

      {/* Last Operation Result */}
      {lastResult && !isJobRunning && (
        <Alert
          severity={lastResult.status === 'completed' ? 'success' : lastResult.status === 'cancelled' ? 'warning' : 'error'}
          icon={lastResult.status === 'completed' ? <CheckCircle /> : <ErrorIcon />}
          sx={{ mb: 3 }}
          onClose={() => setLastResult(null)}
        >
          <Typography variant="body2">
            <strong>{lastResult.operation}</strong>: {lastResult.status}
            {lastResult.errors > 0 && ` with ${lastResult.errors} error(s)`}
            {' '}at {lastResult.timestamp.toLocaleTimeString()}
          </Typography>
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Reclassify All Messages */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Reclassify All Messages
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Re-run AI classification on all messages in your database.
                Useful when you've updated your tag taxonomy or want to
                re-evaluate classifications with the current AI model.
              </Typography>
            </CardContent>
            <CardActions>
              <Button
                startIcon={<Refresh />}
                variant="contained"
                onClick={() => setConfirmDialog({
                  open: true,
                  operation: 'reclassify-all',
                  overrideUserEdits: false,
                })}
                disabled={!!isJobRunning}
              >
                Reclassify All
              </Button>
            </CardActions>
          </Card>
        </Grid>

        {/* Reclassify Unclassified */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Reclassify Unclassified
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Run AI classification only on messages that haven't been
                classified yet. Faster than reclassifying all messages.
              </Typography>
            </CardContent>
            <CardActions>
              <Button
                startIcon={<PlayArrow />}
                variant="contained"
                onClick={() => setConfirmDialog({
                  open: true,
                  operation: 'reclassify-unclassified',
                  overrideUserEdits: false,
                })}
                disabled={!!isJobRunning}
              >
                Classify Unclassified
              </Button>
            </CardActions>
          </Card>
        </Grid>

        {/* Refresh Statistics */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Refresh Statistics
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Recalculate tag counts and statistics. Use this if the
                sidebar tag counts appear incorrect or out of sync.
              </Typography>
            </CardContent>
            <CardActions>
              <Button
                startIcon={refreshingStats ? <CircularProgress size={20} /> : <Sync />}
                variant="outlined"
                onClick={refreshStats}
                disabled={refreshingStats || !!isJobRunning}
              >
                {refreshingStats ? 'Refreshing...' : 'Refresh Stats'}
              </Button>
            </CardActions>
          </Card>
        </Grid>
      </Grid>

      {/* Confirmation Dialog */}
      <Dialog
        open={confirmDialog.open}
        onClose={() => setConfirmDialog({ open: false, operation: null, overrideUserEdits: false })}
      >
        <DialogTitle>
          {confirmDialog.operation === 'reclassify-all'
            ? 'Reclassify All Messages?'
            : 'Classify Unclassified Messages?'}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {confirmDialog.operation === 'reclassify-all'
              ? 'This will re-run AI classification on all messages. This may take a while depending on the number of messages.'
              : 'This will run AI classification on messages that have not been classified yet.'}
          </DialogContentText>
          {confirmDialog.operation === 'reclassify-all' && (
            <FormControlLabel
              control={
                <Checkbox
                  checked={confirmDialog.overrideUserEdits}
                  onChange={(e) => setConfirmDialog({
                    ...confirmDialog,
                    overrideUserEdits: e.target.checked,
                  })}
                />
              }
              label="Override user-edited tags (will replace manual corrections)"
              sx={{ mt: 2 }}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setConfirmDialog({ open: false, operation: null, overrideUserEdits: false })}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={() => {
              if (confirmDialog.operation === 'reclassify-all') {
                startReclassifyAll(confirmDialog.overrideUserEdits);
              } else {
                startReclassifyUnclassified();
              }
            }}
          >
            Start
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
