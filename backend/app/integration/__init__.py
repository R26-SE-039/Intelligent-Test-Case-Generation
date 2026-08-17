"""Integration API — the read-only contract Component 2 (Test Case Generation)
exposes to other components, currently Component 3 (Failure Analysis & Self-Healing).

Mirrors how Component 1 exposes user stories to us: a clean, documented feed
another service consumes through the API Gateway. No component reaches into
another's database — everyone goes through these endpoints.
"""
