# Backend Requirements Split — Plan & Risk Map

**Date**: 2026-05-10
**Status**: PLAN ONLY — no requirements file, Dockerfile, or CI step changes
in this doc. This is the discussion zemini before any taslak dosya üretimi.
**Scope**: `backend/requirements.txt` (222 satır, ~210 paket) ve etkilediği
tüketiciler.

## 1. Mevcut Durum Haritası

### 1.1 Requirements dosyaları

| Dosya | Satır | Rol |
|-------|-------|-----|
| `backend/requirements.txt` | 222 | Tek aggregate — API + worker + ML + reports + integrations + dev hepsi içinde |
| `backend/requirements-ci.txt` | 3 | Sadece `-r requirements.txt` (sınıflandırma yok) |

### 1.2 Tüketiciler (split sırasında dokunulacak yerler)

| Tüketici | Şu an | Notlar |
|----------|-------|--------|
| `backend/Dockerfile` L12-14 | `pip install -r requirements.txt` + sonradan `litellm>=1.83.2 --no-deps` override | **Kritik**: litellm override split sonrası dokümante edilmeli |
| `worker/Dockerfile` L11-12 | `pip install -r backend/requirements.txt` (full set) | API ile aynı devasa set — küçültme fırsatı, ama riskli |
| `.github/workflows/ci-cd.yml` L105, L209, L337 | 3 ayrı job `pip install -r requirements.txt` | Hepsi aggregate'ten kuruyor |
| `.github/workflows/frontend-quality.yml` L74 | `pip install -r requirements.txt` | Frontend job neden backend req kuruyor? — ayrı incelenecek |
| `.github/workflows/ci-cd.yml` L383 | `--exclude="requirements.txt"` (rsync exclude) | **Önemli**: rsync exclude'u split sonrası `requirements/**` tüm klasörü dışlamalı |
| `backend/start.sh` | Doğrudan `requirements*` referansı yok (workflow zaten dependency olduğu varsayımıyla çalışır) | Replit dev workflow için güvenli |

### 1.3 Replit secrets / runtime context

`backend/start.sh` workflow'u Mongo Atlas + local Redis + uvicorn server
başlatır. Dependency kurulumu Replit ortamında **runtime'da değil** önceden
yapılmış varsayılır. Yani Replit dev tarafında split anlık kırmaz; risk
Docker/CI tarafında.

## 2. Hedef Grup Tablosu

Aşama 2'de oluşturulacak `backend/requirements/` alt klasörü için **plan**.
Bu sadece harita — henüz dosya üretilmedi.

| Grup | Amaç | Örnek paketler (aggregate'ten) | Risk |
|------|------|-------------------------------|------|
| `base.txt` | Her runtime'da gereken çekirdek | `pydantic`, `pydantic_core`, `python-dotenv`, `orjson`, `requests`, `httpx`, `httpcore`, `tenacity`, `PyJWT`, `cryptography`, `cffi`, `anyio`, `sniffio`, `typing_extensions`, `idna`, `urllib3`, `certifi`, `packaging`, `python-dateutil`, `pytz`, `tzdata`, `PyYAML`, `Jinja2`, `MarkupSafe`, `dnspython`, `email-validator`, `attrs`, `jsonschema`, `passlib`, `bcrypt`, `pyotp`, `python-jose`, `python-multipart`, `qrcode`, `pypng`, `holidays`, `humanize`, `pycountry`, `babel` | düşük |
| `api.txt` | FastAPI backend runtime | `fastapi`, `starlette`, `uvicorn[standard]`, `uvloop`, `httptools`, `watchfiles`, `websockets`, `motor`, `pymongo`, `strawberry-graphql`, `graphql-core`, `aiodataloader`, `python-socketio`, `python-engineio`, `simple-websocket`, `wsproto`, `bidict`, `prometheus_client`, `aiohttp`, `aiosignal`, `multidict`, `yarl`, `frozenlist`, `sentry-sdk[fastapi]` | orta |
| `worker.txt` | Celery + scheduler + flower | `celery`, `kombu`, `billiard`, `vine`, `amqp`, `redis`, `aioredis`, `APScheduler`, `flower`, `tornado`, `gevent`, `greenlet`, `Flask`, `Flask-BasicAuth`, `Flask-Login`, `Werkzeug` (flower dep), `prompt_toolkit`, `wcwidth`, `click-didyoumean`, `click-plugins`, `click-repl` | orta |
| `ml.txt` | AI/ML ağır paketler | `numpy`, `pandas`, `scipy`, `scikit-learn`, `xgboost`, `joblib`, `threadpoolctl`, `nltk`, `textblob`, `tokenizers`, `tiktoken`, `huggingface_hub`, `hf-xet`, `fsspec`, `nvidia-nccl-cu12`, `tqdm`, `regex` | **yüksek** |
| `reports.txt` | PDF/Excel/font/HTML rendering | `weasyprint`, `pydyf`, `pyphen`, `fonttools`, `tinycss2`, `tinyhtml5`, `cssselect2`, `webencodings`, `lxml`, `openpyxl`, `et_xmlfile`, `pillow`, `zopfli`, `brotli` | orta-yüksek |
| `integrations.txt` | Dış servis SDK'ları | `boto3`, `botocore`, `s3transfer`, `jmespath`, `stripe`, `resend`, `iyzipay`, `openai`, `litellm`, `google-genai`, `google-generativeai`, `google-ai-generativelanguage`, `google-api-core`, `google-api-python-client`, `google-auth`, `google-auth-httplib2`, `googleapis-common-protos`, `grpcio`, `grpcio-status`, `proto-plus`, `protobuf` | orta |
| `dev.txt` | Lokal kalite/test (production'a gitmez) | `pytest`, `pytest-asyncio`, `pytest-timeout`, `playwright`, `pyee`, `locust`, `geventhttpclient`, `ConfigArgParse`, `psutil`, `pyzmq`, `black`, `ruff`, `mypy`, `mypy_extensions`, `isort`, `flake8`, `pyflakes`, `pycodestyle`, `mccabe`, `pip-api`, `pip-requirements-parser`, `pip_audit`, `pipdeptree`, `cyclonedx-python-lib`, `license-expression`, `packageurl-python`, `py-serializable`, `boolean.py`, `typer`, `typer-slim`, `rich`, `markdown-it-py`, `mdurl`, `Pygments`, `shellingham`, `distro` | düşük |
| `all.txt` | Geçici geriye dönük uyumluluk | `-r base.txt` + `-r api.txt` + `-r worker.txt` + `-r ml.txt` + `-r reports.txt` + `-r integrations.txt` + `-r dev.txt` | düşük (legacy aggregate davranışı) |

**Not**: Aggregate'teki ~210 paketin tümü tek tek kategorize edilmedi —
yukarıdaki örnekler temsili. Aşama 2'de gerçek dosya üretiminden önce
**her paketin** bir gruba atandığı kapsamlı tablo (CSV/markdown) hazırlanacak
ve diff ile aggregate parity (set eşitliği) doğrulanacak.

## 3. Belirsiz / İncelenecek Paketler

Bu paketler birden fazla gruba düşebilir; karar gerektiriyor:

| Paket | Tartışma |
|-------|----------|
| `pillow` | Reports için kesin gerekli, ama bazı API endpoint'leri (image upload validation) da kullanıyor olabilir → muhtemelen `reports.txt`'e koy, API'a `-r reports.txt` çek |
| `brotli` | uvicorn middleware sıkıştırma + WeasyPrint ikisinde de — `base.txt` veya `api.txt` |
| `lxml` | Reports + Exely XML parsing → `reports.txt` ama API runtime'da gerekli olabilir |
| `regex` | tiktoken/textblob'a transitive — `ml.txt`'te kalır ama Pydantic email-validator de kullanıyor → muhtemelen `base.txt` |
| `aiohttp` | API runtime + bazı integrations SDK transitive → `api.txt` |
| `tornado` | Sadece flower → `worker.txt` |
| `Flask*` | Flower web UI dep → `worker.txt` |
| `litellm` | `integrations.txt`'e konacak ama Dockerfile override (`>=1.83.2 --no-deps`) ayrıca yönetilmeli (Madde 5) |
| `cross-web`, `librt`, `s5cmd`, `jq`, `sortedcontainers` | Transitive deps — set parity kontrolünde otomatik düşecek; manuel atama gerekmez |
| `resend`, `iyzipay`, `stripe`, `boto3` | `integrations.txt` — net |

## 4. Kritik Riskler

### 4.1 ML paketleri (yüksek)
`numpy`/`pandas`/`scipy`/`scikit-learn`/`xgboost`/`nvidia-nccl-cu12` image
boyutunda en pahalı kısım. API image'dan ayırmak çok değerli (~500MB+
tasarruf), ama yanlış ayrılırsa AI/RMS endpoint'leri runtime'da
`ImportError` ile patlar. **Önerilen**: ilk turda API image'a `-r ml.txt`
dahil edilir; ikinci turda gerçek import grafından AI endpoint'lerin
bağımsız bir worker queue'ya taşınabilirliği değerlendirilir.

### 4.2 PDF/rapor paketleri (orta-yüksek)
`weasyprint`/`pydyf`/`pyphen`/`fonttools`/`lxml`/`tinycss2` bazı invoice/
report endpoint'lerinde gerekiyor. API'dan tamamen çıkarmak riskli.
**Önerilen**: `reports.txt` API image'da kalır (`api.txt` `-r reports.txt`
çeker); worker için ayrıca incelenir.

### 4.3 litellm override (kritik)
`backend/Dockerfile` L13-14 şu sırayı uyguluyor:
```dockerfile
RUN pip install -r requirements.txt ... && \
    pip install --prefix=/install "litellm>=1.83.2" --no-deps
```
Yani `requirements.txt` içindeki `litellm==1.80.0` kuruluyor, sonra
`>=1.83.2` ile **deps olmadan** üzerine yazılıyor. Split sırasında bu
açıkça dokümante edilmeli; aksi halde `requirements/integrations.txt`
içinde `litellm==1.80.0` ile Dockerfile override'ı kafa karıştırır.
**Çözüm seçenekleri**:
- **A**: `integrations.txt` içinde `litellm>=1.83.2` yap, override'ı
  Dockerfile'dan kaldır (en temiz, ama transitive dep değişikliği riski).
- **B**: `integrations.txt` içinde `litellm==1.80.0` bırak + Dockerfile
  override'ı koru + `integrations.txt` üstüne yorum ekle (en güvenli,
  davranış değişmez).
- **Öneri**: ilk turda **B** (davranış parity), ikinci turda **A** ile
  override'ı kaldır.

### 4.4 Worker Dockerfile (orta)
Worker şu an aggregate'in tamamını kuruyor. Worker komutu:
```
celery -A celery_app worker -Q default,ml,analytics,messaging,pipeline,backup
```
6 farklı queue dinliyor → ML/analytics/messaging/pipeline/backup
job'larında dependency eksikliği runtime'da Celery task failure'ına
sebep olur. **Önerilen ilk hedef worker setup**:
```
-r base.txt
-r worker.txt
-r ml.txt
-r reports.txt
-r integrations.txt
```
(API ve dev hariç). Acele edilmemeli — task import grafı taranmalı.

### 4.5 CI workflow rsync exclude
`.github/workflows/ci-cd.yml` L383:
```
--exclude="requirements.txt"
```
Split sonrası bu satır `--exclude="requirements*.txt"` veya
`--exclude="requirements/"` olarak güncellenmeli. Aksi halde `requirements/`
klasörü deploy edilen image'a kopyalanır (zararsız ama gereksiz).

### 4.6 Frontend quality workflow neden backend req kuruyor?
`.github/workflows/frontend-quality.yml` L74 backend `requirements.txt`
kuruyor. Bu split kapsamı dışında; ayrı incelenecek follow-up.

## 5. Aşama Planı (özet)

| Aşama | İçerik | Dosya değişikliği | Docker/CI dokunulur mu? |
|-------|--------|-------------------|-------------------------|
| **1 (bu doküman)** | Plan + risk haritası | Sadece bu doc | Hayır |
| **2** | `backend/requirements/{base,api,worker,ml,reports,integrations,dev,all}.txt` taslakları | 8 yeni dosya | Hayır |
| **3** | Set parity + dry install + smoke import | Yok | Hayır (sadece doğrulama) |
| **4** | Backend Dockerfile → `requirements/all.txt` | `backend/Dockerfile` L12 + L13 | Evet (parity-preserving) |
| **5** | Worker Dockerfile → minimal subset | `worker/Dockerfile` L11-12 | Evet (worker küçülür) |
| **6** | Backend Dockerfile → `requirements/api.txt` (+reports) | `backend/Dockerfile` | Evet (API küçülür) |
| **7** | CI workflow'larda subset kullanımı | `.github/workflows/*.yml` | Evet |
| **8** | `requirements.txt` legacy aggregate yorumlu → silme/redirect | aggregate dosya | Evet |

**Kural**: Her aşama ayrı PR / commit. Aşamalar arası rollback kolay
olmalı. Aşama 4-8 arası herhangi bir adım build/CI kırarsa, sadece o
adım revert edilir; önceki aşamalar etkilenmez.

## 6. Aşama 3 — Doğrulama Komutları (referans)

```bash
# 1. Set parity: aggregate vs split union
diff \
  <(grep -vE '^\s*(#|$|-r )' backend/requirements.txt | sort -u) \
  <(grep -vhE '^\s*(#|$|-r )' backend/requirements/{base,api,worker,ml,reports,integrations,dev}.txt | sort -u)
# expected: empty

# 2. Duplicate kontrolü (her paket tek bir alt dosyada)
grep -hvE '^\s*(#|$|-r )' backend/requirements/{base,api,worker,ml,reports,integrations,dev}.txt \
  | awk -F'==' '{print $1}' | sort | uniq -d
# expected: empty

# 3. Dry install (sanal env zorunlu)
python -m venv /tmp/venv-split && source /tmp/venv-split/bin/activate
python -m pip install --dry-run -r backend/requirements/all.txt
python -m pip install --dry-run -r backend/requirements/api.txt
python -m pip install --dry-run -r backend/requirements/worker.txt

# 4. pip check (çelişen versiyon yok)
python -m pip install -r backend/requirements/all.txt
python -m pip check
# expected: "No broken requirements found."

# 5. API import smoke
python - <<'PY'
import fastapi, motor, pydantic, jwt, redis, celery
import sys; sys.path.insert(0, "backend")
import server
print("api ok")
PY

# 6. Worker import smoke
python - <<'PY'
import sys; sys.path.insert(0, "backend")
import celery_app
print("worker ok")
PY
```

## 7. Açık Sorular (Aşama 2 öncesi karara bağlanacak)

1. `litellm` override stratejisi — A (clean upgrade) mı B (parity preserve) mi?
2. `pillow` ve `brotli` API image'da kalıp `reports.txt` üzerinden mi gelecek, yoksa `base.txt`'e mi konulacak?
3. `requirements-ci.txt` ne olacak — silinecek mi, `-r requirements/all.txt`'e mi yönlendirilecek?
4. Aşama 2'de aggregate `requirements.txt` dokunulmayacak (yorum ekleme dahil) mı, yoksa sadece "deprecated, use `requirements/`" header'ı eklenecek mi?
5. Worker minimal subset için gerçek import grafı taraması (ör. `pipdeptree --warn silence` veya AST scan) gerekli mi?

## 8. Aşama 1 Çıktısı

Bu doküman. Aşama 2'ye geçiş için onay bekleniyor.

**Sıradaki konuşma için açık sorular**: Madde 7.

**Sıradaki kod aksiyonu (onay sonrası)**: `backend/requirements/` klasörü
+ 8 dosya taslağı, aggregate `requirements.txt` dokunulmadan.
