"""Webhook handler for events."""

import json
import time
from typing import Any, override
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from infrafoundry.core.events.context import EventContext, EventResult
from infrafoundry.core.events.handlers.base import BaseHandler


class WebhookHandler(BaseHandler):
    """Handler that sends event data to a webhook URL.

    Configuration:
        url: Webhook URL to POST to
        headers: Additional HTTP headers (optional)
        timeout: Request timeout in seconds (default: 30)
        include_context: If True, include full context in payload (default: True)

    The webhook receives a JSON payload with:
        - event_type: Event type string
        - environment: Environment name
        - data: Event data
        - provider: Provider name (if applicable)
        - resource: Resource name (if applicable)

    Example config:
        type: webhook
        url: https://hooks.slack.com/services/xxx
        headers:
          Authorization: "Bearer ${SLACK_TOKEN}"
        timeout: 10
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize webhook handler.

        Args:
            config: Handler configuration
        """
        super().__init__(config)

    @override
    def validate_config(self) -> list[str]:
        """Validate handler configuration."""
        errors: list[str] = []

        if "url" not in self.config:
            errors.append("Webhook handler requires 'url' field")

        url = self.config.get("url", "")
        if url and not (url.startswith("http://") or url.startswith("https://")):
            errors.append("Webhook URL must start with http:// or https://")

        timeout = self.config.get("timeout", 30)
        if not isinstance(timeout, int) or timeout < 1 or timeout > 300:
            errors.append("Timeout must be an integer between 1 and 300")

        return errors

    @override
    def execute(self, context: EventContext) -> EventResult:
        """Execute the webhook handler.

        Args:
            context: Event context

        Returns:
            EventResult with webhook response
        """
        url = self.config["url"]
        timeout = self.config.get("timeout", 30)
        headers = self.config.get("headers", {})
        include_context = self.config.get("include_context", True)

        # Build payload
        payload = self._build_payload(context, include_context)

        start_time = time.monotonic()
        try:
            # Prepare request
            data = json.dumps(payload).encode("utf-8")
            req = Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")

            # Add custom headers
            for key, value in headers.items():
                req.add_header(key, value)

            # Send request
            with urlopen(req, timeout=timeout) as response:  # nosec B310 - user-configured URL
                response_body = response.read().decode("utf-8")
                duration = time.monotonic() - start_time

                return EventResult(
                    success=True,
                    stdout=response_body,
                    duration_seconds=duration,
                    handler_name=self.name,
                    data={"status_code": response.status},
                )

        except HTTPError as e:
            duration = time.monotonic() - start_time
            return EventResult(
                success=False,
                reason=f"HTTP error {e.code}: {e.reason}",
                stderr=e.read().decode("utf-8") if e.fp else "",
                duration_seconds=duration,
                handler_name=self.name,
                data={"status_code": e.code},
            )

        except URLError as e:
            duration = time.monotonic() - start_time
            return EventResult(
                success=False,
                reason=f"URL error: {e.reason}",
                duration_seconds=duration,
                handler_name=self.name,
            )

        except TimeoutError:
            duration = time.monotonic() - start_time
            return EventResult(
                success=False,
                reason=f"Request timeout after {timeout} seconds",
                duration_seconds=duration,
                handler_name=self.name,
            )

        except Exception as e:
            duration = time.monotonic() - start_time
            return EventResult(
                success=False,
                reason=f"Webhook error: {e}",
                duration_seconds=duration,
                handler_name=self.name,
            )

    def _build_payload(
        self,
        context: EventContext,
        include_context: bool,
    ) -> dict[str, Any]:
        """Build webhook payload from event context.

        Args:
            context: Event context
            include_context: Whether to include full context

        Returns:
            Payload dictionary
        """
        payload: dict[str, Any] = {
            "event_type": context.event_type.value,
            "environment": context.environment,
        }

        if include_context:
            payload["data"] = context.data

            if context.provider:
                payload["provider"] = context.provider

            if context.resource:
                payload["resource"] = context.resource

            if context.deployment_id:
                payload["deployment_id"] = context.deployment_id

        return payload
