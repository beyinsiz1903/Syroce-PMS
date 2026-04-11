# CDN Deployment Rehberi

## Frontend Global Dağıtım - CloudFront/Cloudflare

### 1. CloudFront Konfigürasyonu

```yaml
# cloudfront-distribution.yaml
Distribution:
  Origins:
    - DomainName: roomops-frontend.s3.amazonaws.com
      S3OriginConfig:
        OriginAccessIdentity: ''
      OriginAccessControlId: !Ref OAC
  
  DefaultCacheBehavior:
    ViewerProtocolPolicy: redirect-to-https
    CachePolicyId: !Ref CachePolicy
    OriginRequestPolicyId: !Ref OriginRequestPolicy
    Compress: true
    AllowedMethods: [GET, HEAD, OPTIONS]
    CachedMethods: [GET, HEAD]
  
  CacheBehaviors:
    - PathPattern: '/api/*'
      TargetOriginId: backend-alb
      CachePolicyId: CachingDisabled
      OriginRequestPolicyId: AllViewer
      AllowedMethods: [DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT]
      ViewerProtocolPolicy: https-only
    
    - PathPattern: '/static/*'
      TargetOriginId: s3-frontend
      CachePolicyId: CachingOptimized  # 1 year cache
      Compress: true
  
  PriceClass: PriceClass_100  # US, Europe, Asia
  HttpVersion: http2and3
  
  CustomErrorResponses:
    - ErrorCode: 404
      ResponsePagePath: /index.html
      ResponseCode: 200
      ErrorCachingMinTTL: 0
```

### 2. Cloudflare Konfigürasyonu

```toml
# wrangler.toml (Cloudflare Pages)
name = "roomops-frontend"
compatibility_date = "2025-01-01"

[site]
bucket = "./frontend/build"

[[headers]]
  for = "/static/*"
  [headers.values]
    Cache-Control = "public, max-age=31536000, immutable"

[[headers]]
  for = "/*.html"
  [headers.values]
    Cache-Control = "public, max-age=0, must-revalidate"

[[redirects]]
  from = "/api/*"
  to = "https://api.roomops.com/api/:splat"
  status = 200
```

### 3. Cache Stratejisi

| Kaynak | TTL | Strateji |
|--------|-----|----------|
| HTML (index.html) | 0 | always revalidate |
| JS/CSS (hashed) | 1 year | immutable |
| Images | 1 week | stale-while-revalidate |
| API responses | 0 | no-cache |
| Fonts | 1 year | immutable |

### 4. Performans Hedefleri

- **TTFB**: < 100ms (global)
- **FCP**: < 1.5s
- **LCP**: < 2.5s
- **CLS**: < 0.1
- **Availability**: 99.99%

### 5. SSL/TLS

- TLS 1.3 zorunlu
- HSTS header aktif
- Certificate: ACM (AWS) veya Cloudflare Universal SSL
