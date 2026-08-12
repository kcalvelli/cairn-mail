/**
 * TokenGate - modal prompt for the API bearer token.
 *
 * Opens automatically when no token is stored, and whenever the API returns 401
 * (via the AUTH_REQUIRED_EVENT the axios interceptor fires). On submit it stores
 * the token and reloads so every query and the WebSocket reconnect with it.
 */

import { useEffect, useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  TextField,
} from '@mui/material';
import { AUTH_REQUIRED_EVENT, getToken, setToken } from '../api/token';

export function TokenGate() {
  const [open, setOpen] = useState(() => !getToken());
  const [value, setValue] = useState('');

  useEffect(() => {
    const onAuthRequired = () => setOpen(true);
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
  }, []);

  const submit = () => {
    const token = value.trim();
    if (!token) return;
    setToken(token);
    // Reload so all queries and the WebSocket re-establish with the token.
    window.location.reload();
  };

  return (
    <Dialog open={open} disableEscapeKeyDown maxWidth="xs" fullWidth>
      <DialogTitle>Enter access token</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          cairn-mail requires an access token. Paste the shared token to continue.
        </DialogContentText>
        <TextField
          autoFocus
          fullWidth
          type="password"
          label="Access token"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit();
          }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={submit} variant="contained" disabled={!value.trim()}>
          Continue
        </Button>
      </DialogActions>
    </Dialog>
  );
}
