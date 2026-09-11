"""Transactional model-governance application service."""

# SQL statements remain complete and reviewable.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ima.config import Settings
from ima.domain.model_governance import (
    EmbeddingConfig,
    ModelCapability,
    ModelGatewayInput,
    Workflow,
    canonical_config,
    config_digest,
    parse_profile_config,
)
from ima.infrastructure.model_gateway.egress import (
    EgressPolicy,
    GatewayError,
    GuardedGatewayClient,
    validate_egress,
)
from ima.infrastructure.model_gateway.secrets import (
    SecretEnvelope,
    SecretEnvelopeError,
    SecretKeyRing,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


# Every workflow resolves exactly one governed operation; the scene default
# and the resolver must agree on this mapping.
WORKFLOW_OPERATION: dict[Workflow, str] = {
    Workflow.GROUNDED_ASK: "chat",
    Workflow.TITLE_GENERATION: "chat",
    Workflow.SUMMARIZATION: "chat",
    Workflow.EMBEDDING: "embedding",
    Workflow.RERANKING: "rerank",
}

# The system-managed capability profile backing a scene default.  At most one
# profile per workflow carries this alias (unique index
# ux_capability_profiles_workflow_alias).
SCENE_DEFAULT_ALIAS = "场景默认"


class ModelGovernanceError(RuntimeError):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


class ModelGovernanceService:
    """Single mutable authority for gateways, models, profiles and assignments."""

    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings
        self.key_ring = SecretKeyRing(
            settings.model_key_ring.get_secret_value(),
            settings.model_current_key_version,
            settings.model_fingerprint_key.get_secret_value(),
        )

    def _policy_for_gateway(self, row: Any) -> EgressPolicy:
        """Build the transport policy from the persisted gateway boundary.

        The deployment policy supplies the custom-CA root, while every other
        egress limit is owned by the gateway record.  Reusing the global client
        here would silently ignore an administrator's per-gateway boundary.
        """
        return EgressPolicy(
            allowed_hosts=tuple(row.get("allowed_hosts") or self.settings.model_allowed_hosts),
            allowed_cidrs=tuple(row.get("allowed_cidrs") or self.settings.model_allowed_cidrs),
            allow_insecure_private=bool(row.get("insecure_private"))
            and self.settings.model_allow_insecure_private,
            max_response_bytes=int(
                row.get("max_response_bytes") or self.settings.model_max_response_bytes
            ),
            connect_timeout_seconds=int(row.get("connect_timeout_ms") or 5000) / 1000,
            read_timeout_seconds=int(row.get("read_timeout_ms") or 30000) / 1000,
            write_timeout_seconds=int(row.get("write_timeout_ms") or 30000) / 1000,
            pool_timeout_seconds=int(row.get("pool_timeout_ms") or 5000) / 1000,
            custom_ca_dir=self.settings.model_custom_ca_dir,
        )

    def _client_for_gateway(self, row: Any) -> GuardedGatewayClient:
        return GuardedGatewayClient(self._policy_for_gateway(row))

    def _policy_for_input(self, payload: ModelGatewayInput) -> EgressPolicy:
        return EgressPolicy(
            allowed_hosts=payload.allowed_hosts or self.settings.model_allowed_hosts,
            allowed_cidrs=payload.allowed_cidrs or self.settings.model_allowed_cidrs,
            allow_insecure_private=payload.insecure_private
            and self.settings.model_allow_insecure_private,
            max_response_bytes=payload.max_response_bytes,
            connect_timeout_seconds=payload.connect_timeout_ms / 1000,
            read_timeout_seconds=payload.read_timeout_ms / 1000,
            write_timeout_seconds=payload.write_timeout_ms / 1000,
            pool_timeout_seconds=payload.pool_timeout_ms / 1000,
            custom_ca_dir=self.settings.model_custom_ca_dir,
        )

    @staticmethod
    def _profile_model_references(config: Any) -> tuple[tuple[str, ModelCapability], ...]:
        references: list[tuple[str, ModelCapability]] = []
        for field, capability in (
            ("chat_model_id", ModelCapability.CHAT),
            ("embedding_model_id", ModelCapability.EMBEDDING),
            ("rerank_model_id", ModelCapability.RERANK),
        ):
            model_id = getattr(config, field, None)
            if model_id:
                references.append((str(model_id), capability))
        return tuple(references)

    async def _locked_model_health(self, conn: AsyncConnection, model_id: str) -> Any:
        """Read one governed model row under FOR SHARE with its health state.

        The health row sits on the nullable side of a LEFT JOIN and PostgreSQL
        rejects FOR SHARE there, so it is read without a lock separately.
        """
        model = (
            (
                await conn.execute(
                    text(
                        "SELECT m.gateway_id,m.capability,m.embedding_dimension,m.enabled,m.validated,g.enabled gateway_enabled FROM ima.governed_models m JOIN ima.model_gateways g ON g.id=m.gateway_id WHERE m.id=:id FOR SHARE"
                    ),
                    {"id": model_id},
                )
            )
            .mappings()
            .first()
        )
        if not model:
            return None
        state = await conn.scalar(
            text(
                "SELECT state FROM ima.model_gateway_health WHERE gateway_id=:gateway AND capability=:capability"
            ),
            {"gateway": model["gateway_id"], "capability": model["capability"]},
        )
        row = dict(model)
        row["health_state"] = state or "unknown"
        return row

    async def _audit(
        self,
        conn: AsyncConnection,
        actor_id: str | None,
        action: str,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        result: str = "success",
        reason: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        safe = metadata or {}
        await conn.execute(
            text(
                """INSERT INTO ima.audit_events(actor_id,action,target_type,target_id,result,reason_code,metadata,created_at)
                VALUES (:actor,:action,:type,:target,:result,:reason,CAST(:metadata AS jsonb),:now)"""
            ),
            {
                "actor": actor_id,
                "action": action,
                "type": target_type,
                "target": target_id,
                "result": result,
                "reason": reason,
                "metadata": json.dumps(safe, ensure_ascii=True),
                "now": utcnow(),
            },
        )

    def _gateway_policy(self, data: ModelGatewayInput) -> tuple[str, str]:
        parsed_scheme = data.base_url.split(":", 1)[0].lower()
        tls_mode = "private_http" if parsed_scheme == "http" else "required"
        return data.base_url.rstrip("/"), tls_mode

    @staticmethod
    def _gateway_payload(
        row: Any, *, include_sensitive: bool = False, health: tuple[Any, ...] = ()
    ) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "baseUrl": row["normalized_base_url"] if include_sensitive else None,
            "enabled": row["enabled"],
            "allowedCapabilities": tuple(row["allowed_capabilities"] or ()),
            "tlsMode": row["tls_mode"],
            "insecurePrivate": row["insecure_private"],
            "customCaRef": row["custom_ca_ref"] if include_sensitive else None,
            "version": row["version"],
            "secretPresent": bool(row["secret_id"]),
            "fingerprint": row.get("fingerprint") if include_sensitive else None,
            "health": health,
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    async def list_gateways(self, *, include_sensitive: bool) -> list[dict[str, Any]]:
        async with self.engine.begin() as conn:
            rows = (
                (await conn.execute(text("SELECT * FROM ima.model_gateways ORDER BY name,id")))
                .mappings()
                .all()
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                health = (
                    (
                        await conn.execute(
                            text(
                                "SELECT capability,state,reason_code,latency_ms,checked_at FROM ima.model_gateway_health WHERE gateway_id=:id ORDER BY capability"
                            ),
                            {"id": row["id"]},
                        )
                    )
                    .mappings()
                    .all()
                )
                fingerprint = None
                if include_sensitive and row["secret_id"]:
                    fingerprint = await conn.scalar(
                        text("SELECT fingerprint FROM ima.model_gateway_secrets WHERE id=:id"),
                        {"id": row["secret_id"]},
                    )
                result.append(
                    self._gateway_payload(
                        row,
                        include_sensitive=include_sensitive,
                        # Health state/timestamps are safe governance metadata.
                        # Auditors need them even though endpoint, CA and
                        # credential fingerprint remain manager-only fields.
                        health=tuple(dict(item) for item in health),
                    )
                )
                result[-1]["fingerprint"] = fingerprint
            return result

    async def create_gateway(
        self, actor_id: str, payload: ModelGatewayInput, secret: str | None
    ) -> dict[str, Any]:
        normalized, tls_mode = self._gateway_policy(payload)
        try:
            await validate_egress(
                normalized,
                self._policy_for_input(payload),
                insecure_private=payload.insecure_private,
            )
        except GatewayError as exc:
            raise ModelGovernanceError(
                400, exc.code, "Gateway egress policy rejected the endpoint"
            ) from exc
        gateway_id = uuid4()
        secret_id = uuid4() if secret else None
        now = utcnow()
        async with self.engine.begin() as conn:
            if secret_id:
                envelope = self.key_ring.encrypt(
                    secret or "", gateway_id=str(gateway_id), secret_id=str(secret_id)
                )
                await conn.execute(
                    text(
                        "INSERT INTO ima.model_gateway_secrets(id,key_version,nonce,ciphertext,fingerprint,created_at) VALUES (:id,:version,:nonce,:cipher,:fingerprint,:now)"
                    ),
                    {
                        "id": secret_id,
                        "version": envelope.key_version,
                        "nonce": envelope.nonce,
                        "cipher": envelope.ciphertext,
                        "fingerprint": envelope.fingerprint,
                        "now": now,
                    },
                )
            try:
                await conn.execute(
                    text("""INSERT INTO ima.model_gateways(id,name,normalized_base_url,allowed_capabilities,tls_mode,insecure_private,custom_ca_ref,connect_timeout_ms,read_timeout_ms,write_timeout_ms,pool_timeout_ms,max_response_bytes,allowed_hosts,allowed_cidrs,secret_id,created_by,updated_by,created_at,updated_at)
                    VALUES (:id,:name,:url,:caps,:tls,:insecure,:ca,:connect,:read,:write,:pool,:max,:hosts,:cidrs,:secret,:actor,:actor,:now,:now)"""),
                    {
                        "id": gateway_id,
                        "name": payload.name,
                        "url": normalized,
                        "caps": [item.value for item in payload.allowed_capabilities],
                        "tls": tls_mode,
                        "insecure": payload.insecure_private,
                        "ca": payload.custom_ca_ref,
                        "connect": payload.connect_timeout_ms,
                        "read": payload.read_timeout_ms,
                        "write": payload.write_timeout_ms,
                        "pool": payload.pool_timeout_ms,
                        "max": payload.max_response_bytes,
                        "hosts": list(payload.allowed_hosts),
                        "cidrs": list(payload.allowed_cidrs),
                        "secret": secret_id,
                        "actor": actor_id,
                        "now": now,
                    },
                )
            except Exception as exc:
                if "unique" in str(exc).lower():
                    raise ModelGovernanceError(
                        409, "GATEWAY_NAME_CONFLICT", "Gateway name already exists"
                    ) from exc
                raise
            await self._audit(
                conn,
                actor_id,
                "model.gateway.created",
                target_type="model_gateway",
                target_id=str(gateway_id),
                metadata={"version": 1},
            )
        rows = await self.list_gateways(include_sensitive=True)
        return next(item for item in rows if str(item["id"]) == str(gateway_id))

    async def rotate_gateway_secret(
        self, actor_id: str, gateway_id: UUID, secret: str, expected_version: int | None = None
    ) -> dict[str, Any]:
        if not secret:
            raise ModelGovernanceError(400, "EMPTY_SECRET", "Gateway secret cannot be empty")
        new_secret_id = uuid4()
        now = utcnow()
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,secret_id,version FROM ima.model_gateways WHERE id=:id FOR UPDATE"
                        ),
                        {"id": gateway_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise ModelGovernanceError(404, "GATEWAY_NOT_FOUND", "Gateway not found")
            if (
                expected_version is not None
                and int(row.get("version", expected_version)) != expected_version
            ):
                raise ModelGovernanceError(
                    409, "VERSION_CONFLICT", "Gateway was changed by another administrator"
                )
            envelope = self.key_ring.encrypt(
                secret, gateway_id=str(gateway_id), secret_id=str(new_secret_id)
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.model_gateway_secrets(id,key_version,nonce,ciphertext,fingerprint,created_at,rotated_at,rotated_by) VALUES (:id,:version,:nonce,:cipher,:fingerprint,:now,:now,:actor)"
                ),
                {
                    "id": new_secret_id,
                    "version": envelope.key_version,
                    "nonce": envelope.nonce,
                    "cipher": envelope.ciphertext,
                    "fingerprint": envelope.fingerprint,
                    "now": now,
                    "actor": actor_id,
                },
            )
            await conn.execute(
                text(
                    "UPDATE ima.model_gateways SET secret_id=:secret,version=version+1,updated_by=:actor,updated_at=:now WHERE id=:id"
                ),
                {"secret": new_secret_id, "actor": actor_id, "now": now, "id": gateway_id},
            )
            await self._audit(
                conn,
                actor_id,
                "model.gateway.secret_rotated",
                target_type="model_gateway",
                target_id=str(gateway_id),
                metadata={"secretPresent": True},
            )
        rows = await self.list_gateways(include_sensitive=True)
        return next(item for item in rows if str(item["id"]) == str(gateway_id))

    async def set_gateway_enabled(
        self, actor_id: str, gateway_id: UUID, enabled: bool, expected_version: int | None = None
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.model_gateways WHERE id=:id FOR UPDATE"),
                        {"id": gateway_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise ModelGovernanceError(404, "GATEWAY_NOT_FOUND", "Gateway not found")
            if expected_version is not None and row["version"] != expected_version:
                raise ModelGovernanceError(
                    409, "VERSION_CONFLICT", "Gateway was changed by another administrator"
                )
            now = utcnow()
            await conn.execute(
                text(
                    "UPDATE ima.model_gateways SET enabled=:enabled,version=version+1,updated_by=:actor,updated_at=:now WHERE id=:id"
                ),
                {"enabled": enabled, "actor": actor_id, "now": now, "id": gateway_id},
            )
            await self._audit(
                conn,
                actor_id,
                "model.gateway.enabled" if enabled else "model.gateway.disabled",
                target_type="model_gateway",
                target_id=str(gateway_id),
            )
        return next(
            item
            for item in await self.list_gateways(include_sensitive=True)
            if str(item["id"]) == str(gateway_id)
        )

    async def update_gateway(
        self, actor_id: str, gateway_id: UUID, values: dict[str, Any], expected_version: int
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            current = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.model_gateways WHERE id=:id FOR UPDATE"),
                        {"id": gateway_id},
                    )
                )
                .mappings()
                .first()
            )
            if not current:
                raise ModelGovernanceError(404, "GATEWAY_NOT_FOUND", "Gateway not found")
            if current["version"] != expected_version:
                raise ModelGovernanceError(
                    409, "VERSION_CONFLICT", "Gateway was changed by another administrator"
                )
            merged = {
                "name": values.get("name", current["name"]),
                "base_url": values.get("base_url", current["normalized_base_url"]),
                "allowed_capabilities": values.get(
                    "allowed_capabilities", tuple(current["allowed_capabilities"] or ())
                ),
                "insecure_private": values.get("insecure_private", current["insecure_private"]),
                "allowed_hosts": values.get("allowed_hosts", tuple(current["allowed_hosts"] or ())),
                "allowed_cidrs": values.get("allowed_cidrs", tuple(current["allowed_cidrs"] or ())),
                "custom_ca_ref": values.get("custom_ca_ref", current["custom_ca_ref"]),
                "connect_timeout_ms": values.get(
                    "connect_timeout_ms", current["connect_timeout_ms"]
                ),
                "read_timeout_ms": values.get("read_timeout_ms", current["read_timeout_ms"]),
                "write_timeout_ms": values.get("write_timeout_ms", current["write_timeout_ms"]),
                "pool_timeout_ms": values.get("pool_timeout_ms", current["pool_timeout_ms"]),
                "max_response_bytes": values.get(
                    "max_response_bytes", current["max_response_bytes"]
                ),
            }
            try:
                checked = ModelGatewayInput.model_validate(
                    {
                        "name": merged["name"],
                        "baseUrl": merged["base_url"],
                        "allowedCapabilities": merged["allowed_capabilities"],
                        "insecurePrivate": merged["insecure_private"],
                        "allowedHosts": merged["allowed_hosts"],
                        "allowedCidrs": merged["allowed_cidrs"],
                        "customCaRef": merged["custom_ca_ref"],
                        "connectTimeoutMs": merged["connect_timeout_ms"],
                        "readTimeoutMs": merged["read_timeout_ms"],
                        "writeTimeoutMs": merged["write_timeout_ms"],
                        "poolTimeoutMs": merged["pool_timeout_ms"],
                        "maxResponseBytes": merged["max_response_bytes"],
                    }
                )
                normalized, tls_mode = self._gateway_policy(checked)
                await validate_egress(
                    normalized,
                    self._policy_for_input(checked),
                    insecure_private=checked.insecure_private,
                )
            except (ValueError, GatewayError) as exc:
                code = exc.code if isinstance(exc, GatewayError) else "INVALID_GATEWAY"
                raise ModelGovernanceError(400, code, "Gateway configuration is invalid") from exc
            await conn.execute(
                text(
                    """UPDATE ima.model_gateways SET name=:name,normalized_base_url=:url,allowed_capabilities=:caps,tls_mode=:tls,insecure_private=:insecure,custom_ca_ref=:ca,connect_timeout_ms=:connect,read_timeout_ms=:read,write_timeout_ms=:write,pool_timeout_ms=:pool,max_response_bytes=:max,allowed_hosts=:hosts,allowed_cidrs=:cidrs,version=version+1,updated_by=:actor,updated_at=:now WHERE id=:id"""
                ),
                {
                    "name": checked.name,
                    "url": normalized,
                    "caps": [item.value for item in checked.allowed_capabilities],
                    "tls": tls_mode,
                    "insecure": checked.insecure_private,
                    "ca": checked.custom_ca_ref,
                    "connect": checked.connect_timeout_ms,
                    "read": checked.read_timeout_ms,
                    "write": checked.write_timeout_ms,
                    "pool": checked.pool_timeout_ms,
                    "max": checked.max_response_bytes,
                    "hosts": list(checked.allowed_hosts),
                    "cidrs": list(checked.allowed_cidrs),
                    "actor": actor_id,
                    "now": utcnow(),
                    "id": gateway_id,
                },
            )
            await self._audit(
                conn,
                actor_id,
                "model.gateway.updated",
                target_type="model_gateway",
                target_id=str(gateway_id),
            )
        return next(
            item
            for item in await self.list_gateways(include_sensitive=True)
            if str(item["id"]) == str(gateway_id)
        )

    async def delete_gateway(self, actor_id: str, gateway_id: UUID) -> None:
        async with self.engine.begin() as conn:
            row = await conn.scalar(
                text("SELECT id FROM ima.model_gateways WHERE id=:id FOR UPDATE"),
                {"id": gateway_id},
            )
            if not row:
                raise ModelGovernanceError(404, "GATEWAY_NOT_FOUND", "Gateway not found")
            dependency = await conn.scalar(
                text("SELECT 1 FROM ima.governed_models m WHERE m.gateway_id=:id LIMIT 1"),
                {"id": gateway_id},
            )
            if dependency:
                raise ModelGovernanceError(
                    409, "DEPENDENCY_CONFLICT", "Gateway has published model dependencies"
                )
            await conn.execute(
                text("DELETE FROM ima.model_gateways WHERE id=:id"), {"id": gateway_id}
            )
            await self._audit(
                conn,
                actor_id,
                "model.gateway.deleted",
                target_type="model_gateway",
                target_id=str(gateway_id),
            )

    @staticmethod
    def _model_payload(row: Any, *, include_sensitive: bool) -> dict[str, Any]:
        return {
            "id": row["id"],
            "gatewayId": row["gateway_id"] if include_sensitive else None,
            "remoteName": row["remote_name"] if include_sensitive else None,
            "capability": row["capability"],
            "businessLabel": row["business_label"],
            "enabled": row["enabled"],
            "validated": row["validated"],
            "validationDigest": row["validation_digest"] if include_sensitive else None,
            "validatedAt": row["validated_at"],
            "contextLimit": row["context_limit"],
            "outputLimit": row["output_limit"],
            "embeddingDimension": row["embedding_dimension"],
            "maxDocuments": row["max_documents"],
            "version": row["version"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    async def list_models(self, *, include_sensitive: bool) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.governed_models ORDER BY capability,business_label,id"
                        )
                    )
                )
                .mappings()
                .all()
            )
        return [self._model_payload(row, include_sensitive=include_sensitive) for row in rows]

    async def create_model(self, actor_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        capability = ModelCapability(payload["capability"])
        if capability == ModelCapability.EMBEDDING and not payload.get("embedding_dimension"):
            raise ModelGovernanceError(
                400, "DIMENSION_REQUIRED", "Embedding models require a dimension"
            )
        model_id = uuid4()
        now = utcnow()
        async with self.engine.begin() as conn:
            gateway = (
                (
                    await conn.execute(
                        text("SELECT id,allowed_capabilities FROM ima.model_gateways WHERE id=:id"),
                        {"id": payload["gateway_id"]},
                    )
                )
                .mappings()
                .first()
            )
            if not gateway:
                raise ModelGovernanceError(404, "GATEWAY_NOT_FOUND", "Gateway not found")
            if capability.value not in (gateway["allowed_capabilities"] or ()):
                raise ModelGovernanceError(
                    400, "CAPABILITY_NOT_ALLOWED", "Gateway does not allow this capability"
                )
            await conn.execute(
                text(
                    """INSERT INTO ima.governed_models(id,gateway_id,remote_name,capability,business_label,context_limit,output_limit,embedding_dimension,max_documents,created_by,updated_by,created_at,updated_at) VALUES (:id,:gateway,:remote,:capability,:label,:context,:output,:dimension,:documents,:actor,:actor,:now,:now)"""
                ),
                {
                    "id": model_id,
                    "gateway": payload["gateway_id"],
                    "remote": payload["remote_name"],
                    "capability": capability.value,
                    "label": payload["business_label"],
                    "context": payload.get("context_limit"),
                    "output": payload.get("output_limit"),
                    "dimension": payload.get("embedding_dimension"),
                    "documents": payload.get("max_documents"),
                    "actor": actor_id,
                    "now": now,
                },
            )
            await self._audit(
                conn,
                actor_id,
                "model.registry.created",
                target_type="governed_model",
                target_id=str(model_id),
                metadata={"capability": capability.value},
            )
            row = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.governed_models WHERE id=:id"), {"id": model_id}
                    )
                )
                .mappings()
                .one()
            )
        return self._model_payload(row, include_sensitive=True)

    async def validate_model(
        self, actor_id: str, model_id: UUID, expected_version: int | None = None
    ) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT m.*,g.normalized_base_url,g.insecure_private,g.enabled gateway_enabled,g.secret_id,g.custom_ca_ref,g.allowed_hosts,g.allowed_cidrs,g.max_response_bytes,g.connect_timeout_ms,g.read_timeout_ms,g.write_timeout_ms,g.pool_timeout_ms FROM ima.governed_models m JOIN ima.model_gateways g ON g.id=m.gateway_id WHERE m.id=:id"
                        ),
                        {"id": model_id},
                    )
                )
                .mappings()
                .first()
            )
        if not row:
            raise ModelGovernanceError(404, "MODEL_NOT_FOUND", "Model not found")
        if expected_version is not None and int(row["version"]) != expected_version:
            raise ModelGovernanceError(
                409, "VERSION_CONFLICT", "Model was changed by another administrator"
            )
        ok, reason, latency = await self._client_for_gateway(row).probe(
            row["normalized_base_url"],
            row["capability"],
            row["remote_name"],
            dimension=row["embedding_dimension"],
            api_key=await self._decrypt_secret(row["gateway_id"], row["secret_id"]),
            custom_ca_ref=row["custom_ca_ref"],
            insecure_private=row["insecure_private"],
        )
        async with self.engine.begin() as conn:
            now = utcnow()
            digest = hashlib.sha256(
                f"{row['gateway_id']}:{row['remote_name']}:{row['capability']}:{row['embedding_dimension']}".encode()
            ).hexdigest()
            await conn.execute(
                text(
                    "UPDATE ima.governed_models SET validated=:ok,validation_digest=:digest,validated_at=:now,version=version+1,updated_by=:actor,updated_at=:now WHERE id=:id"
                ),
                {
                    "ok": ok,
                    "digest": digest if ok else None,
                    "now": now,
                    "actor": actor_id,
                    "id": model_id,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.model_gateway_health(gateway_id,capability,state,reason_code,latency_ms,checked_at,next_check_at,consecutive_failures) VALUES (:gateway,:capability,:state,:reason,:latency,:now,:next,:failures) ON CONFLICT(gateway_id,capability) DO UPDATE SET state=EXCLUDED.state,reason_code=EXCLUDED.reason_code,latency_ms=EXCLUDED.latency_ms,checked_at=EXCLUDED.checked_at,next_check_at=EXCLUDED.next_check_at,consecutive_failures=EXCLUDED.consecutive_failures"
                ),
                {
                    "gateway": row["gateway_id"],
                    "capability": row["capability"],
                    "state": "healthy" if ok else "unavailable",
                    "reason": reason,
                    "latency": latency,
                    "now": now,
                    "next": now,
                    "failures": 0 if ok else 1,
                },
            )
            await self._audit(
                conn,
                actor_id,
                "model.registry.validated",
                target_type="governed_model",
                target_id=str(model_id),
                result="success" if ok else "failed",
                reason=reason,
                metadata={"latencyMs": latency},
            )
            result = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.governed_models WHERE id=:id"), {"id": model_id}
                    )
                )
                .mappings()
                .one()
            )
        return self._model_payload(result, include_sensitive=True)

    async def set_model_enabled(
        self, actor_id: str, model_id: UUID, enabled: bool, expected_version: int | None = None
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.governed_models WHERE id=:id FOR UPDATE"),
                        {"id": model_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise ModelGovernanceError(404, "MODEL_NOT_FOUND", "Model not found")
            if expected_version is not None and row["version"] != expected_version:
                raise ModelGovernanceError(
                    409, "VERSION_CONFLICT", "Model was changed by another administrator"
                )
            if enabled and not row["validated"]:
                raise ModelGovernanceError(
                    409, "MODEL_NOT_VALIDATED", "Model must pass validation before enablement"
                )
            await conn.execute(
                text(
                    "UPDATE ima.governed_models SET enabled=:enabled,version=version+1,updated_by=:actor,updated_at=:now WHERE id=:id"
                ),
                {"enabled": enabled, "actor": actor_id, "now": utcnow(), "id": model_id},
            )
            await self._audit(
                conn,
                actor_id,
                "model.registry.enabled" if enabled else "model.registry.disabled",
                target_type="governed_model",
                target_id=str(model_id),
            )
            result = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.governed_models WHERE id=:id"), {"id": model_id}
                    )
                )
                .mappings()
                .one()
            )
        return self._model_payload(result, include_sensitive=True)

    async def update_model(
        self, actor_id: str, model_id: UUID, values: dict[str, Any], expected_version: int
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.governed_models WHERE id=:id FOR UPDATE"),
                        {"id": model_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise ModelGovernanceError(404, "MODEL_NOT_FOUND", "Model not found")
            if row["version"] != expected_version:
                raise ModelGovernanceError(
                    409, "VERSION_CONFLICT", "Model was changed by another administrator"
                )
            await conn.execute(
                text(
                    "UPDATE ima.governed_models SET business_label=COALESCE(:label,business_label),context_limit=COALESCE(:context,context_limit),output_limit=COALESCE(:output,output_limit),embedding_dimension=COALESCE(:dimension,embedding_dimension),max_documents=COALESCE(:documents,max_documents),validated=false,validation_digest=NULL,validated_at=NULL,version=version+1,updated_by=:actor,updated_at=:now WHERE id=:id"
                ),
                {
                    "label": values.get("business_label"),
                    "context": values.get("context_limit"),
                    "output": values.get("output_limit"),
                    "dimension": values.get("embedding_dimension"),
                    "documents": values.get("max_documents"),
                    "actor": actor_id,
                    "now": utcnow(),
                    "id": model_id,
                },
            )
            await self._audit(
                conn,
                actor_id,
                "model.registry.updated",
                target_type="governed_model",
                target_id=str(model_id),
            )
            result = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.governed_models WHERE id=:id"), {"id": model_id}
                    )
                )
                .mappings()
                .one()
            )
        return self._model_payload(result, include_sensitive=True)

    async def delete_model(self, actor_id: str, model_id: UUID) -> None:
        async with self.engine.begin() as conn:
            if await conn.scalar(
                text(
                    "SELECT 1 FROM ima.model_dependency_index WHERE model_id=:id AND active LIMIT 1"
                ),
                {"id": model_id},
            ):
                raise ModelGovernanceError(
                    409, "DEPENDENCY_CONFLICT", "Model has active dependencies"
                )
            if await conn.scalar(
                text(
                    """SELECT 1
                    FROM ima.capability_profile_versions
                    WHERE state='published'
                      AND (
                        config @> jsonb_build_object('chatModelId', CAST(:id AS text))
                        OR config @> jsonb_build_object('embeddingModelId', CAST(:id AS text))
                        OR config @> jsonb_build_object('rerankModelId', CAST(:id AS text))
                      )
                    LIMIT 1"""
                ),
                {"id": str(model_id)},
            ):
                raise ModelGovernanceError(
                    409, "DEPENDENCY_CONFLICT", "Model is used by a published profile"
                )
            deleted = await conn.execute(
                text("DELETE FROM ima.governed_models WHERE id=:id"), {"id": model_id}
            )
            if not deleted.rowcount:
                raise ModelGovernanceError(404, "MODEL_NOT_FOUND", "Model not found")
            await self._audit(
                conn,
                actor_id,
                "model.registry.deleted",
                target_type="governed_model",
                target_id=str(model_id),
            )

    @staticmethod
    def _profile_payload(row: Any, *, include_config: bool) -> dict[str, Any]:
        return {
            "id": row["id"],
            "workflow": row["workflow"],
            "businessAlias": row["business_alias"],
            "description": row["description"],
            "lifecycle": row["lifecycle"],
            "currentVersion": row["current_version"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    async def list_profiles(self) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.capability_profiles ORDER BY workflow,business_alias,id"
                        )
                    )
                )
                .mappings()
                .all()
            )
        return [self._profile_payload(row, include_config=False) for row in rows]

    async def create_profile(
        self,
        actor_id: str,
        workflow: Workflow,
        alias: str,
        description: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            parsed = parse_profile_config(config, workflow)
        except Exception as exc:
            raise ModelGovernanceError(
                422, "INVALID_PROFILE_CONFIG", "Profile configuration is invalid"
            ) from exc
        profile_id = uuid4()
        now = utcnow()
        canonical = canonical_config(parsed)
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO ima.capability_profiles(id,workflow,business_alias,description,current_version,created_by,updated_by,created_at,updated_at) VALUES (:id,:workflow,:alias,:description,0,:actor,:actor,:now,:now)"
                ),
                {
                    "id": profile_id,
                    "workflow": workflow.value,
                    "alias": alias,
                    "description": description,
                    "actor": actor_id,
                    "now": now,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.capability_profile_versions(profile_id,version,state,config,config_digest,created_by,created_at,updated_at) VALUES (:id,1,'draft',CAST(:config AS jsonb),:digest,:actor,:now,:now)"
                ),
                {
                    "id": profile_id,
                    "config": json.dumps(canonical, ensure_ascii=True),
                    "digest": config_digest(parsed),
                    "actor": actor_id,
                    "now": now,
                },
            )
            await self._audit(
                conn,
                actor_id,
                "model.profile.created",
                target_type="capability_profile",
                target_id=str(profile_id),
                metadata={"workflow": workflow.value},
            )
            row = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.capability_profiles WHERE id=:id"),
                        {"id": profile_id},
                    )
                )
                .mappings()
                .one()
            )
        return self._profile_payload(row, include_config=False)

    async def list_profile_versions(
        self, profile_id: UUID, *, include_config: bool
    ) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.capability_profile_versions WHERE profile_id=:id ORDER BY version DESC"
                        ),
                        {"id": profile_id},
                    )
                )
                .mappings()
                .all()
            )
        result = []
        for row in rows:
            value = {
                "profileId": row["profile_id"],
                "version": row["version"],
                "state": row["state"],
                "config": row["config"] if include_config else None,
                "configDigest": row["config_digest"],
                "draftVersion": row["draft_version"],
                "publishedAt": row["published_at"],
                "disabledAt": row["disabled_at"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            result.append(value)
        return result

    async def patch_profile_draft(
        self, actor_id: str, profile_id: UUID, config: dict[str, Any], expected_draft_version: int
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            profile = (
                (
                    await conn.execute(
                        text(
                            "SELECT workflow FROM ima.capability_profiles WHERE id=:id FOR UPDATE"
                        ),
                        {"id": profile_id},
                    )
                )
                .mappings()
                .first()
            )
            if not profile:
                raise ModelGovernanceError(404, "PROFILE_NOT_FOUND", "Profile not found")
            try:
                parsed = parse_profile_config(config, profile["workflow"])
            except Exception as exc:
                raise ModelGovernanceError(
                    422, "INVALID_PROFILE_CONFIG", "Profile configuration is invalid"
                ) from exc
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.capability_profile_versions WHERE profile_id=:id AND state='draft' FOR UPDATE"
                        ),
                        {"id": profile_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise ModelGovernanceError(409, "NO_DRAFT", "Profile has no editable draft")
            if row["draft_version"] != expected_draft_version:
                raise ModelGovernanceError(
                    409, "VERSION_CONFLICT", "Profile draft was changed by another administrator"
                )
            canonical = canonical_config(parsed)
            await conn.execute(
                text(
                    "UPDATE ima.capability_profile_versions SET config=CAST(:config AS jsonb),config_digest=:digest,draft_version=draft_version+1,updated_at=:now WHERE profile_id=:id AND version=:version"
                ),
                {
                    "config": json.dumps(canonical, ensure_ascii=True),
                    "digest": config_digest(parsed),
                    "now": utcnow(),
                    "id": profile_id,
                    "version": row["version"],
                },
            )
            await self._audit(
                conn,
                actor_id,
                "model.profile.draft_updated",
                target_type="capability_profile",
                target_id=str(profile_id),
                metadata={"draftVersion": expected_draft_version + 1},
            )
        return (await self.list_profile_versions(profile_id, include_config=True))[0]

    async def publish_profile(
        self, actor_id: str, profile_id: UUID, expected_draft_version: int
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            profile = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.capability_profiles WHERE id=:id FOR UPDATE"),
                        {"id": profile_id},
                    )
                )
                .mappings()
                .first()
            )
            if not profile:
                raise ModelGovernanceError(404, "PROFILE_NOT_FOUND", "Profile not found")
            draft = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.capability_profile_versions WHERE profile_id=:id AND state='draft' FOR UPDATE"
                        ),
                        {"id": profile_id},
                    )
                )
                .mappings()
                .first()
            )
            if not draft or draft["draft_version"] != expected_draft_version:
                raise ModelGovernanceError(
                    409, "VERSION_CONFLICT", "Profile draft was changed by another administrator"
                )
            cfg = parse_profile_config(draft["config"], profile["workflow"])
            refs = self._profile_model_references(cfg)
            for ref, expected_capability in refs:
                model = await self._locked_model_health(conn, ref)
                if (
                    not model
                    or model["capability"] != expected_capability.value
                    or (
                        expected_capability == ModelCapability.EMBEDDING
                        and model["embedding_dimension"] != getattr(cfg, "dimension", None)
                    )
                    or not model["enabled"]
                    or not model["validated"]
                    or not model["gateway_enabled"]
                    or model["health_state"] not in {"healthy", "degraded"}
                ):
                    raise ModelGovernanceError(
                        409, "MODEL_UNAVAILABLE", "All profile models must be validated and enabled"
                    )
            semantic_version = int(profile["current_version"]) + 1
            now = utcnow()
            published_version = semantic_version
            # The draft occupies the next semantic version slot.  Publishing
            # promotes it in place, preserving its optimistic edit history.
            await conn.execute(
                text(
                    "UPDATE ima.capability_profile_versions SET state='published',published_at=:now,published_by=:actor,updated_at=:now WHERE profile_id=:id AND version=:version"
                ),
                {"id": profile_id, "version": draft["version"], "now": now, "actor": actor_id},
            )
            next_draft = published_version + 1
            await conn.execute(
                text(
                    "INSERT INTO ima.capability_profile_versions(profile_id,version,state,config,config_digest,draft_version,created_by,created_at,updated_at) VALUES (:id,:version,'draft',:config,:digest,1,:actor,:now,:now)"
                ),
                {
                    "id": profile_id,
                    "version": next_draft,
                    "config": json.dumps(canonical_config(cfg), ensure_ascii=True),
                    "digest": config_digest(cfg),
                    "actor": actor_id,
                    "now": now,
                },
            )
            await conn.execute(
                text(
                    "UPDATE ima.capability_profiles SET current_version=:version,updated_by=:actor,updated_at=:now WHERE id=:id"
                ),
                {"version": semantic_version, "actor": actor_id, "now": now, "id": profile_id},
            )
            await self._audit(
                conn,
                actor_id,
                "model.profile.published",
                target_type="capability_profile",
                target_id=str(profile_id),
                metadata={"version": semantic_version},
            )
            result = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.capability_profile_versions WHERE profile_id=:id AND version=:version"
                        ),
                        {"id": profile_id, "version": published_version},
                    )
                )
                .mappings()
                .one()
            )
        return {
            "profileId": result["profile_id"],
            "version": result["version"],
            "state": result["state"],
            "config": None,
            "configDigest": result["config_digest"],
            "draftVersion": result["draft_version"],
            "publishedAt": result["published_at"],
            "disabledAt": result["disabled_at"],
            "createdAt": result["created_at"],
            "updatedAt": result["updated_at"],
        }

    async def set_profile_disabled(
        self, actor_id: str, profile_id: UUID, disabled: bool, expected_version: int | None = None
    ) -> None:
        async with self.engine.begin() as conn:
            current = await conn.scalar(
                text("SELECT current_version FROM ima.capability_profiles WHERE id=:id FOR UPDATE"),
                {"id": profile_id},
            )
            if current is None:
                raise ModelGovernanceError(404, "PROFILE_NOT_FOUND", "Profile not found")
            if expected_version is not None and int(current) != expected_version:
                raise ModelGovernanceError(
                    409, "VERSION_CONFLICT", "Profile was changed by another administrator"
                )
            await conn.execute(
                text(
                    "UPDATE ima.capability_profiles SET lifecycle=:state,updated_by=:actor,updated_at=:now WHERE id=:id"
                ),
                {
                    "state": "disabled" if disabled else "active",
                    "actor": actor_id,
                    "now": utcnow(),
                    "id": profile_id,
                },
            )
            await self._audit(
                conn,
                actor_id,
                "model.profile.disabled" if disabled else "model.profile.restored",
                target_type="capability_profile",
                target_id=str(profile_id),
            )

    async def validate_profile(self, actor_id: str, profile_id: UUID) -> dict[str, object]:
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT p.workflow,v.config FROM ima.capability_profiles p JOIN ima.capability_profile_versions v ON v.profile_id=p.id AND v.state='draft' WHERE p.id=:id"
                        ),
                        {"id": profile_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise ModelGovernanceError(404, "PROFILE_NOT_FOUND", "Profile draft not found")
            try:
                config = parse_profile_config(row["config"], row["workflow"])
            except Exception:
                await self._audit(
                    conn,
                    actor_id,
                    "model.profile.validated",
                    target_type="capability_profile",
                    target_id=str(profile_id),
                    result="failed",
                    reason="INVALID_PROFILE_CONFIG",
                )
                return {"ok": False, "reasonCode": "INVALID_PROFILE_CONFIG"}
            available = True
            references = self._profile_model_references(config)
            for reference, expected_capability in references:
                model = (
                    (
                        await conn.execute(
                            text(
                                "SELECT m.capability,m.embedding_dimension,m.enabled,m.validated,g.enabled gateway_enabled,COALESCE(h.state,'unknown') health_state FROM ima.governed_models m JOIN ima.model_gateways g ON g.id=m.gateway_id LEFT JOIN ima.model_gateway_health h ON h.gateway_id=g.id AND h.capability=m.capability WHERE m.id=:id"
                            ),
                            {"id": reference},
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    not model
                    or model["capability"] != expected_capability.value
                    or (
                        expected_capability == ModelCapability.EMBEDDING
                        and model["embedding_dimension"] != getattr(config, "dimension", None)
                    )
                    or not model["enabled"]
                    or not model["validated"]
                    or not model["gateway_enabled"]
                    or model["health_state"] not in {"healthy", "degraded"}
                ):
                    available = False
            reason = None if available else "MODEL_UNAVAILABLE"
            await self._audit(
                conn,
                actor_id,
                "model.profile.validated",
                target_type="capability_profile",
                target_id=str(profile_id),
                result="success" if available else "failed",
                reason=reason,
            )
            return {"ok": available, "reasonCode": reason}

    async def delete_profile(self, actor_id: str, profile_id: UUID) -> None:
        async with self.engine.begin() as conn:
            if await conn.scalar(
                text("SELECT 1 FROM ima.kb_profile_assignments WHERE profile_id=:id LIMIT 1"),
                {"id": profile_id},
            ):
                raise ModelGovernanceError(
                    409, "DEPENDENCY_CONFLICT", "Profile has knowledge base assignments"
                )
            row = await conn.scalar(
                text("SELECT lifecycle FROM ima.capability_profiles WHERE id=:id FOR UPDATE"),
                {"id": profile_id},
            )
            if row is None:
                raise ModelGovernanceError(404, "PROFILE_NOT_FOUND", "Profile not found")
            if row == "active":
                raise ModelGovernanceError(
                    409, "PROFILE_ACTIVE", "Disable a profile before deletion"
                )
            await conn.execute(
                text("DELETE FROM ima.capability_profile_versions WHERE profile_id=:id"),
                {"id": profile_id},
            )
            await conn.execute(
                text("DELETE FROM ima.capability_profiles WHERE id=:id"), {"id": profile_id}
            )
            await self._audit(
                conn,
                actor_id,
                "model.profile.deleted",
                target_type="capability_profile",
                target_id=str(profile_id),
            )

    async def clone_profile(
        self, actor_id: str, profile_id: UUID, alias: str | None, description: str | None
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT p.*,v.config FROM ima.capability_profiles p JOIN ima.capability_profile_versions v ON v.profile_id=p.id AND v.version=p.current_version WHERE p.id=:id AND v.state='published'"
                        ),
                        {"id": profile_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise ModelGovernanceError(
                    404, "PROFILE_VERSION_NOT_FOUND", "Published profile version not found"
                )
            new_id = uuid4()
            now = utcnow()
            await conn.execute(
                text(
                    "INSERT INTO ima.capability_profiles(id,workflow,business_alias,description,current_version,created_by,updated_by,created_at,updated_at) VALUES (:id,:workflow,:alias,:description,0,:actor,:actor,:now,:now)"
                ),
                {
                    "id": new_id,
                    "workflow": row["workflow"],
                    "alias": alias or f"{row['business_alias']} draft",
                    "description": description or row["description"],
                    "actor": actor_id,
                    "now": now,
                },
            )
            cfg = canonical_config(parse_profile_config(row["config"], row["workflow"]))
            await conn.execute(
                text(
                    "INSERT INTO ima.capability_profile_versions(profile_id,version,state,config,config_digest,created_by,created_at,updated_at) VALUES (:id,1,'draft',CAST(:config AS jsonb),:digest,:actor,:now,:now)"
                ),
                {
                    "id": new_id,
                    "config": json.dumps(cfg, ensure_ascii=True),
                    "digest": config_digest(cfg),
                    "actor": actor_id,
                    "now": now,
                },
            )
            await self._audit(
                conn,
                actor_id,
                "model.profile.cloned",
                target_type="capability_profile",
                target_id=str(new_id),
                metadata={"sourceProfileId": str(profile_id)},
            )
            result = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.capability_profiles WHERE id=:id"), {"id": new_id}
                    )
                )
                .mappings()
                .one()
            )
        return self._profile_payload(result, include_config=False)

    async def profile_diff(
        self, profile_id: UUID, from_version: int, to_version: int
    ) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT version,config FROM ima.capability_profile_versions WHERE profile_id=:id AND version IN (:from_version,:to_version)"
                        ),
                        {"id": profile_id, "from_version": from_version, "to_version": to_version},
                    )
                )
                .mappings()
                .all()
            )
        values = {int(row["version"]): row["config"] for row in rows}
        if from_version not in values or to_version not in values:
            raise ModelGovernanceError(
                404, "PROFILE_VERSION_NOT_FOUND", "Profile version not found"
            )
        before = values[from_version]
        after = values[to_version]
        fields = (
            tuple(sorted(set(before) | set(after)))
            if isinstance(before, dict) and isinstance(after, dict)
            else ()
        )
        changed = tuple(field for field in fields if before.get(field) != after.get(field))
        return {
            "profileId": profile_id,
            "fromVersion": from_version,
            "toVersion": to_version,
            "changedFields": changed,
        }

    async def discover_gateway(self, gateway_id: UUID) -> tuple[str, ...]:
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,normalized_base_url,insecure_private,secret_id,custom_ca_ref FROM ima.model_gateways WHERE id=:id"
                        ),
                        {"id": gateway_id},
                    )
                )
                .mappings()
                .first()
            )
        if not row:
            raise ModelGovernanceError(404, "GATEWAY_NOT_FOUND", "Gateway not found")
        try:
            return await self._client_for_gateway(row).discover(
                row["normalized_base_url"],
                api_key=await self._decrypt_secret(row["id"], row["secret_id"]),
                custom_ca_ref=row["custom_ca_ref"],
                insecure_private=row["insecure_private"],
            )
        except GatewayError as exc:
            raise ModelGovernanceError(502, exc.code, "Gateway discovery failed") from exc

    async def check_gateway_health(
        self, actor_id: str | None, gateway_id: UUID, capability: ModelCapability | None = None
    ) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            gateway = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.model_gateways WHERE id=:id"), {"id": gateway_id}
                    )
                )
                .mappings()
                .first()
            )
            if not gateway:
                raise ModelGovernanceError(404, "GATEWAY_NOT_FOUND", "Gateway not found")
            models = (
                (
                    await conn.execute(
                        text(
                            """SELECT m.*,h.state current_health_state,h.reason_code current_reason_code,
                            h.latency_ms current_latency_ms,h.checked_at current_checked_at,
                            h.next_check_at current_next_check_at,h.consecutive_failures current_failures
                            FROM ima.governed_models m
                            LEFT JOIN ima.model_gateway_health h ON h.gateway_id=m.gateway_id AND h.capability=m.capability
                            WHERE m.gateway_id=:id AND (CAST(:capability AS varchar) IS NULL OR m.capability=:capability)
                            ORDER BY m.capability,m.remote_name"""
                        ),
                        {"id": gateway_id, "capability": capability.value if capability else None},
                    )
                )
                .mappings()
                .all()
            )
        results: list[dict[str, Any]] = []
        failures_by_capability: dict[str, int] = {}
        now = utcnow()
        for model in models:
            next_check = model.get("current_next_check_at")
            if next_check is not None and next_check > now:
                capability_name = str(model["capability"])
                results.append(
                    {
                        "capability": capability_name,
                        "state": model.get("current_health_state") or "unknown",
                        "reasonCode": model.get("current_reason_code"),
                        "latencyMs": model.get("current_latency_ms"),
                    }
                )
                failures_by_capability[capability_name] = int(model.get("current_failures") or 0)
                continue
            ok, reason, latency = await self._client_for_gateway(gateway).probe(
                gateway["normalized_base_url"],
                model["capability"],
                model["remote_name"],
                dimension=model["embedding_dimension"],
                api_key=await self._decrypt_secret(gateway["id"], gateway["secret_id"]),
                custom_ca_ref=gateway["custom_ca_ref"],
                insecure_private=gateway["insecure_private"],
            )
            results.append(
                {
                    "capability": model["capability"],
                    "state": "healthy" if ok else "unavailable",
                    "reasonCode": reason,
                    "latencyMs": latency,
                }
            )
            failures_by_capability[str(model["capability"])] = (
                0 if ok else int(model.get("current_failures") or 0) + 1
            )
        async with self.engine.begin() as conn:
            for item in results:
                await conn.execute(
                    text(
                        "INSERT INTO ima.model_gateway_health(gateway_id,capability,state,reason_code,latency_ms,checked_at,next_check_at,consecutive_failures) VALUES (:gateway,:capability,:state,:reason,:latency,:now,:next,:failures) ON CONFLICT(gateway_id,capability) DO UPDATE SET state=EXCLUDED.state,reason_code=EXCLUDED.reason_code,latency_ms=EXCLUDED.latency_ms,checked_at=EXCLUDED.checked_at,next_check_at=EXCLUDED.next_check_at,consecutive_failures=EXCLUDED.consecutive_failures"
                    ),
                    {
                        "gateway": gateway_id,
                        "capability": item["capability"],
                        "state": item["state"],
                        "reason": item["reasonCode"],
                        "latency": item["latencyMs"],
                        "now": utcnow(),
                        "next": now
                        + timedelta(seconds=self.settings.model_health_min_interval_seconds),
                        "failures": failures_by_capability.get(str(item["capability"]), 0),
                    },
                )
            await self._audit(
                conn,
                actor_id,
                "model.gateway.health_checked",
                target_type="model_gateway",
                target_id=str(gateway_id),
                metadata={"capabilities": len(results)},
            )
        return results

    async def assign_profile(
        self,
        actor_id: str,
        kb_id: str,
        workflow: Workflow,
        profile_id: UUID,
        profile_version: int,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            profile = (
                (
                    await conn.execute(
                        text(
                            "SELECT p.*,v.state,v.config FROM ima.capability_profiles p JOIN ima.capability_profile_versions v ON v.profile_id=p.id AND v.version=:version WHERE p.id=:id AND p.workflow=:workflow FOR SHARE"
                        ),
                        {"id": profile_id, "version": profile_version, "workflow": workflow.value},
                    )
                )
                .mappings()
                .first()
            )
            if not profile or profile["state"] != "published" or profile["lifecycle"] != "active":
                raise ModelGovernanceError(
                    409, "PROFILE_UNAVAILABLE", "Only active published profiles can be assigned"
                )
            if not await conn.scalar(
                text("SELECT 1 FROM ima.knowledge_bases WHERE id=:id AND is_active"),
                {"id": kb_id},
            ):
                raise ModelGovernanceError(404, "KB_NOT_FOUND", "Knowledge base not found")
            current = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.kb_profile_assignments WHERE kb_id=:kb AND workflow=:workflow FOR UPDATE"
                        ),
                        {"kb": kb_id, "workflow": workflow.value},
                    )
                )
                .mappings()
                .first()
            )
            if current and expected_version is not None and current["version"] != expected_version:
                raise ModelGovernanceError(
                    409, "VERSION_CONFLICT", "Assignment was changed by another administrator"
                )
            cfg = parse_profile_config(profile["config"], workflow)
            if workflow == Workflow.EMBEDDING:
                dimension = cast(EmbeddingConfig, cfg).dimension
                affected = (
                    await conn.scalar(
                        text(
                            "SELECT count(*) FROM ima.model_dependency_index WHERE active AND model_id IS NOT NULL AND dependency_kind IN ('target_index','legacy_index') AND kb_id=:kb"
                        ),
                        {"kb": kb_id},
                    )
                    or 0
                )
                if affected:
                    old_dim = await conn.scalar(
                        text(
                            "SELECT dimension FROM ima.model_dependency_index WHERE kb_id=:kb AND active ORDER BY updated_at DESC LIMIT 1"
                        ),
                        {"kb": kb_id},
                    )
                    if old_dim != dimension:
                        raise ModelGovernanceError(
                            409,
                            "REINDEX_REQUIRED",
                            "Embedding assignment requires a completed reindex",
                        )
            now = utcnow()
            version = int(current["version"]) + 1 if current else 1
            await conn.execute(
                text(
                    """INSERT INTO ima.kb_profile_assignments(kb_id,workflow,profile_id,profile_version,version,availability,availability_reason,assigned_by,assigned_at) VALUES (:kb,:workflow,:profile,:profile_version,:version,'available',NULL,:actor,:now) ON CONFLICT(kb_id,workflow) DO UPDATE SET profile_id=EXCLUDED.profile_id,profile_version=EXCLUDED.profile_version,version=EXCLUDED.version,availability=EXCLUDED.availability,availability_reason=NULL,assigned_by=EXCLUDED.assigned_by,assigned_at=EXCLUDED.assigned_at"""
                ),
                {
                    "kb": kb_id,
                    "workflow": workflow.value,
                    "profile": profile_id,
                    "profile_version": profile_version,
                    "version": version,
                    "actor": actor_id,
                    "now": now,
                },
            )
            await self._audit(
                conn,
                actor_id,
                "model.assignment.updated",
                target_type="knowledge_base",
                target_id=kb_id,
                metadata={"workflow": workflow.value, "profileVersion": profile_version},
            )
            result = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.kb_profile_assignments WHERE kb_id=:kb AND workflow=:workflow"
                        ),
                        {"kb": kb_id, "workflow": workflow.value},
                    )
                )
                .mappings()
                .one()
            )
        return dict(result)

    async def remove_assignment(
        self,
        actor_id: str,
        kb_id: str,
        workflow: Workflow,
        expected_version: int | None = None,
    ) -> None:
        async with self.engine.begin() as conn:
            current = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.kb_profile_assignments WHERE kb_id=:kb AND workflow=:workflow FOR UPDATE"
                        ),
                        {"kb": kb_id, "workflow": workflow.value},
                    )
                )
                .mappings()
                .first()
            )
            if not current:
                raise ModelGovernanceError(404, "ASSIGNMENT_NOT_FOUND", "Assignment not found")
            if expected_version is not None and current["version"] != expected_version:
                raise ModelGovernanceError(
                    409, "VERSION_CONFLICT", "Assignment was changed by another administrator"
                )
            await conn.execute(
                text(
                    "DELETE FROM ima.kb_profile_assignments WHERE kb_id=:kb AND workflow=:workflow"
                ),
                {"kb": kb_id, "workflow": workflow.value},
            )
            await self._audit(
                conn,
                actor_id,
                "model.assignment.removed",
                target_type="knowledge_base",
                target_id=kb_id,
                metadata={"workflow": workflow.value},
            )

    @staticmethod
    def _scene_default_slot(operation: str) -> str:
        return {
            "chat": "chatModelId",
            "embedding": "embeddingModelId",
            "rerank": "rerankModelId",
        }[operation]

    async def list_scene_defaults(self) -> list[dict[str, Any]]:
        """Report every workflow's scene default (model slot or None)."""
        async with self.engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            """SELECT d.workflow,p.id profile_id,p.current_version profile_version,v.config FROM ima.scene_defaults d JOIN ima.capability_profiles p ON p.id=d.profile_id JOIN ima.capability_profile_versions v ON v.profile_id=p.id AND v.version=p.current_version AND v.state='published' ORDER BY d.workflow"""
                        )
                    )
                )
                .mappings()
                .all()
            )
        by_workflow = {row["workflow"]: row for row in rows}
        result: list[dict[str, Any]] = []
        for workflow in Workflow:
            row = by_workflow.get(workflow.value)
            model_id = None
            if row:
                try:
                    config = parse_profile_config(row["config"], workflow)
                except Exception:
                    config = None
                slot = {
                    "chat": "chat_model_id",
                    "embedding": "embedding_model_id",
                    "rerank": "rerank_model_id",
                }[WORKFLOW_OPERATION[workflow]]
                model_id = getattr(config, slot, None) if config else None
            result.append(
                {
                    "workflow": workflow.value,
                    "profileId": row["profile_id"] if row else None,
                    "profileVersion": int(row["profile_version"]) if row else None,
                    "modelId": str(model_id) if model_id else None,
                }
            )
        return result

    async def scene_default_config(self, workflow: Workflow) -> dict[str, Any] | None:
        """Return the workflow's published scene-default config, or None if unset.

        Uses the same joins as the ``_execution_target`` fallback so config
        composition and execution resolution always agree on what is active.
        """
        async with self.engine.connect() as conn:
            config = await conn.scalar(
                text(
                    """SELECT v.config FROM ima.scene_defaults d JOIN ima.capability_profiles p ON p.id=d.profile_id JOIN ima.capability_profile_versions v ON v.profile_id=p.id AND v.version=p.current_version AND v.state='published' WHERE d.workflow=:workflow"""
                ),
                {"workflow": workflow.value},
            )
        return dict(config) if config else None

    @staticmethod
    def _scene_default_config(workflow: Workflow, model: Any) -> dict[str, Any]:
        """Build a minimal valid profile config around one scene-default model."""
        if workflow == Workflow.EMBEDDING:
            return {
                "embeddingModelId": str(model["id"]),
                "dimension": int(model["embedding_dimension"]),
            }
        if workflow == Workflow.RERANKING:
            return {"rerankModelId": str(model["id"])}
        return {
            "chatModelId": str(model["id"]),
            "systemPrompt": "You are a helpful assistant.",
            "contextLimit": int(model["context_limit"] or 32768),
            "outputLimit": int(model["output_limit"] or 2048),
        }

    async def set_scene_default(
        self, actor_id: str, workflow: Workflow, model_id: UUID | None
    ) -> dict[str, Any]:
        """Publish ``model_id`` as the workflow's scene default (None clears it)."""
        if model_id is None:
            return await self.clear_scene_default(actor_id, workflow)
        operation = WORKFLOW_OPERATION[workflow]
        capability = {
            "chat": ModelCapability.CHAT,
            "embedding": ModelCapability.EMBEDDING,
            "rerank": ModelCapability.RERANK,
        }[operation]
        async with self.engine.connect() as conn:
            model = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,capability,enabled,embedding_dimension,context_limit,output_limit FROM ima.governed_models WHERE id=:id"
                        ),
                        {"id": model_id},
                    )
                )
                .mappings()
                .first()
            )
        if not model:
            raise ModelGovernanceError(422, "MODEL_NOT_FOUND", "Model not found")
        if not model["enabled"]:
            raise ModelGovernanceError(422, "MODEL_DISABLED", "Model is disabled")
        if model["capability"] != capability.value:
            raise ModelGovernanceError(
                422,
                "CAPABILITY_MISMATCH",
                "Model capability does not match the workflow operation",
            )
        current = next(
            item for item in await self.list_scene_defaults() if item["workflow"] == workflow.value
        )
        if current["modelId"] == str(model_id):
            return current
        async with self.engine.connect() as conn:
            profile = (
                (
                    await conn.execute(
                        text(
                            "SELECT id FROM ima.capability_profiles WHERE workflow=:workflow AND lower(business_alias)=lower(:alias)"
                        ),
                        {"workflow": workflow.value, "alias": SCENE_DEFAULT_ALIAS},
                    )
                )
                .mappings()
                .first()
            )
        fresh = False
        if profile:
            profile_id = UUID(str(profile["id"]))
        else:
            try:
                created = await self.create_profile(
                    actor_id,
                    workflow,
                    SCENE_DEFAULT_ALIAS,
                    "系统管理的场景默认模型配置",
                    self._scene_default_config(workflow, model),
                )
            except Exception as exc:
                # Two administrators racing to create the same managed profile
                # resolve to the existing winner instead of a raw 500.
                if "unique" not in str(exc).lower():
                    raise
                async with self.engine.connect() as conn:
                    profile = (
                        (
                            await conn.execute(
                                text(
                                    "SELECT id FROM ima.capability_profiles WHERE workflow=:workflow AND lower(business_alias)=lower(:alias)"
                                ),
                                {"workflow": workflow.value, "alias": SCENE_DEFAULT_ALIAS},
                            )
                        )
                        .mappings()
                        .first()
                    )
                if not profile:
                    raise
                profile_id = UUID(str(profile["id"]))
            else:
                profile_id = UUID(str(created["id"]))
                fresh = True
                try:
                    await self.publish_profile(actor_id, profile_id, 1)
                except ModelGovernanceError:
                    await self._discard_scene_profile(profile_id)
                    raise
        if not fresh:
            published_config = await self._scene_published_config(profile_id)
            versions = await self.list_profile_versions(profile_id, include_config=False)
            draft = next((item for item in versions if item["state"] == "draft"), None)
            if draft is None:
                raise ModelGovernanceError(
                    409, "NO_DRAFT", "Scene default profile has no editable draft"
                )
            base = (
                dict(published_config)
                if published_config
                else self._scene_default_config(workflow, model)
            )
            base[self._scene_default_slot(operation)] = str(model_id)
            if workflow == Workflow.EMBEDDING:
                base["dimension"] = int(model["embedding_dimension"])
            await self.patch_profile_draft(actor_id, profile_id, base, draft["draftVersion"])
            await self.publish_profile(actor_id, profile_id, draft["draftVersion"] + 1)
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO ima.scene_defaults(workflow,profile_id,updated_at,updated_by) VALUES (:workflow,:profile,:now,:actor) ON CONFLICT(workflow) DO UPDATE SET profile_id=EXCLUDED.profile_id,updated_at=EXCLUDED.updated_at,updated_by=EXCLUDED.updated_by"
                ),
                {
                    "workflow": workflow.value,
                    "profile": profile_id,
                    "now": utcnow(),
                    "actor": actor_id,
                },
            )
            await self._audit(
                conn,
                actor_id,
                "model.scene_default.updated",
                target_type="scene_default",
                target_id=workflow.value,
                metadata={"profileId": str(profile_id), "modelId": str(model_id)},
            )
        return next(
            item for item in await self.list_scene_defaults() if item["workflow"] == workflow.value
        )

    async def clear_scene_default(self, actor_id: str, workflow: Workflow) -> dict[str, Any]:
        """Remove the workflow's scene default pointer; the managed profile stays."""
        current = next(
            item for item in await self.list_scene_defaults() if item["workflow"] == workflow.value
        )
        if current["profileId"] is None:
            return current
        async with self.engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM ima.scene_defaults WHERE workflow=:workflow"),
                {"workflow": workflow.value},
            )
            await self._audit(
                conn,
                actor_id,
                "model.scene_default.cleared",
                target_type="scene_default",
                target_id=workflow.value,
                metadata={"profileId": str(current["profileId"])},
            )
        return next(
            item for item in await self.list_scene_defaults() if item["workflow"] == workflow.value
        )

    async def _scene_published_config(self, profile_id: UUID) -> dict[str, Any] | None:
        async with self.engine.connect() as conn:
            config = await conn.scalar(
                text(
                    "SELECT v.config FROM ima.capability_profile_versions v WHERE v.profile_id=:id AND v.version=(SELECT current_version FROM ima.capability_profiles WHERE id=:id) AND v.state='published'"
                ),
                {"id": profile_id},
            )
        return dict(config) if config else None

    async def _discard_scene_profile(self, profile_id: UUID) -> None:
        """Remove a just-created scene profile whose first publish failed."""
        async with self.engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM ima.capability_profile_versions WHERE profile_id=:id"),
                {"id": profile_id},
            )
            await conn.execute(
                text("DELETE FROM ima.capability_profiles WHERE id=:id"), {"id": profile_id}
            )

    async def kb_capabilities(self, user_id: str, kb_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            if not await conn.scalar(
                text(
                    "SELECT 1 FROM ima.kb_members m JOIN ima.users u ON u.id=m.user_id JOIN ima.knowledge_bases kb ON kb.id=m.kb_id WHERE m.user_id=:user AND m.kb_id=:kb AND m.state='active' AND u.is_active AND kb.is_active"
                ),
                {"user": user_id, "kb": kb_id},
            ):
                raise ModelGovernanceError(404, "KB_NOT_FOUND", "Knowledge base not found")
            rows = (
                (
                    await conn.execute(
                        text(
                            """SELECT a.workflow,p.business_alias,p.description,p.current_version,a.profile_version,a.availability,a.availability_reason,p.lifecycle,v.state FROM ima.kb_profile_assignments a JOIN ima.capability_profiles p ON p.id=a.profile_id JOIN ima.capability_profile_versions v ON v.profile_id=a.profile_id AND v.version=a.profile_version WHERE a.kb_id=:kb ORDER BY a.workflow"""
                        ),
                        {"kb": kb_id},
                    )
                )
                .mappings()
                .all()
            )
        capabilities: list[dict[str, Any]] = []
        operation_for_workflow = {
            Workflow.GROUNDED_ASK: "chat",
            Workflow.TITLE_GENERATION: "chat",
            Workflow.SUMMARIZATION: "chat",
            Workflow.EMBEDDING: "embedding",
            Workflow.RERANKING: "rerank",
        }
        for row in rows:
            workflow = Workflow(row["workflow"])
            target = None
            if row["lifecycle"] == "active" and row["state"] == "published":
                target = await self._execution_target(
                    kb_id, workflow, operation_for_workflow[workflow], decrypt_secret=False
                )
            if not target or target.get("reason"):
                status = "unavailable"
                reason = (target or {}).get("reason") or row["availability_reason"] or "UNAVAILABLE"
            else:
                status = "degraded" if target.get("health_state") == "degraded" else "available"
                reason = row["availability_reason"]
            capabilities.append(
                {
                    "workflow": workflow.value,
                    "alias": row["business_alias"],
                    "description": row["description"],
                    "version": row["profile_version"],
                    "status": status,
                    "reason": reason,
                }
            )
        return capabilities

    async def _execution_target(
        self,
        kb_id: str,
        workflow: Workflow,
        operation: str,
        *,
        decrypt_secret: bool = True,
    ) -> dict[str, Any] | None:
        expected = {
            Workflow.GROUNDED_ASK: "chat",
            Workflow.TITLE_GENERATION: "chat",
            Workflow.SUMMARIZATION: "chat",
            Workflow.EMBEDDING: "embedding",
            Workflow.RERANKING: "rerank",
        }[workflow]
        if operation != expected:
            async with self.engine.begin() as conn:
                await self._audit(
                    conn,
                    None,
                    "model.execution.denied",
                    target_type="knowledge_base",
                    target_id=kb_id,
                    result="failed",
                    reason="WORKFLOW_OPERATION_MISMATCH",
                    metadata={"workflow": workflow.value, "operation": operation},
                )
            raise ModelGovernanceError(
                400, "WORKFLOW_OPERATION_MISMATCH", "Workflow and operation do not match"
            )
        async with self.engine.connect() as conn:
            raw_row = (
                (
                    await conn.execute(
                        text(
                            """SELECT a.*,p.workflow,p.lifecycle,v.state,v.config,g.id gateway_id,g.normalized_base_url,g.insecure_private,g.enabled gateway_enabled,g.secret_id,g.custom_ca_ref,g.allowed_hosts,g.allowed_cidrs,g.max_response_bytes,g.connect_timeout_ms,g.read_timeout_ms,g.write_timeout_ms,g.pool_timeout_ms,m.id model_id,m.version model_version,m.remote_name,m.capability,m.enabled model_enabled,m.validated,m.embedding_dimension,COALESCE(h.state,'unknown') health_state FROM ima.kb_profile_assignments a JOIN ima.capability_profiles p ON p.id=a.profile_id JOIN ima.capability_profile_versions v ON v.profile_id=a.profile_id AND v.version=a.profile_version JOIN ima.governed_models m ON m.id=CAST(CASE WHEN :operation='chat' THEN v.config->>'chatModelId' WHEN :operation='embedding' THEN v.config->>'embeddingModelId' WHEN :operation='rerank' THEN v.config->>'rerankModelId' END AS uuid) JOIN ima.model_gateways g ON g.id=m.gateway_id LEFT JOIN ima.model_gateway_health h ON h.gateway_id=g.id AND h.capability=m.capability WHERE a.kb_id=:kb AND a.workflow=:workflow"""
                        ),
                        {
                            "kb": kb_id,
                            "workflow": workflow.value,
                            "operation": operation,
                        },
                    )
                )
                .mappings()
                .first()
            )
        source: str | None = None
        if not raw_row:
            # A target assignment is authoritative even when its typed config
            # references a missing model (or a partially migrated row).  The
            # inner joins above intentionally prevent execution, but must not
            # turn that case into NO_ASSIGNMENT, which would hide the denial.
            async with self.engine.connect() as conn:
                assignment = (
                    (
                        await conn.execute(
                            text(
                                "SELECT profile_id,profile_version FROM ima.kb_profile_assignments WHERE kb_id=:kb AND workflow=:workflow"
                            ),
                            {"kb": kb_id, "workflow": workflow.value},
                        )
                    )
                    .mappings()
                    .first()
                )
            if assignment:
                return {
                    "profile_id": assignment["profile_id"],
                    "profile_version": assignment["profile_version"],
                    "reason": "UNAVAILABLE",
                }
            # No assignment row exists at all: the workflow's scene default
            # (if configured) is the managed fallback, resolved through the
            # same profile/version/model/gateway/health joins.
            async with self.engine.connect() as conn:
                raw_row = (
                    (
                        await conn.execute(
                            text(
                                """SELECT p.id profile_id,p.current_version profile_version,p.workflow,p.lifecycle,v.state,v.config,g.id gateway_id,g.normalized_base_url,g.insecure_private,g.enabled gateway_enabled,g.secret_id,g.custom_ca_ref,g.allowed_hosts,g.allowed_cidrs,g.max_response_bytes,g.connect_timeout_ms,g.read_timeout_ms,g.write_timeout_ms,g.pool_timeout_ms,m.id model_id,m.version model_version,m.remote_name,m.capability,m.enabled model_enabled,m.validated,m.embedding_dimension,COALESCE(h.state,'unknown') health_state FROM ima.scene_defaults d JOIN ima.capability_profiles p ON p.id=d.profile_id JOIN ima.capability_profile_versions v ON v.profile_id=p.id AND v.version=p.current_version AND v.state='published' JOIN ima.governed_models m ON m.id=CAST(CASE WHEN :operation='chat' THEN v.config->>'chatModelId' WHEN :operation='embedding' THEN v.config->>'embeddingModelId' WHEN :operation='rerank' THEN v.config->>'rerankModelId' END AS uuid) JOIN ima.model_gateways g ON g.id=m.gateway_id LEFT JOIN ima.model_gateway_health h ON h.gateway_id=g.id AND h.capability=m.capability WHERE d.workflow=:workflow"""
                            ),
                            {"workflow": workflow.value, "operation": operation},
                        )
                    )
                    .mappings()
                    .first()
                )
            if not raw_row:
                async with self.engine.begin() as conn:
                    await self._audit(
                        conn,
                        None,
                        "model.execution.denied",
                        target_type="knowledge_base",
                        target_id=kb_id,
                        result="failed",
                        reason="NO_ASSIGNMENT",
                        metadata={"workflow": workflow.value, "operation": operation},
                    )
                return None
            source = "scene_default"
        row = dict(raw_row)
        if source:
            row["source"] = source
        denial_metadata: dict[str, object] = {"workflow": workflow.value, "operation": operation}
        if source:
            denial_metadata["source"] = source
        if (
            row["lifecycle"] != "active"
            or row["state"] != "published"
            or not row["gateway_enabled"]
            or not row["model_enabled"]
            or not row["validated"]
            or row["health_state"] not in {"healthy", "degraded"}
        ):
            row["reason"] = "UNAVAILABLE"
            async with self.engine.begin() as conn:
                await self._audit(
                    conn,
                    None,
                    "model.execution.denied",
                    target_type="knowledge_base",
                    target_id=kb_id,
                    result="failed",
                    reason="UNAVAILABLE",
                    metadata=denial_metadata,
                )
            return row
        row["reason"] = None
        if decrypt_secret:
            row["api_key"] = await self._decrypt_gateway_secret(row)
        return row

    async def managed_chat(
        self,
        kb_id: str,
        workflow: Workflow,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, object]:
        row = await self._execution_target(kb_id, workflow, "chat")
        if not row:
            raise ModelGovernanceError(
                409, "NO_ASSIGNMENT", "No managed workflow assignment exists"
            )
        if row["reason"]:
            raise ModelGovernanceError(
                503, row["reason"], "Managed model capability is unavailable"
            )
        config = parse_profile_config(row["config"], workflow)
        system_prompt = getattr(config, "system_prompt", None)
        request_messages = (
            [{"role": "system", "content": system_prompt}] if system_prompt else []
        ) + messages
        payload: dict[str, object] = {
            "messages": request_messages,
            "max_tokens": min(int(getattr(config, "output_limit", 2048)), 524288),
            "temperature": float(getattr(config, "temperature", 0.2)),
        }
        if tools:
            payload["tools"] = tools
        return await self._client_for_gateway(row).chat_completion(
            row["normalized_base_url"],
            row["remote_name"],
            payload,
            api_key=row["api_key"],
            custom_ca_ref=row["custom_ca_ref"],
            insecure_private=row["insecure_private"],
        )

    async def managed_chat_stream(
        self,
        kb_id: str,
        workflow: Workflow,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[bytes]:
        row = await self._execution_target(kb_id, workflow, "chat")
        if not row:
            raise ModelGovernanceError(
                409, "NO_ASSIGNMENT", "No managed workflow assignment exists"
            )
        if row["reason"]:
            raise ModelGovernanceError(
                503, row["reason"], "Managed model capability is unavailable"
            )
        config = parse_profile_config(row["config"], workflow)
        system_prompt = getattr(config, "system_prompt", None)
        payload: dict[str, object] = {
            "messages": ([{"role": "system", "content": system_prompt}] if system_prompt else [])
            + messages,
            "max_tokens": min(int(getattr(config, "output_limit", 2048)), 524288),
            "temperature": float(getattr(config, "temperature", 0.2)),
        }
        if tools:
            payload["tools"] = tools
        async for chunk in self._client_for_gateway(row).stream_chat_completion(
            row["normalized_base_url"],
            row["remote_name"],
            payload,
            api_key=row["api_key"],
            custom_ca_ref=row["custom_ca_ref"],
            insecure_private=row["insecure_private"],
        ):
            yield chunk

    async def embedding_target(self, kb_id: str) -> dict[str, Any] | None:
        """Resolve the exact embedding execution target for a knowledge base.

        Thin public wrapper over :meth:`_execution_target` so ingestion resolves
        the embedding model through the same assignment-then-scene-default
        precedence and the same audit/denial semantics as retrieval.
        """
        return await self._execution_target(kb_id, Workflow.EMBEDDING, "embedding")

    async def managed_embeddings(
        self, kb_id: str, inputs: list[str]
    ) -> tuple[tuple[float, ...], ...]:
        row = await self._execution_target(kb_id, Workflow.EMBEDDING, "embedding")
        if not row:
            raise ModelGovernanceError(
                409, "NO_ASSIGNMENT", "No managed embedding assignment exists"
            )
        if row["reason"]:
            raise ModelGovernanceError(
                503, row["reason"], "Managed embedding capability is unavailable"
            )
        return await self._client_for_gateway(row).embeddings(
            row["normalized_base_url"],
            row["remote_name"],
            inputs,
            api_key=row["api_key"],
            custom_ca_ref=row["custom_ca_ref"],
            insecure_private=row["insecure_private"],
        )

    async def managed_rerank(
        self, kb_id: str, query: str, documents: list[str]
    ) -> tuple[tuple[int, float], ...]:
        row = await self._execution_target(kb_id, Workflow.RERANKING, "rerank")
        if not row:
            raise ModelGovernanceError(
                409, "NO_ASSIGNMENT", "No managed reranking assignment exists"
            )
        if row["reason"]:
            raise ModelGovernanceError(
                503, row["reason"], "Managed reranking capability is unavailable"
            )
        return await self._client_for_gateway(row).rerank(
            row["normalized_base_url"],
            row["remote_name"],
            query,
            documents,
            api_key=row["api_key"],
            custom_ca_ref=row["custom_ca_ref"],
            insecure_private=row["insecure_private"],
        )

    async def _decrypt_secret(
        self, gateway_id: UUID | str, secret_id: UUID | str | None
    ) -> str | None:
        if not secret_id:
            return None
        async with self.engine.connect() as conn:
            secret = (
                (
                    await conn.execute(
                        text("SELECT * FROM ima.model_gateway_secrets WHERE id=:id"),
                        {"id": secret_id},
                    )
                )
                .mappings()
                .first()
            )
        if not secret:
            raise ModelGovernanceError(
                503, "SECRET_UNAVAILABLE", "Gateway credential is unavailable"
            )
        try:
            return self.key_ring.decrypt(
                SecretEnvelope(
                    key_version=secret["key_version"],
                    nonce=secret["nonce"],
                    ciphertext=secret["ciphertext"],
                    fingerprint=secret["fingerprint"],
                ),
                gateway_id=str(gateway_id),
                secret_id=str(secret["id"]),
            )
        except SecretEnvelopeError as exc:
            raise ModelGovernanceError(
                503, "SECRET_UNAVAILABLE", "Gateway credential is unavailable"
            ) from exc

    async def _decrypt_gateway_secret(self, row: Any) -> str | None:
        return await self._decrypt_secret(row["gateway_id"], row.get("secret_id"))

    async def impact(self, model_id: UUID) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            model = (
                (
                    await conn.execute(
                        text("SELECT id,embedding_dimension FROM ima.governed_models WHERE id=:id"),
                        {"id": model_id},
                    )
                )
                .mappings()
                .first()
            )
            if not model:
                raise ModelGovernanceError(404, "MODEL_NOT_FOUND", "Model not found")
            rows = (
                (
                    await conn.execute(
                        text(
                            """SELECT a.kb_id,a.workflow,a.profile_version,m.id current_model_id,m.embedding_dimension current_dimension,count(d.id) affected_indexes,coalesce(array_agg(d.source_id) FILTER (WHERE d.source_id IS NOT NULL),'{}') affected_source_ids FROM ima.kb_profile_assignments a JOIN ima.capability_profile_versions v ON v.profile_id=a.profile_id AND v.version=a.profile_version LEFT JOIN ima.governed_models m ON m.id=CAST(v.config->>'embeddingModelId' AS uuid) LEFT JOIN ima.model_dependency_index d ON d.kb_id=a.kb_id AND d.active AND d.dependency_kind IN ('target_index','legacy_index') WHERE a.workflow='embedding' GROUP BY a.kb_id,a.workflow,a.profile_version,m.id,m.embedding_dimension"""
                        )
                    )
                )
                .mappings()
                .all()
            )
        affected = []
        for row in rows:
            if (
                row["current_model_id"] != model_id
                or row["current_dimension"] != model["embedding_dimension"]
            ):
                affected.append(
                    {
                        "kbId": row["kb_id"],
                        "workflow": row["workflow"],
                        "currentModelId": row["current_model_id"],
                        "currentDimension": row["current_dimension"],
                        "affectedIndexes": int(row["affected_indexes"]),
                        "affectedSourceIds": tuple(row["affected_source_ids"] or ()),
                    }
                )
        return {
            "modelId": model_id,
            "dimension": model["embedding_dimension"],
            "affected": tuple(affected),
            "requiresReindex": bool(affected),
        }


__all__ = ["ModelGovernanceError", "ModelGovernanceService"]
