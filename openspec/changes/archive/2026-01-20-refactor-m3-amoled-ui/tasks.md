# Implementation Tasks

## 1. Theme & Color System
- [x] 1.1 Update ThemeContext with M3 AMOLED color palette
  - Background: `#000000`
  - Surface Container Low: `#121212` (drawer)
  - Surface Container: `#1E1E1E` (cards)
  - On-Surface Variant: `#CAC4D0` (secondary text)
- [x] 1.2 Create M3 Active Indicator Pill component (Secondary Container color)

## 2. Navigation Drawer
- [x] 2.1 Set Sidebar background to `#121212`
- [x] 2.2 Implement Active Indicator Pill for selected nav items
- [x] 2.3 Update drawer width to 256dp (256px)
- [x] 2.4 Ensure 24dp left margin on content that doesn't shift with drawer toggle

## 3. Email List Cards
- [x] 3.1 Remove all borders from MessageCard component
- [x] 3.2 Set card background to `#1E1E1E`
- [x] 3.3 Set gap/space between cards to `#000000` (parent background)
- [x] 3.4 Apply 12px border-radius and 16px padding to cards

## 4. Typography Hierarchy
- [x] 4.1 Set Sender name to Title Medium (fontWeight: 500)
- [x] 4.2 Set Snippet to Body Small (fontWeight: 400, color: `#CAC4D0`)
- [x] 4.3 Increase header area top padding to 24dp

## 5. Compose FAB
- [x] 5.1 Transform Compose button into Extended FAB component
- [x] 5.2 Apply Primary Container color styling
- [x] 5.3 Position FAB floating bottom-right (mobile)

## 6. App Bar
- [x] 6.1 Set TopBar background to `#000000`
- [x] 6.2 Ensure consistent icon weight for Material Symbols

## 7. Bug Fix: Snippet Sanitization
- [x] 7.1 Create sanitizeSnippet utility function (strip HTML/CSS tags)
- [x] 7.2 Apply sanitization in MessageCard component
- [x] 7.3 Test with emails containing CSS/HTML (e.g., DukemyHR newsletters)

## 8. Testing & Validation
- [x] 8.1 Visual regression check across all views
- [x] 8.2 Verify drawer toggle doesn't shift content alignment
- [x] 8.3 Test on actual AMOLED display for contrast/readability
- [x] 8.4 Verify snippet sanitization works for various HTML email formats

## 9. Additional Improvements (Added During Implementation)
- [x] 9.1 Gmail-style collapsible sidebar (expanded/collapsed rail)
- [x] 9.2 Smooth collapse animation with CSS transitions
- [x] 9.3 Floating Compose FAB (desktop and mobile)
- [x] 9.4 Rename app title to "Cairn Mail"
