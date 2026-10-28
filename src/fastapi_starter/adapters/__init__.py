"""Adapters: the code that talks to one external service, one folder each.

Each adapter implements ports defined in core (Protocol classes), and only
bootstrap.py builds them. core and features never import an adapter: the
layers contract in pyproject.toml fails the build if they do.
"""
