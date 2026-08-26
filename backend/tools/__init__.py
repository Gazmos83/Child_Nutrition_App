"""Callable tools over the deterministic nutrition layer (Day 4).

``nutrient_tools`` -- the five pure functions (BMI, calorie target, protein target, food
lookup, meal nutrition). ``doctors_note`` -- LLM-assisted extraction of a clinician's note
into a bounded override, applied by deterministic code. ``meal_plan`` -- the composed
child-facing recommendation with its audit log. ``langchain_tools`` -- ``StructuredTool``
wrappers for Day 5's router.

Importing this package performs no network access.
"""
