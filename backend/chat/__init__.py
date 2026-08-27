"""The Day 5 chat layer: intent routing, deterministic tool execution, answer composition.

``router`` decides (one model call; the returned tool calls *are* the decision),
``service`` executes and composes, ``prompts`` holds what the model is told, ``copy``
holds what the parent is told, ``wiring`` builds the process-wide service.
"""
