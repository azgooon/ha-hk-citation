# HK Citation Health Monitor

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant integration that automatically discovers and monitors
[Harman Kardon Citation](https://www.harmankardon.com/) speakers on your network.

## What it does

HK Citation speakers are known to freeze due to Google Assistant issues.
This integration detects frozen speakers by measuring HTTP POST response times
against two diagnostic endpoints. Healthy speakers respond in <200ms;
frozen ones take 2-5+ seconds.

Each discovered speaker gets a **binary sensor** (Connected / Disconnected)
that you can use in automations — for example, to power-cycle a smart plug
when a speaker is detected as frozen.

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add this repository URL, category: **Integration**
4. Search for "HK Citation Health Monitor" and install
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → Add Integration → HK Citation Health Monitor**

### Manual

Copy `custom_components/hk_citation/` to your HA `custom_components/` directory
and restart Home Assistant.

## Configuration

The integration requires no configuration. It automatically discovers
HK Citation speakers via mDNS.

### Options

After setup, click the gear icon on the integration to adjust:

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| Scan interval | 300s (5 min) | 60–3600s | How often to scan and health-check |
| Health threshold | 1000ms | 200–10000ms | Response time above this = frozen |

## Entities

Each speaker gets one binary sensor:

- **binary_sensor.\<name\>_health** — `Connected` (healthy) / `Disconnected` (frozen)

### Attributes

| Attribute | Description |
|-----------|-------------|
| `response_time_ms` | Worst response time from last check |
| `ip_address` | Current IP address |

## How it works

Every scan interval, the integration:

1. Runs an mDNS scan for `_googlecast._tcp.local.` services
2. Filters to devices whose model starts with "HK Citation"
3. Sends two HTTP POST probes to each speaker on port 8008
4. Marks speakers as frozen if either probe exceeds the threshold

Two endpoints are probed because different frozen states cause slowness
on different endpoints — a single probe would miss some frozen speakers.
