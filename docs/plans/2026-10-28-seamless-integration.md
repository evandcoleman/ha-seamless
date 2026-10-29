# Seamless integration: implementation plan

The spec, `docs/specs/2026-10-28-seamless-integration.md`, wins on conflict.

> **Superseded in part (2026-10-28):** step 0 found that scripted login is blocked by PerimeterX. The login, anonymous-auth and email/password config-flow parts below were replaced by pasted-refresh-token setup. See the spec's Auth section and commit 2de698d.

**Target:** HA 2026.10. `pytest-homeassistant-custom-component==0.13.375` pins `homeassistant==2026.10.4` and needs Python 3.14.

## What the captures show (shapes only)

**Login response**
- `credential.ud_id`, plus `session_handle.{access_token, refresh_token, token_remaining_secs, refresh_token_remaining_secs}`.
- `expire_in` and `refresh_expire_in` are in **minutes**. Use `token_remaining_secs` for expiry.
- Anonymous `POST /auth` and refresh `POST /auth` return the same top-level keys (`credential`, `claims`, `session_handle`). Verified by a live probe: refresh **rotates** the refresh token.

**Order list `results[]`**
- `id`, `order_number`, `order_status`, `time_placed` (ISO `Z`), `restaurants[].name`, `order_tracking.enabled`, `when_for`, `scheduled`.
- `order_status` values seen: `CONFIRMED`, `OUT_FOR_DELIVERY`, `FULFILLED`.
- `results[].state` reads `COMPLETED` on **every** order, including live ones, so it is useless. Use `order_status`.
- Orders with tracking disabled stay `CONFIRMED` for 10+ hours. Only the 4 h window retires them.
- The list comes back newest first.

**order-status**
- `order_tracking.state`, `current_eta_state` (uppercase, e.g. `ON_TIME`).
- `display_estimate_range.{single_estimate_time,start_time,end_time}`.
- `dropoff_pin_code`.
- `delivery_tracking_info.courier.{name,vehicle_type,photo_url}`.
- `delivery_tracking_info.current_courier_location.{latitude,longitude,bearing,timestamp}`.

**User-Agent:** `Seamless/2026.42 (iPhone; iOS 27.0.1; Scale/3.00)`.

## HA API notes (core 2026.10.4)

- **Coordinator:** `DataUpdateCoordinator(hass, logger, config_entry=entry, …)`. `update_interval` can be set at runtime.
- **TrackerEntity:** import from `homeassistant.components.device_tracker`. Don't use `_attr_location_name` (deprecated). For `not_home` with no coordinates, set `_attr_in_zones = []`.
- **ImageEntity:** call `ImageEntity.__init__(hass)` as well as the coordinator init. Clear `_cached_image` when the URL changes.
- **Reauth:** `async_step_reauth` → `reauth_confirm`, using `_get_reauth_entry()`, `_abort_if_unique_id_mismatch()` and `async_update_reload_and_abort(data_updates=…)`.
- **ENUM sensors:** HA raises `ValueError` for states outside `options`, so `options` must add the current value at runtime when it's new.

## Resolved decisions

1. **Reauth** asks for email and password. Entry data stays exactly `{ud_id, device_id, refresh_token}`.
2. **order-status 4xx for the active order:** fail soft. Status is `None`, entities show `unknown`, and polling continues.
3. **Scheduled orders:** follow the spec's rule (4 h window from `time_placed`). Revisit after E2E.
4. **docs/ ships in the public repo.** The owner's name has been scrubbed. The PII scan covers `docs/`.
5. **CI:** copy the reference Validate workflow verbatim. A pytest job is a follow-up.
6. **Commit identity:** the noreply GitHub address (already set).

## Steps

### 0. Login probe (gate; kept outside the repo)

**Files**
- `probe.py` in a scratch directory outside the repo.
- `probe.env`, holding only `op://Olympus/Seamless/username` and `op://Olympus/Seamless/password` references.

**What it does**
- Uses aiohttp, a fresh uuid4 `device_id`, and only the User-Agent, Accept, Content-Type and Authorization headers.
- Call sequence:
  1. Anonymous `/auth`.
  2. `/auth/login` with the spec's body.
  3. One refresh.
  4. `search_listing`.
  5. order-status, only if the newest order isn't terminal.
  6. `/auth` with a junk refresh token, to record the failure status code.
- Output: one line per call with method, masked path, status, and **keys and types only**, plus `rotated=<bool>`.
- It never prints values, never retries, and stops at the first unexpected non-2xx.

**Verify:** `op run --env-file=probe.env -- uv run --with aiohttp python -I probe.py`, then `git -C <repo> status --porcelain` must be empty.

**Pass:** login 200 with `credential.ud_id` and `session_handle.refresh_token`, and a refresh 200 with `rotated=True`.

**Fail:** stop and report. Don't try header or body variants. Step 6 then gains the spec's paste-a-refresh-token fallback.

**Blocked until** the owner adds the `Seamless` item to 1Password. Steps 1–5 may proceed first; only step 6 depends on the result.

### 1. Scaffold and test harness

**Files**
- `.gitignore`: add `*.py[cod]` and `.pytest_cache/`.
- `hacs.json`: `{"name":"Seamless","render_readme":true,"homeassistant":"2026.10.0"}`.
- `manifest.json`: domain `seamless`, `config_flow`, `cloud_polling`, no requirements, `0.1.0`, codeowners `@evandcoleman`, and doc and issue URLs for `evandcoleman/ha-seamless`.
- `const.py` and `__init__.py`.
- `requirements_test.txt`: phcc `0.13.375`, `aioresponses==0.7.9`.
- `pyproject.toml`: `asyncio_mode = "auto"`.
- `tests/conftest.py`: autouse `enable_custom_integrations`.
- `.github/workflows/validate.yml`: copied from `evandcoleman/ha-buildinglink`.

**Failing tests**
- `tests/test_init.py::test_integration_loads`.
- `tests/pyseamless/test_harness.py`: aioresponses intercepts a plain `ClientSession`. Delete it after step 4.

**Verify**
```
uv venv --python 3.14 .venv
uv pip install -p .venv -r requirements_test.txt
.venv/bin/pytest -q tests/test_init.py tests/pyseamless/test_harness.py
```

### 2. Synthetic fixtures (no PII by construction)

Fixtures are written by hand from key and type knowledge. **They are never produced by transforming HAR data.**

**Fixed synthetic values**

| Field | Value |
|---|---|
| IDs | `00000000-0000-4000-8000-0000000000NN` (ud_id `…01`, device `…d1`; orders `…a1` active, `…a2` old, `…a3` delivered) |
| `order_number` | `TEST-0001` |
| Restaurant / courier | `Test Kitchen` / `Test Courier`, vehicle `car` |
| Photo URLs | `https://example.com/courier-1.jpg`, `-2.jpg` |
| Address | `1 Example Plaza, New York, NY 10036` |
| Email / phone / PIN | `diner@example.com` / `+1 555 0100` / `0000` |
| Coordinates | Times Square `40.7580, -73.9855` (courier within 0.005°) |
| Tokens | `test-access-1`, `test-refresh-1`, `test-refresh-2` |
| Clock | frozen at `2026-01-15T18:00:00Z` |

**Files**
- Auth: `auth_anonymous.json`, `auth_login.json`, `auth_refresh.json`.
- Order lists:
  - `orders_active.json`: newest `OUT_FOR_DELIVERY` at 17:30Z, plus an old `CONFIRMED` with tracking disabled. Every order has `state: COMPLETED`.
  - `orders_idle.json`: newest `FULFILLED`.
  - `orders_stale.json`: newest `CONFIRMED`, 6 h old.
  - `orders_empty.json`.
- Order status:
  - `status_out_for_delivery.json`.
  - `status_out_for_delivery_moved.json`: new location and new photo URL.
  - `status_delivered.json`.
  - `status_minimal.json`: only `order_id`.
  - `status_unknown_state.json`: `TELEPORTING`.
- `tests/fixtures/README.md` stating that every fixture is synthetic.

**Failing test:** `tests/test_fixtures_synthetic.py` is a permanent guard. It checks that:
- every UUID has the synthetic prefix;
- every email ends in `@example.com`;
- every coordinate is within 0.01° of Times Square;
- every `*token*` value starts with `test-`;
- every URL host is `example.com`.

### 3. `pyseamless` models and exceptions

**Rules:** no HA imports. `from_dict` fails soft: a missing or malformed field becomes `None`.

**Exceptions:** `SeamlessError`, `AuthenticationError`, `ApiError(status)`, `SeamlessConnectionError`.

**Models:** frozen dataclasses.
- `TokenSet(access_token, refresh_token, expires_at)`, built by `from_session_handle(d, now)`.
- `LoginResult(ud_id, tokens)`.
- `OrderSummary(id, order_number, order_status, time_placed, restaurant_name, tracking_enabled)`.
- `Courier`, `CourierLocation`.
- `OrderStatus(order_id, tracking_state, eta, eta_window_start, eta_window_end, eta_state, courier, location, dropoff_pin)`.
- `parse_orders()` sorts newest first. Datetimes are UTC-aware.

**Failing tests:** `tests/pyseamless/test_models.py`
- List parsing and ordering.
- Every status field.
- Minimal status gives all `None`.
- A bad datetime gives `None`.
- `expires_at` equals `now + token_remaining_secs`.

### 4. `pyseamless` auth

**Interface:** `SeamlessAuth(session, device_id, refresh_token=None, *, on_refresh_token=None, clock=time.time)`
- `async_login(email, password)`: anonymous `/auth`, then `/auth/login` with that Bearer token.
- `async_get_access_token()`: refreshes when 300 s or less remain, under an `asyncio.Lock`.
- `async_force_refresh()` and a `refresh_token` property.
- `on_refresh_token` runs synchronously before returning.

**Failing tests:** aioresponses plus a fake clock
- Exact bodies and headers.
- Login 401/403 raises `AuthenticationError`.
- A refresh rotates the token and fires the callback.
- A token with more than 5 min left is reused; one with 5 min or less is refreshed.
- Refresh 401/403 raises `AuthenticationError`. 5xx raises `ApiError`. A `ClientError` raises `SeamlessConnectionError`.
- Two concurrent callers cause exactly one refresh.

**Constraint:** never test reusing a rotated token against the live API, because reuse detection could revoke the session.

### 5. `pyseamless` client

**Interface:** `SeamlessClient(session, auth, ud_id)` with `async_get_orders()` and `async_get_order_status(order_id)`. Query strings match the spec exactly; each request uses a `ClientTimeout`.

**Failing tests**
- Exact URLs and params.
- Responses are parsed.
- 401, then one refresh, then a successful retry.
- 401, refresh, 401 again raises `AuthenticationError`.
- 5xx raises `ApiError`.
- A timeout raises `SeamlessConnectionError`.
- order-status 4xx (not 401/403) returns `None` (decision 2).

### 6. Config flow (user and reauth)

**Files:** `config_flow.py`, `strings.json`, `translations/en.json` (identical). The session comes from `async_get_clientsession`.

**User step:** email and password → `async_login` → `async_set_unique_id(ud_id)` → abort if already configured → create an entry titled `Seamless` whose data is exactly `{ud_id, device_id, refresh_token}`.

**Reauth step:** email and password. Reuse `device_id`, run `_abort_if_unique_id_mismatch`, then `async_update_reload_and_abort(data_updates={refresh_token})`.

**Failing tests**
- Success: entry data keys are exactly those three, with no password or email.
- `invalid_auth`, `cannot_connect`, `already_configured`.
- Reauth success.
- Reauth with a different account aborts with `unique_id_mismatch`.

If step 0 failed, add the paste-refresh-token step and its tests here.

### 7. Coordinator, setup and unload

**Constants:** `IDLE_INTERVAL` 5 min, `ACTIVE_INTERVAL` 30 s, `ACTIVE_WINDOW` 4 h. `TERMINAL_STATUSES` = {`FULFILLED`, `DELIVERED`, `CANCELLED`, `COMPLETED`}, applied to `order_status` and to `order_tracking.state` only, never to `results[].state`.

**Pure helpers:** `select_order(orders, now)` and `is_active(order, recorded_terminal_id)`.

**`SeamlessCoordinator(hass, entry, client)` and frozen `SeamlessData(order, status, is_active)`**
- While active and inside the window, fetch order-status only.
- Otherwise fetch the list. If an order is now active, fetch its status in the same update.
- Record the ID of any order that reaches a terminal state, and never reactivate it.
- Keep showing the status until the window ends, and set `update_interval` from the mode.
- `AuthenticationError` becomes `ConfigEntryAuthFailed`; any other `SeamlessError` becomes `UpdateFailed`.

**`__init__.py`**
- `type SeamlessConfigEntry = ConfigEntry[SeamlessCoordinator]`.
- Wire `on_refresh_token` to `async_update_entry(data={**entry.data, "refresh_token": new})`.
- Register **no update listener**; a reload would loop on every rotation.
- Order: first refresh, then `runtime_data`, then forward platforms. Unload them on unload.

**Failing tests:** `freezer`, `async_fire_time_changed` and request counts
1. Idle polls every 5 min.
2. An active order switches to 30 s polling of status only.
3. A delivered status drops back to 5 min and the status stays visible.
4. The order clears after 4 h.
5. A stale `CONFIRMED` order isn't active.
6. `state: COMPLETED` alone isn't terminal.
7. A lagging list doesn't reactivate a finished order.
8. The rotated token is saved.
9. A refresh 401 starts reauth.
10. A 5xx sets `last_update_success` to false.
11. A network error during setup gives `SETUP_RETRY`.
12. Unload works.

### 8. Base entity, sensors and binary sensor

**Base entity:** `entity.py` uses `has_entity_name` and unique ID `{entry.unique_id}_{key}`. One `DeviceInfo` "Seamless" with entry type SERVICE.

**Sensors:** description-driven, matching the spec table.
- `order_status` and `eta_state` are lowercased ENUMs with dynamic `options`.
- Three TIMESTAMP sensors for the ETA.
- `restaurant`, `courier` (attribute `vehicle_type`) and `dropoff_pin`.

**Binary sensor:** `order_active`, with attributes `order_id` and `order_number`.

**Translations:** keys go in both string files.

**Failing tests**
- Entity IDs match the spec.
- With no order, the binary sensor is `off` and every sensor is `unknown`.
- Active values are correct.
- `TELEPORTING` shows as `teleporting` with no error.
- The minimal status gives `unknown`.
- A coordinator failure gives `unavailable`.

### 9. Device tracker and image

**Tracker:** GPS source. With no location, `_attr_in_zones = []` (so `not_home`); otherwise `None`. Attributes: `bearing`, `timestamp`.

**Image:** call both inits. When the URL changes, set `image_last_updated` and clear `_cached_image`.

**Failing tests**
- With no order, the tracker is `not_home` with no lat/lon, and the image is `unknown`.
- With an active order, the tracker has lat/lon and attributes.
- The `_moved` fixture updates the tracker.
- `image_last_updated` changes only when the URL changes.
- Tests never fetch real images.

### 10. Diagnostics

Required by the spec's Privacy section.

**Implementation:** `async_redact_data` over `email`, `phone`, `refresh_token`, `access_token`, `dropoff_pin`, `latitude`, `longitude`, `address`, `ud_id`, `device_id`, `photo_url` and `name`.

**Failing test:** each key reads `**REDACTED**`, and no synthetic token or PIN appears anywhere in the dump.

### 11. README and validation

TDD exception: docs and config.

**README:** HACS install, entities table, an example automation, and privacy notes.

**Verify**
- hassfest via Docker.
- `python3 -m json.tool` on each JSON file.
- `diff strings.json translations/en.json`.

### 12. Integration gate

Check the load average first. Above about 30, run only targeted tests and defer the full run.

**Verify**
- Full pytest with `--durations=10`. Wrap it in `heavy` only if it runs long.
- No test takes over 1 s.
- No `asyncio.sleep` or `time.sleep` in tests.

### 13. PII scan (blocks any push)

**Script:** `pii_scan.py`, kept in a scratch directory outside the repo.

**In-memory denylist from `captures/*.har`**
- Every value of the PII keys: email, phone, names, all IDs and UUIDs, order numbers, tokens, password, PIN, photo URLs, IP and address fields.
- The PX, `x-gh-*`, cookie and authorization headers.
- Every coordinate, rounded to 3 decimals.

**Generic patterns**
- Emails other than `@example.com` and `@users.noreply.github.com`.
- JWTs, phone numbers, and IPv4 addresses other than loopback.
- UUIDs without the synthetic prefix.
- A name list kept in the script.

**Scope and output**
- Scans tracked files, `git log -p --all`, commit identities, and untracked non-ignored files.
- `git ls-files captures` must be empty.
- Reports `file:line` and the key name only, never the value. Exits non-zero on any hit.

### 14. End to end on the owner's HA

1. Copy the component in. **Restarting HA needs the owner's confirmation.**
2. With no order, check the idle state.
3. Watch the entities through a real order. Record every status value seen and extend `TERMINAL_STATUSES` and the enum options test-first.

### 15. Publish

1. Create `evandcoleman/ha-seamless` as private and push.
2. Confirm Validate is green.
3. Re-run step 13 on a fresh clone.
4. Make the repo public. The owner approved public on 2026-10-28, conditional on a clean PII scan.

## Risks

1. **Login refusal.** Login may be refused without PX headers or fraud-SDK fields. Step 0 is the gate; the fallback is pasting a refresh token.
2. **Lost token rotation.** A crash between rotation and save loses the session; the spec accepts this.
3. **Older HA.** `in_zones` needs HA 2026.7 or later, so `hacs.json` pins 2026.10.0.
4. **Sign-in email.** The probe login may send the owner a "new sign-in" email.
5. **Courier photo URL.** It may expire or need auth. E2E will show.
6. **Test library compatibility.** aioresponses may not work with HA's aiohttp. The step 1 harness test catches it.
