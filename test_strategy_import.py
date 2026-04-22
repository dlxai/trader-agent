#!/usr/bin/env python3
import sys
import os

# Add the backend-py src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'packages/backend-py'))
sys.path.insert(0, os.path.dirname(__file__))

try:
    from src.models.strategy import Strategy
    print("OK: Successfully imported Strategy model")

    # Check if all new fields exist
    new_fields = [
        'provider_id', 'system_prompt', 'custom_prompt', 'data_sources',
        'min_order_size', 'max_order_size', 'market_filter_days',
        'market_filter_type', 'run_interval_minutes', 'last_run_at', 'total_runs'
    ]

    for field in new_fields:
        if hasattr(Strategy, field):
            print(f"OK: Field {field} exists")
        else:
            print(f"ERROR: Field {field} missing")

except Exception as e:
    print(f"ERROR: Failed to import Strategy model: {e}")
    import traceback
    traceback.print_exc()