# Change: Add AI-Powered Smart Replies

## Why

Users often need to quickly respond to emails with short, common replies. Manually typing these repetitive responses takes time and interrupts workflow. By leveraging the existing local AI infrastructure (Ollama), we can generate contextually appropriate reply suggestions that users can select with a single click.

## What Changes

- **New Backend Endpoint**: `GET /api/messages/{id}/smart-replies` - Generates 3-4 short reply suggestions based on message content
- **New Frontend Component**: `SmartReplies` - Displays reply suggestions as clickable chips below the message body
- **Updated Compose Page**: Accept `body` query parameter to pre-populate editor content
- **New AI Prompt**: Reply generation prompt that produces concise, professional responses

## Impact

- Affected specs: `ai-features` (new capability)
- Affected code:
  - `src/cairn_mail/api/routes/messages.py` - New endpoint
  - `src/cairn_mail/ai_classifier.py` - New reply generation method (or separate module)
  - `web/src/pages/MessageDetailPage.tsx` - Add SmartReplies component
  - `web/src/pages/Compose.tsx` - Handle `body` query param
  - `web/src/components/SmartReplies.tsx` - New component

## User Stories

1. As a user viewing an email, I want to see AI-generated reply suggestions so I can quickly respond without typing
2. As a user, I want to click a suggested reply to open the compose page with that reply pre-filled
3. As a user, I want the suggestions to be contextually relevant to the email I'm reading
4. As a user, I want the option to not use smart replies if I prefer to write my own response

## Non-Goals

- Real-time streaming of reply generation (keep it simple with full response)
- Learning from user corrections (future enhancement)
- Multi-language reply generation (follow system language)
- Reply suggestions for all message types (focus on messages that warrant replies)
