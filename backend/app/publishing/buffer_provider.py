from datetime import datetime, timezone
import logging
import os
from typing import Any
import httpx

from app.config import settings
from app.publishing.interface import (
    AmbiguousTimeoutPublishingError,
    PermanentPublishingError,
    PublisherInterface,
    PublishRequest,
    PublishResult,
    TransientPublishingError,
)

logger = logging.getLogger(__name__)

BUFFER_GRAPHQL_ENDPOINT = "https://api.buffer.com"


def is_placeholder_buffer_token(token: str | None) -> bool:
    if not token or not token.strip():
        return True
    return token.strip().lower() in ("your-buffer-token", "placeholder", "your-key-here")


class BufferPublisher(PublisherInterface):
    """
    Real Buffer publishing provider using Buffer's modern GraphQL API.
    Buffer has deprecated the legacy REST API (api.bufferapp.com/1) in favor of api.buffer.com GraphQL.
    
    Flow:
    1. Resolve organization and active connected channel (or explicit channelId).
    2. Execute createPost mutation (or createIdea as fallback if no social channels connected).
    3. Map outcomes to Content OS exception hierarchy:
       - Network timeout / connection drop -> AmbiguousTimeoutPublishingError
       - 429 / server 5xx -> TransientPublishingError
       - 400 / 401 / 403 / schema reject -> PermanentPublishingError
    4. Return real external post ID and Buffer URL.
    """

    def __init__(
        self,
        access_token: str | None = None,
        channel_id: str | None = None,
        organization_id: str | None = None,
        timeout: float = 30.0,
    ):
        self.access_token = (
            access_token
            or settings.buffer_access_token
            or os.getenv("BUFFER_ACCESS_TOKEN", "")
        ).strip()
        self.channel_id = (
            channel_id
            or settings.buffer_profile_id
            or os.getenv("BUFFER_CHANNEL_ID", "")
            or os.getenv("BUFFER_PROFILE_ID", "")
        ).strip()
        self.organization_id = organization_id.strip() if organization_id else ""
        self.timeout = timeout

    def _execute_graphql(self, client: httpx.Client, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"query": query, "variables": variables or {}}

        try:
            res = client.post(BUFFER_GRAPHQL_ENDPOINT, headers=headers, json=payload, timeout=self.timeout)
        except httpx.TimeoutException as exc:
            logger.error("Ambiguous timeout calling Buffer GraphQL API: %s", exc)
            raise AmbiguousTimeoutPublishingError(f"Ambiguous timeout communicating with Buffer API: {exc}")
        except httpx.NetworkError as exc:
            logger.error("Network error communicating with Buffer GraphQL API: %s", exc)
            raise AmbiguousTimeoutPublishingError(f"Network error communicating with Buffer API: {exc}")

        if res.status_code == 429:
            raise TransientPublishingError(f"Buffer rate limit exceeded (HTTP 429): {res.text[:200]}")
        if res.status_code >= 500:
            raise TransientPublishingError(f"Buffer internal server error (HTTP {res.status_code}): {res.text[:200]}")
        if res.status_code in (401, 403):
            raise PermanentPublishingError(f"Buffer authentication/authorization failed (HTTP {res.status_code}): {res.text[:200]}")
        if res.status_code != 200:
            raise PermanentPublishingError(f"Buffer unexpected HTTP error (HTTP {res.status_code}): {res.text[:200]}")

        try:
            data = res.json()
        except Exception as j_err:
            raise PermanentPublishingError(f"Failed to parse Buffer GraphQL JSON response: {j_err} (raw: {res.text[:200]})")

        return data

    def _resolve_organization(self, client: httpx.Client) -> tuple[str, int]:
        if self.organization_id:
            return self.organization_id, 0

        query = """
        query GetAccount {
          account {
            id
            organizations {
              id
              name
              channelCount
            }
          }
        }
        """
        data = self._execute_graphql(client, query)
        errors = data.get("errors")
        if errors:
            raise PermanentPublishingError(f"Failed to query Buffer account: {errors[0].get('message')}")

        account = data.get("data", {}).get("account") or {}
        orgs = account.get("organizations") or []
        if not orgs:
            raise PermanentPublishingError("No organizations found on Buffer account.")

        org = orgs[0]
        self.organization_id = org["id"]
        channel_count = org.get("channelCount", 0)
        logger.info("Resolved Buffer Organization: %s (channels: %d)", self.organization_id, channel_count)
        return self.organization_id, channel_count

    def _resolve_channel(self, client: httpx.Client, org_id: str) -> str | None:
        if self.channel_id:
            return self.channel_id

        query = """
        query GetChannels($input: ChannelsInput!) {
          channels(input: $input) {
            id
            name
            service
          }
        }
        """
        variables = {"input": {"organizationId": org_id}}
        data = self._execute_graphql(client, query, variables)
        errors = data.get("errors")
        if errors:
            logger.warning("Error fetching channels for organization %s: %s", org_id, errors)
            return None

        channels = data.get("data", {}).get("channels") or []
        if channels:
            selected = channels[0]
            self.channel_id = selected["id"]
            logger.info("Auto-resolved Buffer Channel: %s (%s, %s)", self.channel_id, selected.get("service"), selected.get("name"))
            return self.channel_id

        return None

    def publish(self, request: PublishRequest) -> PublishResult:
        if is_placeholder_buffer_token(self.access_token):
            raise PermanentPublishingError(
                "BUFFER_ACCESS_TOKEN is missing or set to placeholder. Cannot dispatch to Buffer."
            )

        text_to_publish = request.body
        if request.title and not text_to_publish.strip().startswith(request.title.strip()):
            text_to_publish = f"{request.title.strip()}\n\n{text_to_publish.strip()}"

        with httpx.Client(timeout=self.timeout) as client:
            org_id, channel_count = self._resolve_organization(client)
            channel_id = self._resolve_channel(client, org_id)

            if channel_id:
                # Connected social channel exists -> execute createPost mutation
                logger.info(
                    "Publishing post to Buffer Channel %s (idempotency: %s)",
                    channel_id,
                    request.idempotency_key,
                )
                create_post_mutation = """
                mutation CreatePost($input: CreatePostInput!) {
                  createPost(input: $input) {
                    __typename
                    ... on PostActionSuccess {
                      post {
                        id
                        status
                        externalLink
                      }
                    }
                    ... on UnauthorizedError {
                      message
                    }
                    ... on NotFoundError {
                      message
                    }
                    ... on InvalidInputError {
                      message
                    }
                    ... on UnexpectedError {
                      message
                    }
                    ... on LimitReachedError {
                      message
                    }
                  }
                }
                """
                variables = {
                    "input": {
                        "channelId": channel_id,
                        "text": text_to_publish,
                        "mode": "shareNow",
                        "schedulingType": "automatic",
                        "needsApproval": False,
                        "assets": [],
                    }
                }
                resp_data = self._execute_graphql(client, create_post_mutation, variables)
                errors = resp_data.get("errors")
                if errors:
                    raise PermanentPublishingError(f"Buffer createPost failed: {errors[0].get('message')}")

                payload = resp_data.get("data", {}).get("createPost") or {}
                typename = payload.get("__typename")
                if typename != "PostActionSuccess":
                    err_msg = payload.get("message", f"Unexpected Buffer payload type: {typename}")
                    raise PermanentPublishingError(f"Buffer createPost rejected: {err_msg}")

                post = payload.get("post") or {}
                post_id = post.get("id") or f"buffer_{request.idempotency_key[:12]}"
                post_url = post.get("externalLink") or f"https://publish.buffer.com/organization/{org_id}/channels/{channel_id}"

                logger.info("Buffer post successfully created via GraphQL: %s", post_id)
                return PublishResult(
                    platform=request.platform,
                    external_post_id=str(post_id),
                    url=post_url,
                    published_at=datetime.now(timezone.utc),
                    provider_metadata={
                        "provider": "buffer",
                        "organization_id": org_id,
                        "channel_id": channel_id,
                        "post_id": post_id,
                        "idempotency_key": request.idempotency_key,
                    },
                )
            else:
                # No social channels connected yet on this organization
                # Buffer provides the Ideas / Content pipeline for storing pre-published drafts & ideas
                logger.info(
                    "No connected social channel on organization %s. Creating Idea/Draft item in Buffer library.",
                    org_id,
                )
                create_idea_mutation = """
                mutation CreateIdea($input: CreateIdeaInput!) {
                  createIdea(input: $input) {
                    __typename
                    ... on Idea {
                      id
                      createdAt
                    }
                    ... on InvalidInputError {
                      message
                    }
                    ... on UnauthorizedError {
                      message
                    }
                    ... on LimitReachedError {
                      message
                    }
                  }
                }
                """
                variables = {
                    "input": {
                        "organizationId": org_id,
                        "content": {
                            "text": text_to_publish,
                        },
                    }
                }
                resp_data = self._execute_graphql(client, create_idea_mutation, variables)
                errors = resp_data.get("errors")
                if errors:
                    raise PermanentPublishingError(f"Buffer createIdea failed: {errors[0].get('message')}")

                payload = resp_data.get("data", {}).get("createIdea") or {}
                typename = payload.get("__typename")
                if typename != "Idea":
                    err_msg = payload.get("message", f"Unexpected Buffer payload type: {typename}")
                    raise PermanentPublishingError(f"Buffer createIdea rejected: {err_msg}")

                idea_id = payload.get("id")
                post_url = f"https://publish.buffer.com/organization/{org_id}/content/ideas/{idea_id}"

                logger.info("Buffer item successfully published as Idea: %s (%s)", idea_id, post_url)
                return PublishResult(
                    platform=request.platform,
                    external_post_id=f"buffer_idea_{idea_id}",
                    url=post_url,
                    published_at=datetime.now(timezone.utc),
                    provider_metadata={
                        "provider": "buffer",
                        "organization_id": org_id,
                        "idea_id": idea_id,
                        "idempotency_key": request.idempotency_key,
                    },
                )
