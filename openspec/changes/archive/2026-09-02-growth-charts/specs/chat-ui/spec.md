## ADDED Requirements

### Requirement: The Growth tab plots each indicator over the WHO percentile curves

When the child has at least one measurement, the Growth tab SHALL show, above the list,
four line charts — weight-for-age, length/height-for-age, weight-for-length/height, and
BMI-for-age. Each chart SHALL draw the WHO curves for the child's sex at every tenth
percentile from the 10th to the 90th as thin muted lines, with the 50th percentile drawn
thicker and darker, SHALL label the 10th, 50th, and 90th curves directly, and SHALL draw
the child's measurements as a line with a marker per measurement in the product's accent
colour. Age charts SHALL span 0–24 months for a child under 24 months and 0–60 months
otherwise; the weight-for-length/height chart SHALL span the table's centimetre range and
say whether it is the length or the height table. A measurement without a length/height
SHALL appear on the weight-for-age chart only. Hovering or focusing a marker SHALL show
the measurement's date, value, and percentile. Axes and grid SHALL be recessive, text SHALL
use the page's text colours (never the series colour), and the charts SHALL render
correctly in the dark theme. All copy SHALL be direct, with no wordplay about weight or
size. The newest-first list beneath the charts remains the table view.

#### Scenario: Four charts with nine curves each

- **WHEN** a child with two measurements, one of them without a length/height, opens the
  Growth tab
- **THEN** four charts render, each with nine percentile curves of which the 50th is
  thicker, the weight-for-age chart shows two markers, and the other three show one

#### Scenario: Curves match the child's sex and age range

- **WHEN** the child is a 7-month-old girl
- **THEN** the age charts span 0–24 months and the weight-for-length/height chart says it
  shows the length table

#### Scenario: Marker tooltip

- **WHEN** the parent hovers a marker on the weight-for-age chart
- **THEN** the measurement's date, weight, and percentile are shown

#### Scenario: No measurements, no charts

- **WHEN** a saved child has no measurements
- **THEN** the tab shows the form and the empty state and no chart

#### Scenario: Curves unavailable does not hide the list

- **WHEN** the reference curves cannot be loaded
- **THEN** the tab says the charts are unavailable and the measurement list still renders
