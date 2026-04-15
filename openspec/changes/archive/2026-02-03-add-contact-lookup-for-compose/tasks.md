# Tasks: Contact Lookup for Email Composition

## 1. Backend API for Web UI

- [x] 1.1 Create `src/cairn_mail/api/routes/contacts.py` with search endpoint
- [x] 1.2 Add `GET /api/contacts/search?q={query}` route
- [x] 1.3 Wire GatewayClient to call `mcp-dav/search_contacts`
- [x] 1.4 Handle gateway unavailable gracefully (return empty results)
- [x] 1.5 Register router in app initialization

## 2. Web UI Autocomplete

- [x] 2.1 Create `RecipientAutocomplete` component with debounced search
- [x] 2.2 Integrate into ComposeEmail form for To/CC/BCC fields
- [x] 2.3 Support keyboard navigation (up/down/enter/escape)
- [x] 2.4 Show contact name + email in dropdown
- [x] 2.5 Allow multiple recipients (chip-style UI)

## 3. Testing

- [x] 3.1 Test API endpoint end-to-end with mcp-gateway
- [x] 3.2 Test web UI autocomplete
- [x] 3.3 Verify graceful degradation when gateway unavailable
