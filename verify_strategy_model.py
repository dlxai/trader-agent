#!/usr/bin/env python3
"""Verify the Strategy model modifications."""
import sys
import os
from pathlib import Path

# Add the backend-py package directory to path
backend_dir = Path(__file__).parent / "packages/backend-py"
sys.path.insert(0, str(backend_dir))

try:
    # Import the models
    from src.models.strategy import Strategy
    from src.models.provider import Provider

    print("Successfully imported all required models")

    # Check if all new columns exist in the model
    expected_fields = [
        # New fields
        'provider_id', 'system_prompt', 'custom_prompt', 'data_sources',
        'min_order_size', 'max_order_size', 'market_filter_days',
        'market_filter_type', 'run_interval_minutes', 'last_run_at', 'total_runs'
    ]

    # Check for expected fields
    print("\nChecking new fields:")
    all_fields_ok = True
    for field in expected_fields:
        if hasattr(Strategy, field):
            print(f"OK: Field '{field}' exists")
        else:
            print(f"ERROR: Field '{field}' missing")
            all_fields_ok = False

    # Check relationships
    expected_relationships = ['provider']
    print("\nChecking relationships:")
    all_rels_ok = True
    for rel in expected_relationships:
        if hasattr(Strategy, rel):
            print(f"OK: Relationship '{rel}' exists")
        else:
            print(f"ERROR: Relationship '{rel}' missing")
            all_rels_ok = False

    # Check Provider model has strategies relationship
    print("\nChecking Provider model reverse relationship:")
    if hasattr(Provider, 'strategies'):
        print("OK: Provider model has 'strategies' relationship")
    else:
        print("ERROR: Provider model missing 'strategies' relationship")
        all_rels_ok = False

    if all_fields_ok and all_rels_ok:
        print("\nAll modifications verified successfully!")
    else:
        print("\nSome modifications failed verification.")

except Exception as e:
    print("\nError during verification: " + str(e))
    import traceback
    traceback.print_exc()