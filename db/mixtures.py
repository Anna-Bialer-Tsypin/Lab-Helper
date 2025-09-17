# File: db/mixtures.py

import json
import os

MIXTURES_DIR = "db/mixtures"
if not os.path.exists(MIXTURES_DIR):
    os.makedirs(MIXTURES_DIR)


def save_mixture(mixture_name: str, mixture_items: list):
    """Saves a mixture to a JSON file."""
    # Create a clean filename
    filename = f"{mixture_name.replace(' ', '_').lower()}.json"
    filepath = os.path.join(MIXTURES_DIR, filename)

    # Prepare the data to be saved
    data = {
        "name": mixture_name,
        "items": mixture_items
    }

    # Write the data to the JSON file
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"Mixture '{mixture_name}' saved to {filepath}")