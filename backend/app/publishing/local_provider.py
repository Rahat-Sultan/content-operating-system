from datetime import datetime, timezone
import hashlib
import logging
from typing import Any
from app.publishing.interface import (
    PublisherInterface,
    PublishRequest,
    PublishResult,
    TransientPublishingError,
    PermanentPublishingError,
    AmbiguousTimeoutPublishingError,
)

logger = logging.getLogger(__name__)


class LocalTestPublisher(PublisherInterface):
    """
    Deterministic local / test publishing provider.
    - Generates deterministic external_post_id based on idempotency_key.
    - Does NOT call any external commercial API (zero credentials required).
    - Can simulate transient failures, permanent failures, and ambiguous timeouts via simulation controls or request metadata.
    """

    def __init__(
        self,
        simulate_transient_failure_count: int = 0,
        simulate_permanent_failure: bool = False,
        simulate_timeout: bool = False,
    ):
        self._transient_failure_counter: dict[str, int] = {}
        self.simulate_transient_failure_count = simulate_transient_failure_count
        self.simulate_permanent_failure = simulate_permanent_failure
        self.simulate_timeout = simulate_timeout
        # In-memory post registry to ensure exact same post_id returned on same key
        self._published_registry: dict[str, PublishResult] = {}

    def reset_simulation(self):
        self._transient_failure_counter.clear()
        self.simulate_transient_failure_count = 0
        self.simulate_permanent_failure = False
        self.simulate_timeout = False

    def publish(self, request: PublishRequest) -> PublishResult:
        key = request.idempotency_key
        logger.info(
            "LocalTestPublisher.publish called for version %s, platform %s, key %s",
            request.content_version_id,
            request.platform,
            key,
        )

        # 1. Check if we already published this key in-memory (provider-side idempotency)
        if key in self._published_registry:
            logger.info("LocalTestPublisher reusing in-memory publication for key %s", key)
            return self._published_registry[key]

        # 2. Check for simulation instructions in request metadata or instance settings
        req_meta = request.metadata or {}
        should_fail_permanent = (
            self.simulate_permanent_failure
            or req_meta.get("simulate_permanent_failure", False)
        )
        if should_fail_permanent:
            logger.warning("LocalTestPublisher simulating permanent failure for key %s", key)
            raise PermanentPublishingError(
                f"Simulated permanent failure from platform {request.platform}: invalid content or policy rejection"
            )

        should_timeout = (
            self.simulate_timeout
            or req_meta.get("simulate_timeout", False)
        )
        if should_timeout:
            logger.warning("LocalTestPublisher simulating ambiguous timeout for key %s", key)
            raise AmbiguousTimeoutPublishingError(
                f"Simulated connection timeout to {request.platform} after payload dispatch"
            )

        transient_target = req_meta.get(
            "simulate_transient_failure_count",
            self.simulate_transient_failure_count,
        )
        current_attempts = self._transient_failure_counter.get(key, 0)
        if current_attempts < transient_target:
            self._transient_failure_counter[key] = current_attempts + 1
            logger.warning(
                "LocalTestPublisher simulating transient failure (attempt %d of %d) for key %s",
                current_attempts + 1,
                transient_target,
                key,
            )
            raise TransientPublishingError(
                f"Simulated transient error from {request.platform} (503 Service Unavailable / Rate Limit)"
            )

        # 3. Deterministic generation of external_post_id
        # Hashing the idempotency_key ensures identical post_id across executions without randomness
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        external_post_id = f"{request.platform}_{key_hash}"
        fake_url = f"https://www.{request.platform}.com/posts/{external_post_id}"

        result = PublishResult(
            platform=request.platform,
            external_post_id=external_post_id,
            url=fake_url,
            published_at=datetime.now(timezone.utc),
            provider_metadata={
                "provider": "local_test",
                "is_stub": True,
                "platform": request.platform,
                "characters_posted": len(request.body),
                "media_attached": False,
                "idempotency_key": key,
            },
        )

        self._published_registry[key] = result
        return result
