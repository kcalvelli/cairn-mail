# Web UI Capability Delta

## MODIFIED Requirements

### Requirement: Application displays logo in topbar

The topbar MUST display the cairn-mail logo for brand identity.

#### Scenario: Logo is visible in topbar
Given: The user views any page in the application
When: They look at the topbar
Then: The cairn-mail logo is visible on the left side

#### Scenario: Logo links to home
Given: The logo is displayed in the topbar
When: The user clicks the logo
Then: They are navigated to the home page (/)

#### Scenario: Logo has alt text
Given: The logo is displayed
When: A screen reader reads the page
Then: The logo has appropriate alt text "Cairn AI Mail"

#### Scenario: Logo adapts to theme
Given: Either light or dark theme is active
When: The logo is displayed
Then: The logo is visible with sufficient contrast

### Requirement: Sidebar and topbar have consistent styling

The sidebar and topbar MUST have matching background colors for visual consistency.

#### Scenario: Light theme consistent colors
Given: Light theme is active
When: The user views sidebar and topbar
Then: Both have the same primary background color

#### Scenario: Dark theme consistent colors
Given: Dark theme is active
When: The user views sidebar and topbar
Then: Both have the same primary background color (dark variant)

#### Scenario: Visual hierarchy maintained
Given: Consistent navigation colors
When: The user views the application
Then: Content area is visually distinct from navigation areas

### Requirement: Classification confidence is displayed

Message classifications MUST show a visual confidence indicator.

#### Scenario: High confidence display
Given: A message is classified with confidence >= 0.8
When: The message is displayed in the list or detail view
Then: A green confidence indicator is shown (or no indicator for clean UI)

#### Scenario: Medium confidence display
Given: A message is classified with confidence 0.5-0.8
When: The message is displayed
Then: A yellow confidence indicator is shown with "Uncertain" tooltip

#### Scenario: Low confidence display
Given: A message is classified with confidence < 0.5
When: The message is displayed
Then: A red confidence indicator is shown with "Low confidence" tooltip

#### Scenario: Confidence tooltip provides context
Given: A confidence indicator is displayed
When: The user hovers over it
Then: A tooltip shows the numeric confidence value and explanation
