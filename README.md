# Amazon Device Cart Tests

Python Playwright tests for:

- Test Case 1: Search Amazon.com for an iPhone, add a matching item to the cart, and print the price.
- Test Case 2: Search Amazon.com for a Galaxy device, add a matching item to the cart, and print the price.

The test suite is configured to run both cases in parallel with `pytest-xdist`.

## Prerequisites

- Python 3.10+
- Internet access

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

## Run The Tests

```powershell
pytest
```

The selected item title and price are printed to the console for each test case.

## Run On LambdaTest Cloud

Set your LambdaTest credentials, then enable the cloud run:

```powershell
$env:LT_USERNAME="your-lambdatest-username"
$env:LT_ACCESS_KEY="your-lambdatest-access-key"
$env:RUN_ON_LAMBDATEST="true"
pytest
```

Run with the browser visible:

```powershell
$env:HEADLESS="false"
pytest
```

