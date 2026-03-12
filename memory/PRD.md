# Syroce Hotel PMS — Product Requirements Document

## Original Problem Statement
Enterprise hotel operating system platformunun production ortamına güvenli deploy edilmesi. Platform: PMS Core, Channel Manager, Revenue Engine, Operational AI, Guest Intelligence, Messaging Gateway, Revenue Autopilot katmanlarını içerir.

## Architecture
- **Backend**: FastAPI (Python) on port 8001
- **Frontend**: React on port 3000
- **Database**: MongoDB
- **Cache/PubSub**: Redis
- **Workers**: Celery
- **LB**: Nginx
- **Monitoring**: Prometheus + Grafana + OTel + Sentry
- **Alerting**: Alertmanager + Webhook (Slack/PagerDuty)

## Core Requirements
1. Multi-tenant hotel management with RBAC
2. Real-time operations via WebSocket + Redis pub/sub
3. Channel management for OTAs (Booking.com, Expedia, etc.)
4. Revenue engine with dynamic pricing
5. Guest intelligence and AI-powered operations
6. Messaging gateway (SMS/Email/WhatsApp)
7. Production-grade infrastructure with observability

## What's Been Implemented

### Phase 1: Core PMS (Complete)
- Room management, reservations, guest profiles
- Multi-tenant isolation, RBAC, audit trail
- Folio management, rate plans, channel connections

### Phase 2: Infrastructure Hardening (Complete)
- Redis cluster support, Celery workers
- Horizontal scaling readiness
- Backup & DR framework
- Security checklist, observability foundation

### Phase 3: Production Activation & Pre-Launch Verification (Complete — Feb 2026)
- Provider Test Connection Framework (Twilio, SendGrid, WhatsApp, Redis, Sentry, OTel)
- Production Config Activation Workflow
- Pre-Launch Validation Suite with readiness scoring
- Live Ops Alert Integration (webhooks)
- Enhanced Production Go-Live Dashboard (8 tabs)

### Phase 4: Production Deployment Infrastructure (Complete — Mar 2026)
- Full Docker Compose production stack (10 services)
- Enhanced Nginx with rate limiting, caching, TLS, security headers
- Kubernetes deployment manifests (backend, worker, ingress, HPA)
- Prometheus config with alert rules (critical, infrastructure, business)
- OTel Collector config (gRPC + HTTP, batch processing, filtering)
- Alertmanager routing (critical → PagerDuty+Slack, high → Slack)
- Grafana dashboards: Operations, Infrastructure, Business Metrics
- Deployment Orchestrator with risk assessment & strategy
- Secrets health monitoring & access logging
- Backup trigger, restore test, cleanup endpoints
- Horizontal scaling summary & statelessness check
- Production environment template

### Phase 5: PMS Operations Sayfasi Iyilestirmesi (Complete — Mar 2026)
- PMS Operations sayfasina Layout bileseni eklenerek ana uygulama ile tutarli hale getirildi
- Koyu tema (slate-950) kaldirildi, acik tema (white/gray) ile uyumlu tasarim uygulandi
- Turkce dil destegi eklendi (i18n): Tum KPI kartlari, sekmeler, oda durumlari, liste basliklari
- en.json ve tr.json locale dosyalarina pmsOperations bolumu eklendi
- navItems.js'de etiket Turkceye cevrildi

### Phase 6: Tum Uygulama i18n Turkce Dil Destegi (Complete — Mar 2026)
- tr.json'da 44+ cevrilmemis Ingilizce giris tamamen Turkceye cevrildi
- Navigasyon etiketleri (Layout.js) i18n destekli hale getirildi: t('navKeys.${item.key}')
- navKeys bolumu her iki locale dosyasina eklendi (37 navigasyon ogesi)
- FolioDetailView.js: Layout sarmalama + i18n + acik tema donusumu tamamlandi
- AdminControlPanel.js: Layout sarmalama + i18n (19 sekme etiketi) tamamlandi
- 16 teknik dashboard sayfasina useTranslation eklendi ve basliklari cevrildi
- GuestJourneyDashboard, RevenueEngineDashboard, OperationalEventDashboard: Basliklar i18n ile cevrildi
- adminPanel2 ve techDashboards ceviri bolumleri eklendi
- folio bolumune 50+ yeni ceviri anahtari eklendi
- Testing Agent: %100 basari orani ile dogrulandi

### Phase 7: 10 Dil Tam Destek (Complete — Mar 2026)
- 6 dil dosyasina (ar, de, es, fr, it, ru) 4 yeni bolum eklendi: navKeys, pmsOperations, adminPanel2, techDashboards
- pt.json (Portekizce) ve zh.json (Cince) dosyalari olusturuldu
- LanguageSelector bilesenine Deutsch, Portugues ve Cince eklendi (7'den 10'a)
- Her dil icin tam navigasyon cevirileri, PMS Operations tum ekranlari, Admin Panel sekmeleri, teknik dashboard basliklari
- Dogrulama: Ispanyolca ile tam sayfa testi basarili (navigasyon, KPI kartlari, oda durumlari, sekmeler, icerik)

## Key API Endpoints (Production Go-Live)
- `GET /api/production-golive/summary` — Full dashboard data
- `GET /api/production-golive/deployment/risk-assessment` — Safety/risk scores
- `GET /api/production-golive/deployment/strategy` — Deployment strategy & batches
- `GET /api/production-golive/deployment/infrastructure` — Topology & config inventory
- `GET /api/production-golive/deployment/first-batch` — First 5 deployment components
- `POST /api/production-golive/providers/{provider}/test` — Test provider connection
- `POST /api/production-golive/validate/run` — Run pre-launch validation
- `GET /api/production-golive/secrets/health` — Secrets provider health
- `POST /api/production-golive/backup/trigger` — Manual backup
- `GET /api/production-golive/scaling/summary` — Scaling status

## Infrastructure Config Files
- `infra/docker-compose.full-stack.yml` — 10-service production stack
- `infra/nginx/prod.conf` — Rate limiting, caching, TLS
- `infra/prometheus/prometheus.yml` — Scrape targets
- `infra/prometheus/alerts.yml` — Alert rules
- `infra/otel/otel-collector.yml` — Tracing & metrics pipeline
- `infra/alertmanager/alertmanager.yml` — Alert routing
- `infra/grafana/dashboards/*.json` — 3 comprehensive dashboards
- `infra/grafana/provisioning/` — Datasources & dashboard provisioning
- `infra/k8s/base.yml` — Namespace, ConfigMap, Secret, Ingress, PVC
- `infra/k8s/backend-deployment.yml` — Backend deploy + HPA
- `infra/k8s/worker-deployment.yml` — Worker deploy + HPA + Beat CronJob
- `infra/env.production.template` — Full production env template

## Prioritized Backlog
### P0 (Next)
- Real production deployment to cloud (AWS/GCP/Azure)
- Configure production secrets and credentials

### P1
- Activate Twilio/SendGrid/WhatsApp with real credentials
- Enable Sentry and OTel in production
- Configure Prometheus scraping against real services

### P2
- CI/CD pipeline (GitHub Actions / GitLab CI)
- Automated E2E tests in CI
- Load testing before launch

### P3
- Multi-region deployment
- CDN integration for frontend assets
- Database sharding strategy

## Kullanıcı Giriş Bilgileri (Test)
| Kullanıcı | E-posta | Şifre |
|---|---|---|
| **Demo Admin** | `demo@hotel.com` | `demo123` |
