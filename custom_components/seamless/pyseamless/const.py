"""Constants for the pyseamless client."""

BASE_URL = "https://api-gtm.grubhub.com"
BRAND = "SEAMLESS"
USER_AGENT = "Seamless/2026.42 (iPhone; iOS 27.0.1; Scale/3.00)"

REQUEST_TIMEOUT_SECONDS = 20
TOKEN_REFRESH_MARGIN_SECONDS = 300
ORDER_LIST_PAGE_SIZE = 10
ORDER_STATUS_VARIATIONS = (
    "use_new_order_status,courierIsArriving,courierDropoffArrived,"
    "expected_delivery_path_v2,use_self_delivery_statuses"
)
