# Seamless order tracking for Home Assistant — spec

Date: 2026-10-28 · Status: draft, awaiting approval

## Goal
A custom HA integration (`seamless`) that shows the owner's active Seamless/Grubhub order in HA: status, ETA, courier details, a courier location on the map, the dropoff PIN, and the courier photo. These should be good enough to drive automations like "courier arriving → flash the hall light".

## Non-goals
Placing, editing or tipping orders. Order history. Multiple simultaneous orders beyond the newest active one. Grubhub-brand accounts (the code should work if `brand` changes, but only Seamless gets tested).

## Layout
Same structure as `evandcoleman/ha-buildinglink`, installed through HACS:

```
custom_components/seamless/
  __init__.py  config_flow.py  const.py  coordinator.py  entity.py
  sensor.py  binary_sensor.py  device_tracker.py  image.py
  manifest.json  strings.json  translations/en.json
  pyseamless/  __init__.py auth.py client.py models.py exceptions.py const.py
hacs.json  README.md  .github/workflows/validate.yml  tests/
```

`pyseamless` is a vendored aiohttp client with no HA imports. The `aiohttp.ClientSession` is injected into it, and it is unit-tested on its own.

## API (verified against app traffic captures and live probes on 2026-10-28)
Base URL `https://api-gtm.grubhub.com`. Every request sends a `Seamless/<ver> (iPhone; …)` User-Agent. No PerimeterX headers are needed for these calls.

| Purpose | Call |
|---|---|
| Anonymous token | `POST /auth` `{brand:"SEAMLESS", client_id, scope:"anonymous", device_id}` |
| Login | `POST /auth/login` with an anonymous Bearer token, body `{email, password, brand, client_id, scope:"diner", device_id, exclusive_session:false}`. The response gives `credential.ud_id` (the diner ID) and `session_handle`. |
| Refresh | `POST /auth` `{brand, client_id, refresh_token, device_id}`. **Rotates the refresh token.** |
| Order list | `GET /diners/{ud_id}/search_listing?facet=orderType:ALL&facet=showCancelled:true&pageNum=1&pageSize=10` |
| Order detail | `GET /diners/{ud_id}/orders/{order_id}/order-status?variation_id=use_new_order_status,courierIsArriving,courierDropoffArrived,expected_delivery_path_v2,use_self_delivery_statuses` |

**Verified 2026-10-28: login is blocked.** Scripted `POST /auth/login` gets a PerimeterX 403, so the integration does not log in. Refresh, the order list and order-status all work without PerimeterX, with either the iPhone or the web client.

The user gets a refresh token by signing in at seamless.com in a real browser and capturing that session. Its refresh token must be used with the **same `client_id` and `device_id`** that session was created with. The web client sends a numeric `device_id` and `client_id` `beta_seamless_…`. A refresh response includes `credential.ud_id`.

## Auth and storage
- The config flow asks for **refresh token, client ID and device ID**. It does one refresh to validate them, takes `ud_id` from the response, and stores `{ud_id, client_id, device_id, refresh_token}` (the rotated token) in the config entry. There is no password and no login call.
- The access token is kept in memory and refreshed when it is within 5 minutes of expiry, or after a 401.
- Each rotated refresh token is written back with `async_update_entry`.
- A refresh that fails with 401/403 raises `ConfigEntryAuthFailed`, which triggers HA's reauth flow (paste a new refresh token; client ID and device ID are pre-filled from the entry).
- The config entry's unique ID is `ud_id`.

## Polling (one DataUpdateCoordinator)
- **Idle:** every 5 minutes, fetch the order list.
- **Active:** every 30 seconds, fetch order-status for the active order.
- An order counts as **active** when it is the newest order in the list, it was placed within the last 4 hours, and its `order_status` is not terminal (`FULFILLED`, `DELIVERED`, `CANCELLED`, `COMPLETED`, …; the real list comes from the captured values plus whatever the implementer observes).
- Once order-status reports a terminal `order_tracking.state`, the coordinator records it, keeps showing it until the active window ends, and drops back to idle polling.
- Network errors and 5xx responses raise `UpdateFailed`, and entities go unavailable. There are no retry loops beyond the coordinator's.

## Entities
One HA device ("Seamless") holds every entity. With no active order, the binary sensor is `off`, the other order entities report `unknown`, and the tracker reports `not_home` with no coordinates.

| Entity | Source | Notes |
|---|---|---|
| `binary_sensor.seamless_order_active` | the active-order rule above | attributes: `order_id`, `order_number` |
| `sensor.seamless_order_status` | `order_tracking.state` | ENUM device class, lowercased, unknown values passed through |
| `sensor.seamless_eta` | `display_estimate_range.single_estimate_time` | TIMESTAMP |
| `sensor.seamless_eta_window_start` / `_end` | `display_estimate_range.start_time` / `end_time` | TIMESTAMP |
| `sensor.seamless_eta_state` | `current_eta_state` (e.g. `on_time`) | ENUM |
| `sensor.seamless_restaurant` | the order's `restaurants[0].name` | |
| `sensor.seamless_courier` | `delivery_tracking_info.courier.name` | attribute: `vehicle_type` |
| `sensor.seamless_dropoff_pin` | `dropoff_pin_code` | |
| `device_tracker.seamless_courier` | `current_courier_location` lat/lon | GPS source; attributes: `bearing`, `timestamp` |
| `image.seamless_courier_photo` | `courier.photo_url` | `image_last_updated` changes when the URL does |

All timestamps are timezone-aware UTC; HA displays them in ET. Entity IDs above are the defaults, generated from `has_entity_name` with translation keys.

## Privacy
- Diagnostics redact email, phone, address, tokens and PIN.
- Test fixtures are synthetic or scrubbed of PII and tokens, never raw HAR data.
- HAR captures stay out of git.

## Testing
- **`pyseamless`:** pytest with `aioresponses`. Covers refresh with rotation, the 401 → refresh → retry path, refresh failure → auth error, and order-list and order-status parsing.
- **Coordinator:** pytest with `pytest-homeassistant-custom-component`. Covers idle → active → terminal → idle transitions, using a fake clock, plus rotated-token persistence and `ConfigEntryAuthFailed` on refresh failure.
- **Config flow:** success, rejected token, cannot connect, reauth.
- **End to end:** install on the owner's HA, check entities with no order, then watch them during a real order.

## Risks
1. **Login is blocked by PerimeterX (confirmed).** Setup takes a pasted refresh token instead. If the browser session the token came from keeps running, the browser and HA will rotate the same token against each other, so the browser must forget the session after the token is captured.
2. **Unofficial API.** It can change without notice. The parsing code fails soft: a missing field gives `unknown`, not a crash.
3. **Refresh-token rotation.** If HA crashes between receiving a rotated token and saving it, the session is lost and you have to re-authenticate. Accepted.

## Distribution
New GitHub repo `evandcoleman/ha-seamless`, installed as a HACS custom repository, the same way as `ha-buildinglink`. Creating the repo and making it public needs the owner's go-ahead (granted 2026-10-28).
