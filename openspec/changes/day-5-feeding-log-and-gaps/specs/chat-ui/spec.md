## ADDED Requirements

### Requirement: The parent can log feeds and see today's intake

The UI SHALL provide a Feeding-log tab with a form to log a feed (feeding type from the
controlled vocabulary; a food picker offering only foods from the food table, filtered to
milk feeds for breast milk and formula and hidden for water; quantity with the unit set
from the chosen food; time defaulting to now), a list of logged entries grouped by day
with their nutrients and a way to delete one, and "today so far" totals. The log SHALL be
kept in the browser for fourteen days and sent with every message.

#### Scenario: Picker offers only table foods

- **WHEN** the parent logs a solid
- **THEN** the food choices are exactly the foods returned by the food listing, and no
  free-text food can be entered

#### Scenario: Entry appears with nutrients

- **WHEN** the parent logs 150 ml of formula
- **THEN** the entry appears under today with about 100 kcal and today's totals increase
  accordingly

#### Scenario: Log survives a reload

- **WHEN** the parent reloads the page
- **THEN** entries from the last fourteen days are still listed

### Requirement: Gap reports render as a structured card

When a response includes a gap report the UI SHALL render a card showing the confidence
(or that not enough days are logged), the number of complete days and the window, each
nutrient's average against its target with a `below`/`adequate`/`above` indication, the
targets' sources, and the doctor's-note conflict banner when the report shows one.

#### Scenario: Insufficient data

- **WHEN** the report's status is `insufficient_data`
- **THEN** the card says, warmly, that a few full days of feeds are needed before patterns
  can be seen, invites the parent to keep logging, and shows no flags

#### Scenario: Medium-confidence iron gap

- **WHEN** the report flags iron `below` at `medium` confidence over three days
- **THEN** the card shows the confidence, "3 full days", iron marked "a little short of
  target", and a note that this is an average and a nudge toward iron-rich foods, not a
  verdict

#### Scenario: Excluded days are explained without blame

- **WHEN** the report excluded days because of an unmeasured breastfeed
- **THEN** the card says how many days were left out and that this is normal, not a problem

### Requirement: The meal-plan card shows what informed an adjustment

When a plan carries adjustments or already-logged intake the meal-plan card SHALL show
which nutrient it was adjusted for and why, the already-logged totals, and — for the
`targets_met` outcome — a statement that today's logged feeds already meet the targets.

#### Scenario: Adjusted plan

- **WHEN** the plan's adjustments name iron
- **THEN** the card shows an "adjusted for iron" line with the reason

#### Scenario: Targets met

- **WHEN** the plan's outcome is `targets_met`
- **THEN** the card shows that today is already covered and there is nothing more to plan,
  no items, and the disclaimer

#### Scenario: Empty log invites, not nags

- **WHEN** the Feeding-log tab has no entries
- **THEN** it shows one warm sentence inviting the parent to add a feed whenever they like
  and explaining that more days mean more insight, plus a note that the log is kept in this
  browser for fourteen days
