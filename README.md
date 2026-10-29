# Seamless for Home Assistant

Track your active [Seamless](https://www.seamless.com) order in Home Assistant: status, ETA, courier, a live courier location on the map, the dropoff PIN and the courier's photo. Good enough to drive automations like "courier arriving, flash the hall light".

> **Unofficial.** This integration uses the same private API as the Seamless mobile app. It is not affiliated with or endorsed by Seamless or Grubhub, and it can break without notice. It is read-only: it cannot place, edit or tip orders.

Requires Home Assistant 2026.10 or newer.

## Install (HACS)

1. In HACS, open the menu, choose **Custom repositories**, add `https://github.com/evandcoleman/ha-seamless` as an **Integration**.
2. Install **Seamless** and restart Home Assistant.
3. Go to **Settings, Devices & services, Add integration, Seamless**. It asks for a refresh token, client ID and device ID (see below).

### Getting the session values

Seamless blocks scripted logins, so Home Assistant never sees your email or password. You hand it a session from a real browser instead:

1. Sign in at [seamless.com](https://www.seamless.com) in a browser.
2. In the browser's developer tools (Network tab), find the `POST /auth/login` response and copy `session_handle.refresh_token`, plus the `client_id` and `device_id` of that session (they are in the request body). The web client's `device_id` is a number.
3. Paste all three into the integration's setup form.
4. **Then close or clear that browser session** (sign out and clear site data) so it does not rotate the same refresh token against Home Assistant.

The refresh token only works with the same client ID and device ID it was issued for. Home Assistant stores the token, which rotates on every refresh. If Seamless ever rejects it, Home Assistant asks for a new one: repeat steps 1 to 4 (the client ID and device ID are reused).

## Entities

Everything lives on one device called **Seamless**.

| Entity | What it shows |
|---|---|
| `binary_sensor.seamless_order_active` | `on` while your newest order is in progress. Attributes: `order_id`, `order_number` |
| `sensor.seamless_order_status` | Tracking state, e.g. `out_for_delivery`, `delivered` |
| `sensor.seamless_eta` | Estimated arrival (timestamp) |
| `sensor.seamless_eta_window_start` / `_end` | Estimated arrival window (timestamps) |
| `sensor.seamless_eta_state` | e.g. `on_time` |
| `sensor.seamless_restaurant` | Restaurant name |
| `sensor.seamless_courier` | Courier name. Attribute: `vehicle_type` |
| `sensor.seamless_dropoff_pin` | Dropoff PIN |
| `device_tracker.seamless_courier` | Courier GPS position. Attributes: `bearing`, `timestamp` |
| `image.seamless_courier_photo` | Courier photo |

With no active order, the binary sensor is `off`, the other order entities are `unknown` and the tracker is `not_home` with no coordinates. If the API is unreachable, entities are `unavailable`.

Unrecognised status values from Seamless are passed through lowercased rather than rejected.

## How it polls

- **Idle:** every 5 minutes, it lists your recent orders.
- **Active:** every 30 seconds, it fetches the live status of the active order.

An order is **active** when it is your newest order, was placed in the last 4 hours, and has not reached a final state. When it finishes, the last status stays visible until the 4 hour window ends, then everything resets to `unknown`.

## Example automation

```yaml
automation:
  - alias: Courier arriving
    triggers:
      - trigger: state
        entity_id: sensor.seamless_order_status
        to: arriving
    actions:
      - action: light.turn_on
        target:
          entity_id: light.hall
        data:
          flash: long
```

Status values come from Seamless and are not documented. Watch `sensor.seamless_order_status` during a real order to see which ones your orders use.

## Privacy

- No password is ever entered or stored. The config entry keeps only `ud_id`, `client_id`, `device_id` and the rotating refresh token.
- Diagnostics redact email, phone, address, tokens, client and device IDs, the PIN, coordinates, names, photo URLs and order identifiers.
- Test fixtures in this repository are synthetic.

## Development

```
uv venv --python 3.14 .venv
uv pip install -p .venv -r requirements_test.txt
.venv/bin/pytest
```

The API client lives in `custom_components/seamless/pyseamless/`. It has no Home Assistant imports and takes an injected `aiohttp.ClientSession`.
