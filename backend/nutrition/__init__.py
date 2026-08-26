"""Deterministic nutrition data and rules (Day 4).

This package is the layer hard rule 4 requires to be independent of the RAG and LLM
pipeline: it imports no LangChain module and makes no network call. It holds the curated
food-composition table, the DRI target formulas, the diet-preference exclusions, and the
infant-safety filter. ``backend.tools`` wraps these as callables for the model.
"""
