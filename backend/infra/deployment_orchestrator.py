"""
Deployment Orchestrator — Production deployment risk assessment, config generation,
deployment strategy recommendation, and infrastructure readiness scoring.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("infra.deployment_orchestrator")


DEPLOYMENT_COMPONENTS = {
    "backend": {
        "type": "api",
        "replicas_min": 2,
        "replicas_max": 8,
        "cpu_limit": "2.0",
        "memory_limit": "2G",
        "health_endpoint": "/api/health/liveness",
        "critical": True,
    },
    "frontend": {
        "type": "static",
        "replicas_min": 2,
        "replicas_max": 4,
        "cpu_limit": "0.5",
        "memory_limit": "256M",
        "health_endpoint": "/",
        "critical": True,
    },
    "worker": {
        "type": "worker",
        "replicas_min": 2,
        "replicas_max": 10,
        "cpu_limit": "2.0",
        "memory_limit": "2G",
        "health_endpoint": None,
        "critical": True,
    },
    "beat": {
        "type": "scheduler",
        "replicas_min": 1,
        "replicas_max": 1,
        "cpu_limit": "0.25",
        "memory_limit": "256M",
        "health_endpoint": None,
        "critical": False,
    },
    "redis": {
        "type": "cache",
        "replicas_min": 1,
        "replicas_max": 3,
        "cpu_limit": "1.0",
        "memory_limit": "768M",
        "health_endpoint": None,
        "critical": True,
    },
    "nginx": {
        "type": "loadbalancer",
        "replicas_min": 1,
        "replicas_max": 2,
        "cpu_limit": "0.5",
        "memory_limit": "128M",
        "health_endpoint": "/health",
        "critical": True,
    },
    "otel-collector": {
        "type": "observability",
        "replicas_min": 1,
        "replicas_max": 2,
        "cpu_limit": "0.5",
        "memory_limit": "512M",
        "health_endpoint": None,
        "critical": False,
    },
    "prometheus": {
        "type": "monitoring",
        "replicas_min": 1,
        "replicas_max": 1,
        "cpu_limit": "0.5",
        "memory_limit": "1G",
        "health_endpoint": None,
        "critical": False,
    },
    "grafana": {
        "type": "dashboard",
        "replicas_min": 1,
        "replicas_max": 1,
        "cpu_limit": "0.5",
        "memory_limit": "512M",
        "health_endpoint": None,
        "critical": False,
    },
    "alertmanager": {
        "type": "alerting",
        "replicas_min": 1,
        "replicas_max": 1,
        "cpu_limit": "0.25",
        "memory_limit": "128M",
        "health_endpoint": None,
        "critical": False,
    },
}

RISK_FACTORS = {
    "no_redis": {"weight": 25, "description": "Redis not configured — cache/pubsub/event bus unavailable"},
    "no_backup": {"weight": 20, "description": "Backup system not enabled — data loss risk"},
    "no_monitoring": {"weight": 15, "description": "No observability stack — blind to production issues"},
    "no_alerting": {"weight": 15, "description": "No alert webhooks — no operational notifications"},
    "single_replica": {"weight": 10, "description": "Single backend replica — no fault tolerance"},
    "no_ssl": {"weight": 10, "description": "SSL not configured — insecure connections"},
    "weak_jwt": {"weight": 5, "description": "JWT secret too short — security risk"},
    "no_providers": {"weight": 5, "description": "No messaging providers — guest communication unavailable"},
}


class DeploymentOrchestrator:
    """Assesses deployment risk and generates deployment strategy."""

    def assess_risk(self) -> dict[str, Any]:
        """Full deployment risk assessment."""
        risks = []
        risk_score = 0

        if not os.environ.get("REDIS_URL"):
            risks.append({**RISK_FACTORS["no_redis"], "factor": "no_redis"})
            risk_score += RISK_FACTORS["no_redis"]["weight"]

        if os.environ.get("BACKUP_ENABLED", "false").lower() != "true":
            risks.append({**RISK_FACTORS["no_backup"], "factor": "no_backup"})
            risk_score += RISK_FACTORS["no_backup"]["weight"]

        if not os.environ.get("OTEL_EXPORTER_ENDPOINT") and not os.environ.get("SENTRY_DSN"):
            risks.append({**RISK_FACTORS["no_monitoring"], "factor": "no_monitoring"})
            risk_score += RISK_FACTORS["no_monitoring"]["weight"]

        webhook_count = sum(1 for k in ["OPS_WEBHOOK_URL", "SLACK_WEBHOOK_URL", "PAGERDUTY_WEBHOOK_URL"] if os.environ.get(k))
        if webhook_count == 0:
            risks.append({**RISK_FACTORS["no_alerting"], "factor": "no_alerting"})
            risk_score += RISK_FACTORS["no_alerting"]["weight"]

        jwt = os.environ.get("JWT_SECRET", "")
        if len(jwt) < 32:
            risks.append({**RISK_FACTORS["weak_jwt"], "factor": "weak_jwt"})
            risk_score += RISK_FACTORS["weak_jwt"]["weight"]

        provider_count = sum(1 for k in ["TWILIO_ACCOUNT_SID", "SENDGRID_API_KEY", "WHATSAPP_PROVIDER_KEY"] if os.environ.get(k))
        if provider_count == 0:
            risks.append({**RISK_FACTORS["no_providers"], "factor": "no_providers"})
            risk_score += RISK_FACTORS["no_providers"]["weight"]

        safety_score = max(0, 100 - risk_score)

        if safety_score >= 80:
            verdict = "LOW_RISK"
        elif safety_score >= 50:
            verdict = "MEDIUM_RISK"
        else:
            verdict = "HIGH_RISK"

        return {
            "assessed_at": datetime.now(UTC).isoformat(),
            "safety_score": safety_score,
            "risk_score": risk_score,
            "verdict": verdict,
            "risk_count": len(risks),
            "risks": risks,
            "mitigations": self._generate_mitigations(risks),
        }

    def _generate_mitigations(self, risks: list[dict]) -> list[str]:
        mitigations = []
        for r in risks:
            factor = r["factor"]
            if factor == "no_redis":
                mitigations.append("Configure REDIS_URL with a managed Redis instance (ElastiCache, Cloud Memorystore)")
            elif factor == "no_backup":
                mitigations.append("Set BACKUP_ENABLED=true and configure cloud backup target (S3, GCS)")
            elif factor == "no_monitoring":
                mitigations.append("Configure OTEL_EXPORTER_ENDPOINT or SENTRY_DSN for production observability")
            elif factor == "no_alerting":
                mitigations.append("Set SLACK_WEBHOOK_URL or PAGERDUTY_WEBHOOK_URL for ops alerting")
            elif factor == "weak_jwt":
                mitigations.append("Generate a strong JWT_SECRET (minimum 32 chars, use openssl rand -base64 48)")
            elif factor == "no_providers":
                mitigations.append("Configure at least one messaging provider (Twilio, SendGrid, WhatsApp)")
        return mitigations

    def get_deployment_strategy(self) -> dict[str, Any]:
        risk = self.assess_risk()
        safety = risk["safety_score"]

        if safety >= 80:
            strategy = "rolling_update"
            description = "Safe for rolling deployment. All critical services configured."
            batch_order = ["redis", "backend", "worker", "beat", "frontend", "nginx", "otel-collector", "prometheus", "grafana", "alertmanager"]
        elif safety >= 50:
            strategy = "blue_green"
            description = "Recommend blue-green deployment. Some risks present — validate after cutover."
            batch_order = ["redis", "otel-collector", "prometheus", "backend", "worker", "beat", "frontend", "nginx", "grafana", "alertmanager"]
        else:
            strategy = "canary"
            description = "High risk deployment. Use canary strategy with staged rollout."
            batch_order = ["redis", "otel-collector", "prometheus", "alertmanager", "backend", "worker", "beat", "frontend", "nginx", "grafana"]

        batches = []
        for i, component in enumerate(batch_order):
            comp = DEPLOYMENT_COMPONENTS.get(component, {})
            batches.append(
                {
                    "order": i + 1,
                    "component": component,
                    "type": comp.get("type", "unknown"),
                    "replicas": comp.get("replicas_min", 1),
                    "critical": comp.get("critical", False),
                    "health_check": comp.get("health_endpoint"),
                    "rollback_on_failure": comp.get("critical", False),
                }
            )

        return {
            "strategy": strategy,
            "description": description,
            "safety_score": safety,
            "components": DEPLOYMENT_COMPONENTS,
            "deployment_batches": batches,
            "estimated_duration_minutes": len(batches) * 3,
            "rollback_plan": {
                "auto_rollback": True,
                "health_check_interval_sec": 15,
                "failure_threshold": 3,
                "rollback_strategy": "previous_version",
            },
            "pre_deployment_checks": [
                "Run pre-launch validation suite",
                "Verify all secrets are configured",
                "Test provider connections",
                "Confirm backup is recent (< 24h)",
                "Validate Redis connectivity",
                "Check MongoDB replica set health",
            ],
            "post_deployment_checks": [
                "Verify all health endpoints respond 200",
                "Check Redis pub/sub functionality",
                "Confirm WebSocket connections",
                "Test messaging delivery (sandbox)",
                "Verify Prometheus scraping",
                "Check Grafana dashboard access",
            ],
        }

    def get_infra_summary(self) -> dict[str, Any]:
        """Infrastructure topology summary."""
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "components": DEPLOYMENT_COMPONENTS,
            "total_components": len(DEPLOYMENT_COMPONENTS),
            "critical_components": sum(1 for c in DEPLOYMENT_COMPONENTS.values() if c["critical"]),
            "config_files": {
                "docker_compose": "infra/docker-compose.full-stack.yml",
                "nginx": "infra/nginx/prod.conf",
                "prometheus": "infra/prometheus/prometheus.yml",
                "prometheus_alerts": "infra/prometheus/alerts.yml",
                "otel_collector": "infra/otel/otel-collector.yml",
                "alertmanager": "infra/alertmanager/alertmanager.yml",
                "grafana_datasources": "infra/grafana/provisioning/datasources.yml",
                "grafana_dashboards": "infra/grafana/provisioning/dashboards.yml",
                "k8s_base": "infra/k8s/base.yml",
                "k8s_backend": "infra/k8s/backend-deployment.yml",
                "k8s_worker": "infra/k8s/worker-deployment.yml",
            },
            "grafana_dashboards": [
                {"name": "Operations", "uid": "syroce-ops", "path": "infra/grafana/dashboards/operations.json"},
                {"name": "Infrastructure", "uid": "syroce-infra-v2", "path": "infra/grafana/dashboards/infrastructure.json"},
                {"name": "Business Metrics", "uid": "syroce-business", "path": "infra/grafana/dashboards/business.json"},
            ],
            "monitoring_stack": {
                "metrics": "Prometheus (port 9090)",
                "dashboards": "Grafana (port 3001)",
                "tracing": "OpenTelemetry Collector (gRPC 4317, HTTP 4318)",
                "alerting": "Alertmanager (port 9093) + Webhook delivery",
                "error_tracking": "Sentry (external)",
            },
            "security": {
                "tls": "TLSv1.2/1.3 via Nginx",
                "rate_limiting": "Nginx zones: api=60r/s, auth=10r/m, ws=5r/s",
                "headers": "HSTS, CSP, X-Frame, X-Content-Type, Referrer-Policy",
                "secrets": "K8s Secrets / AWS Secrets Manager / Vault",
            },
        }


deployment_orchestrator = DeploymentOrchestrator()
