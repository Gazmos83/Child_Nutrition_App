## MODIFIED Requirements

### Requirement: `lookup_food` and `calculate_meal_nutrition` read only from the food-composition table

`lookup_food` SHALL return a food's nutrient and safety record by identifier or by the
food's common name as the parent said it, resolved deterministically by the
food-composition table's resolution rules — never by language-model guessing. It SHALL
accept an optional quantity and unit (`g` or `ml`); when a quantity is given the result SHALL
also carry the nutrients for exactly that amount, computed in code as the quantity divided
by the table serving size times the per-serving values, alongside the per-serving record. A
unit that contradicts the food's table unit SHALL be refused naming the food's unit; a
quantity without a unit SHALL be read in the food's own unit and the unit used SHALL be
echoed in the result. `calculate_meal_nutrition` SHALL sum the nutrient values of a list of
foods and quantities, using only values present in the food-composition table, accepting
each food by identifier or common name under the same resolution rules, and accepting each
item's amount either as servings (multiples of the table serving) or as a quantity with unit
under the same rules. A string the table refuses to resolve SHALL surface as the tool's
not-found outcome with the string preserved as given.

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

#### Scenario: Lookup with a quantity scales deterministically

- **WHEN** `lookup_food` is called with "sweet potato", quantity 20 and unit `g`, and the
  entry's serving is 60 g
- **THEN** the result carries the per-serving record and, separately, the nutrients for
  20 g equal to the per-serving values times 20/60
- **AND** the result echoes the requested quantity and unit

#### Scenario: Quantity in the wrong unit is refused

- **WHEN** `lookup_food` is called with a food measured in grams and a quantity in `ml`
- **THEN** the call fails naming the food and that it is measured in grams
- **AND** no nutrient figures are returned

#### Scenario: Meal item by quantity

- **WHEN** `calculate_meal_nutrition` is called with an item giving 150 ml of a food whose
  serving is 100 ml
- **THEN** the item counts as 1.5 servings in the totals
