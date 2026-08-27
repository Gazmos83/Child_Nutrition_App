## ADDED Requirements

### Requirement: Feeding-log tools join the deterministic tool set

The system SHALL expose `log_feeding`, `get_daily_nutrition`, `get_remaining_targets`,
and `detect_nutrient_gaps` as deterministic tools with typed, validated inputs, subject to
the same requirements as the existing tools: no language-model arithmetic, validation
before computation, and results that carry their source. `log_feeding` SHALL validate and
normalise an entry and return it with its identifier and table-derived nutrients, and
SHALL NOT persist anything until the feeding-log table ships.

#### Scenario: Ten tools with typed schemas

- **WHEN** the tool set is built
- **THEN** it contains exactly the six existing tools plus the four feeding-log tools, each
  with a typed argument schema

#### Scenario: Invalid entry rejected before computation

- **WHEN** `log_feeding` is invoked with a quantity of zero
- **THEN** the invocation is rejected by validation and no nutrient computation runs

#### Scenario: No model call for totals

- **WHEN** `get_daily_nutrition` is invoked
- **THEN** no language-model call is made
