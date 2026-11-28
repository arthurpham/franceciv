#!/usr/bin/env bash
# Incremental monthly refresh of the sources whose upstream cadence is shortest.
# A monthly Actions cache supplies data/raw and data/interim; the workflow falls back
# to a full pipeline run when that cache is being bootstrapped.
set -euo pipefail
export PYTHONPATH=.
SOURCES=(
  fr_ev_charging
  fr_mobile_network
  fr_electricity
  fr_energy_network
  fr_transit_stops
  fr_transit_frequency
  fr_water_quality
  fr_housing_history
)
BUILDERS=(
  connectivity
  electricity
  energy_system
  transit
  water_circular
  time_dimension
  catalog
  trust
)
uv run python -m pipeline fetch "${SOURCES[@]}"
uv run python -m pipeline process "${SOURCES[@]}"
uv run python -m pipeline build "${BUILDERS[@]}" --force
uv run pytest -q
uv run python -m pipeline check
