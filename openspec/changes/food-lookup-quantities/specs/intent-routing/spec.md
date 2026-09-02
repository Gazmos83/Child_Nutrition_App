## ADDED Requirements

### Requirement: A quantified single-food question routes to the food lookup with its amount

When the parent asks about the nutrients of one food, the router SHALL invoke the food
lookup with the food's name alone as the food argument — never an amount or the question's
wording — and, when the parent names an amount, SHALL pass it as a separate quantity with
its unit. The answer SHALL state the figures for the requested amount when the tool returns
them and the per-serving figures otherwise, naming the serving; the model SHALL NOT scale
between the two itself.

#### Scenario: Food with an amount

- **WHEN** the parent asks "what are the nutritional values for 20 g of sweet potato"
- **THEN** the food lookup runs with a food argument naming only the sweet potato and a
  quantity of 20 with unit `g`
- **AND** the answer leads with the figures the tool returned for 20 g

#### Scenario: Food without an amount

- **WHEN** the parent asks "what's in a serving of avocado"
- **THEN** the food lookup runs with no quantity
- **AND** the answer gives the per-serving figures and names the serving size

#### Scenario: Several foods with amounts

- **WHEN** the parent asks about "150 ml of formula plus 30 g of cereal"
- **THEN** the meal-nutrition tool runs with one item per food, each carrying its own
  quantity and unit
