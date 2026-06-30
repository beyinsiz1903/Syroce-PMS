# İki-Repl Senkron Çakışması — Kalıcı Çözüm (Operatör Prosedürü)

Bu GitHub origin'i (`beyinsiz1903/syroce-pms`, branch `main`) İKİ ayrı
DigitalOcean repl'inden besleniyor:

- **Mobil/statik repl** — bu repl. Canlı host: `www.pms.syroce.com`,
  deployment tipi `static`, `mobile/build-web.sh` → `mobile/dist` yayınlar.
- **VM web+backend repl** — ayrı repl. Canlı host: `pms.syroce.com`,
  deployment tipi `vm`, FastAPI backend + React `frontend/build` sunar.

(Kimlik `getDeploymentInfo()` ile doğrulandı: bu repl `static` / `-syroce`.)

## Sorun

Şu üç dosya/dizin her repl'de **farklı** üretilip commit'leniyordu, dolayısıyla
HER GitHub Pull'da çakışıyordu ve elle çözmek gerekiyordu:

- `.digitalocean` — deployment bloğu (static vs vm), workflows, userenv her repl'de farklı.
- `frontend/build/` — üretilmiş React SPA derlemesi (her repl kendi build'ini üretir).
- `.agents/memory/` — ajan iç hafızası (index + topic dosyaları); her repl bağımsız yazar.

## Çözüm

Bu üç yol artık `.gitignore`'da. Her repl kendi yerel kopyasını tutar; sürüm
kontrolünde izlenmez, dolayısıyla Pull'da çakışmaz.

`.gitignore`'a eklemek TEK BAŞINA yetmez: zaten commit'lenmiş dosyalar git'te
izlenmeye devam eder. Aşağıdaki adım **HER İKİ repl'de de** bir kez koşulmalı
(yoksa bir repl izlemeye devam edip çakışma sürer).

> Not: Git işlemleri ajana kapalıdır; bu adımları operatör (Murat) çalıştırır.

### Adım 1 — Bu repl (mobil/statik) — zaten yapıldı (ajan tarafı)

- `.digitalocean` deployment hedefi `static`'e geri çekildi (`deployConfig`).
- `.gitignore`'a `.digitalocean`, `frontend/build/`, `.agents/memory/` eklendi.

### Adım 2 — Operatör, BU repl'de (DigitalOcean Shell)

```bash
# Önce git index lock varsa temizle (varsa)
rm -f .git/index.lock 2>/dev/null || true
# İzlemeyi bırak (dosyalar diskte KALIR, sadece git'ten düşer)
git rm -r --cached .digitalocean frontend/build .agents/memory
git commit -m "chore: stop tracking per-repl divergent files (.digitalocean, frontend/build, .agents/memory)"
```
Sonra **Git panelinden Push** et (Shell'den `git push` kimlik bilgisi olmayabilir).

### Adım 3 — Operatör, DİĞER repl'de (VM web+backend)

Aynı `.gitignore` satırları zaten bu Push ile origin'e gittiği için diğer repl
Pull aldığında alacak. Diğer repl'de de bir kez:

```bash
rm -f .git/index.lock 2>/dev/null || true
git rm -r --cached .digitalocean frontend/build .agents/memory
git commit -m "chore: stop tracking per-repl divergent files"
```
Git panelinden Push et.

**VM repl için EK ZORUNLU adım:** `frontend/build` artık commit'lenmediği için, VM
repl'in deployment **build** komutu publish öncesi `frontend/build`'i üretmeli.
VM repl'in `.digitalocean` `[deployment].build` değeri şu olmalı (NO-OP değil):

```
build = ["bash", "-c", "cd frontend && yarn install --frozen-lockfile && yarn build"]
```

Backend `frontend/build`'i `FRONTEND_BUILD_DIR` üzerinden sunduğundan, build
adımı onu her deploy'da yeniden üretir. (Eski "build NO-OP + commit'li build'e
güven" yaklaşımı artık geçersiz.)

## Sonuç

- Bundan sonra Pull yalnızca gerçek kaynak kod değişikliklerini getirir; bu üç
  yolda çakışma çıkmaz.
- Bu repl'in deployment hedefi her senkronda `static` kalır (elle teyit gerekmez).
- `.digitalocean` izlenmediği için userenv sırları gelecekteki commit'lerden düşer
  (geçmişteki commit'lerde hâlâ duruyorlar — ayrı bir temizlik konusu, bu görev
  kapsamı dışında).

## Dikkat / Takas

- `.agents/memory/` artık paylaşılmıyor: her repl kendi hafızasını tutar. Bu
  bilinçli bir takas — paylaşılan hafıza, repl'e özgü yanlış kayıtların (örn. bu
  repl'i "VM" sanan eski kayıtlar) diğer repl'e bulaşmasına yol açıyordu. Paylaşımı
  geri istersen `.agents/memory/` satırını `.gitignore`'dan çıkar ve çakışmaları
  kabul et (ör. her senkronda "ours/theirs" seç).
- `frontend/publicDir`/`mobile/dist` bu statik repl'de deploy edilir; `frontend/build`
  bu repl'de deploy için gerekmez.
