# deterministic-nutrient-tools — delta for food-name-resolution

## MODIFIED Requirements

### Requirement: `lookup_food` and `calculate_meal_nutrition` read only from the food-composition table

`lookup_food` SHALL return a food's nutrient and safety record by identifier or by the
food's common name as the parent said it, resolved deterministically by the
food-composition table's resolution rules — never by language-model guessing.
`calculate_meal_nutrition` SHALL sum the nutrient values of a list of foods and
quantities, using only values present in the food-composition table, accepting each
food by identifier or common name under the same resolution rules. A string the table
refuses to resolve SHALL surface as the tool's not-found outcome with the string
preserved as given.

#### Scenario: Meal nutrition sums correctly

- **WHEN** `calculate_meal_nutrition` is called with two foods and their quantities
- **THEN** the returned totals equal the sum of each food's nutrients scaled by quantity

#### Scenario: Unknown food in a meal is reported, not silently skipped

- **WHEN** `calculate_meal_nutrition` is called with a food identifier not in the table
- **THEN** the call reports which identifier was not found
- **AND** does not silently omit it from the total without reporting it

#### Scenario: Lookup by common name

- **WHEN** `lookup_food` is called with "bananas" and the table's only banana entry is
  `banana_mashed`
- **THEN** the tool returns the `banana_mashed` record with its nutrients, safety flags,
  and source

#### Scenario: Meal item by common name

- **WHEN** `calculate_meal_nutrition` is called with an item naming "bananas"
- **THEN** the item is resolved and counted in the totals

#### Scenario: Ambiguous name fails the lookup rather than guessing

- **WHEN** `lookup_food` is called with a name matching more than one table entry
- **THEN** the call fails as not-found, naming the candidate entries
- **AND** no entry is silently chosen
