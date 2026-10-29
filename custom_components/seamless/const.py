"""Constants for the Seamless integration."""

from datetime import timedelta

DOMAIN = "seamless"

CONF_UD_ID = "ud_id"
CONF_CLIENT_ID = "client_id"
CONF_DEVICE_ID = "device_id"
CONF_REFRESH_TOKEN = "refresh_token"

IDLE_INTERVAL = timedelta(minutes=5)
ACTIVE_INTERVAL = timedelta(seconds=30)
ACTIVE_WINDOW = timedelta(hours=4)

# Applied to `order_status` (list) and `order_tracking.state` (status) only.
# Never to `results[].state`, which reads COMPLETED on every order.
TERMINAL_STATUSES = frozenset({"FULFILLED", "DELIVERED", "CANCELLED", "COMPLETED"})
