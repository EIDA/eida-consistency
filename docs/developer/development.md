---
tags:
  - developer
---

# Development

## Quick Start as a Library

To use the tool programmatically, you can import the core checker or the full runner.

### Check a Single Candidate

```python
from eida_consistency.core.checker import check_candidate
from datetime import datetime

# Define a candidate (network, station, channel, starttime)
candidate = {
    "network": "GR",
    "station": "ATH",
    "channel": "BHZ",
    "starttime": "2023-01-01T00:00:00",
    "endtime": "2023-01-02T00:00:00"
}

# Run the check
results, stats = check_candidate(
    base_url="http://node.eida.eu/ fdsnws", # Replace with actual node URL
    candidate=candidate,
    epochs=5,
    duration=600
)

for res in results:
    url, available, start, end, loc, span = res
    print(f"Time: {start} -> Available: {available}")
```

### Run a Full Consistency Check

```python
from eida_consistency.runner import run_consistency_check

# Run check for a specific node
report_path = run_consistency_check(
    node="NOA",
    epochs=10,
    duration=600
)

print(f"Report generated at: {report_path}")
```

## Source

The code, including the docstrings of `eida_consistency.core.checker` and `eida_consistency.runner`, is at https://github.com/EIDA/eida-consistency.
