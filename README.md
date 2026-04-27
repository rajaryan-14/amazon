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

`pytest.ini` runs the suite with two workers by default:

```text
-n 2
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

Optional LambdaTest capability overrides:

```powershell
$env:LT_BROWSER="Chrome"
$env:LT_BROWSER_VERSION="latest"
$env:LT_PLATFORM="Windows 10"
$env:LT_BUILD="Amazon Device Cart Tests"
pytest
```

## Useful Options

Run with the browser visible:

```powershell
$env:HEADLESS="false"
pytest
```

Override the default search terms:

```powershell
$env:IPHONE_QUERY="Simple Mobile iPhone"
$env:GALAXY_QUERY="Samsung Galaxy unlocked smartphone"
pytest
```

Override the Amazon delivery ZIP used for the run:

```powershell
$env:AMAZON_ZIP="10001"
pytest
```

Use a different browser supported by Playwright:

```powershell
$env:BROWSER="firefox"
python -m playwright install firefox
pytest
```

## Notes

Amazon pages, product availability, and add-to-cart controls can change by region and session. The tests default to ZIP `10001` so Amazon.com exposes US add-to-cart controls. If Amazon presents a CAPTCHA or bot-check page, the tests stop with a clear failure message so the run does not produce misleading results.
