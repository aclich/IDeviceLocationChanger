### Requirement: Parenthesized coordinate input
The coordinate input field SHALL accept coordinates wrapped in parentheses `(lat, lng)` in addition to the existing bare `lat, lng` format.

#### Scenario: User pastes parenthesized coordinates
- **WHEN** user enters `(24.953683, 121.551809)` in the coordinate input
- **THEN** the system SHALL parse it as latitude 24.953683, longitude 121.551809 and set the location

#### Scenario: User enters bare coordinates (existing behavior preserved)
- **WHEN** user enters `24.953683, 121.551809` in the coordinate input
- **THEN** the system SHALL parse and set the location as before

#### Scenario: Parentheses with extra whitespace
- **WHEN** user enters `( 24.953683 , 121.551809 )` in the coordinate input
- **THEN** the system SHALL trim whitespace and parse correctly

### Requirement: Input-group visual association
The Go button SHALL be visually attached to the coordinate input field as a connected input-group, with no gap between them.

#### Scenario: Visual layout
- **WHEN** the user views direct mode controls
- **THEN** the input field and Go button SHALL appear as a single connected control with shared border radius
