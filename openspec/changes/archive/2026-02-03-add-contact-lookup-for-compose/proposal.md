# Change: Add Contact Lookup for Email Composition

## Why

cairn-mail is connected to contacts via mcp-gateway (used by action tags), but the web UI compose form doesn't leverage this knowledge. Users must type full email addresses manually when composing emails. Standard email clients provide contact-aware autocomplete - cairn-mail should too.

## What Changes

### Web UI: Recipient Autocomplete
- **Autocomplete in compose form**: To/CC/BCC fields show contact suggestions as user types
- Backend API endpoint to proxy contact search to mcp-gateway
- Debounced search with minimum query length (2-3 chars)
- Keyboard navigation for autocomplete dropdown

## Impact

- Affected specs: New `contact-lookup` capability
- Affected code:
  - New: `src/cairn_mail/api/routes/contacts.py` (autocomplete API endpoint)
  - Modified: `src/web/components/ComposeEmail.tsx` (add autocomplete UI)
