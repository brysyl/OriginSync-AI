from decimal import Decimal
from uuid import UUID

import httpx

from app.core.errors import ServiceError
from app.core.settings import Settings


class PayPalService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = (
            "https://api-m.sandbox.paypal.com"
            if settings.paypal_environment == "sandbox"
            else "https://api-m.paypal.com"
        )

    async def create_payout(
        self,
        *,
        trade_id: UUID,
        email: str,
        amount: Decimal,
        currency: str,
    ) -> str:
        if self.settings.paypal_client_id is None or self.settings.paypal_client_secret is None:
            raise ServiceError(
                "settlement_not_configured",
                "PayPal settlement credentials are not configured.",
                503,
            )
        auth = (
            self.settings.paypal_client_id.get_secret_value(),
            self.settings.paypal_client_secret.get_secret_value(),
        )
        sender_batch_id = f"originsync-{trade_id}"
        payout_payload = {
            "sender_batch_header": {
                "sender_batch_id": sender_batch_id,
                "email_subject": "OriginSync trade settlement",
                "email_message": "An eligible trade settlement has been initiated.",
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "receiver": email,
                    "amount": {"value": f"{amount:.2f}", "currency": currency},
                    "note": f"OriginSync settlement for trade {trade_id}",
                    "sender_item_id": str(trade_id),
                }
            ],
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=20) as client:
            try:
                token_response = await client.post(
                    "/v1/oauth2/token",
                    auth=auth,
                    data={"grant_type": "client_credentials"},
                    headers={"Accept": "application/json", "Accept-Language": "en_US"},
                )
                token_response.raise_for_status()
                access_token = token_response.json()["access_token"]
                if not isinstance(access_token, str) or not access_token:
                    raise ValueError("PayPal returned an invalid access token")
                headers = {
                    "Authorization": "Bearer " + access_token,
                    "Content-Type": "application/json",
                    "PayPal-Request-Id": sender_batch_id,
                }
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                raise ServiceError(
                    "paypal_authentication_failed",
                    "PayPal did not issue an access token.",
                    502,
                ) from error

            try:
                retrying_after_transport_error = False
                try:
                    response = await client.post(
                        "/v1/payments/payouts",
                        headers=headers,
                        json=payout_payload,
                    )
                except httpx.TransportError:
                    retrying_after_transport_error = True
                    response = await client.post(
                        "/v1/payments/payouts",
                        headers=headers,
                        json=payout_payload,
                    )
                if response.status_code >= 500 or (
                    retrying_after_transport_error and response.status_code >= 400
                ):
                    raise ServiceError(
                        "paypal_payout_outcome_unknown",
                        "PayPal payout outcome is unknown; reconcile using the sender batch id.",
                        503,
                    )
                response.raise_for_status()
                try:
                    batch_id = response.json()["batch_header"]["payout_batch_id"]
                except (KeyError, TypeError, ValueError) as error:
                    raise ServiceError(
                        "paypal_payout_outcome_unknown",
                        "PayPal accepted a payout response without a batch id.",
                        503,
                    ) from error
                if not isinstance(batch_id, str) or not batch_id:
                    raise ServiceError(
                        "paypal_payout_outcome_unknown",
                        "PayPal accepted a payout response without a batch id.",
                        503,
                    )
            except ServiceError:
                raise
            except httpx.TransportError as error:
                raise ServiceError(
                    "paypal_payout_outcome_unknown",
                    "PayPal payout outcome is unknown; reconcile using the sender batch id.",
                    503,
                ) from error
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                raise ServiceError(
                    "paypal_payout_failed",
                    "PayPal did not accept the payout request.",
                    502,
                ) from error
        return batch_id
