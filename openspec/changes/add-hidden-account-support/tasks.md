## 1. Nix Configuration

- [ ] 1.1 Add `hidden` boolean option to accountOption submodule in `modules/home-manager/default.nix`
- [ ] 1.2 Propagate `hidden` setting to account settings in `runtimeConfig` generation

## 2. Backend API - Response Models

- [ ] 2.1 Add `hidden: bool` field to `AccountResponse` model in `src/cairn_mail/api/models.py`

## 3. Backend API - Account Endpoints

- [ ] 3.1 Add `include_hidden: bool = False` query parameter to `GET /accounts` endpoint
- [ ] 3.2 Filter accounts based on `settings.get("hidden", False)` when `include_hidden=False`
- [ ] 3.3 Include `hidden` field in account response serialization

## 4. Backend API - Message Endpoints

- [ ] 4.1 Add `include_hidden_accounts: bool = False` query parameter to `GET /messages` endpoint
- [ ] 4.2 Query hidden account IDs and exclude their messages when `include_hidden_accounts=False`
- [ ] 4.3 Skip hidden filtering when explicit `account_id` is provided

## 5. Frontend Types

- [ ] 5.1 Add `hidden?: boolean` field to `Account` interface in `web/src/api/types.ts`

## 6. Frontend API Integration

- [ ] 6.1 Update `useAccounts` hook to use default filtering (hidden accounts excluded)
- [ ] 6.2 Update message query to exclude hidden account messages by default

## 7. Testing

- [ ] 7.1 Test Nix config generates correct settings for hidden accounts
- [ ] 7.2 Verify hidden accounts are excluded from default `/accounts` response
- [ ] 7.3 Verify hidden account messages are excluded from default `/messages` response
- [ ] 7.4 Verify `include_hidden=true` returns hidden accounts
- [ ] 7.5 Verify explicit `account_id` filter works for hidden accounts
