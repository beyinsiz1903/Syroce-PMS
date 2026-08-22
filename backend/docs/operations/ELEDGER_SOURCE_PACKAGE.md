# e-Defter Source Package Boundary

Syroce's `/api/gl/e-ledger/source-package` endpoint produces an accountant-transfer
source archive. It is **not** a GIB e-Defter, journal ledger berat, or general
ledger berat.

The archive contains:

- `journal.csv`: posted journal lines for one closed fiscal month;
- `general_ledger.csv`: account-level debit/credit totals;
- `manifest.json`: SHA-256 digests and the preflight result;
- `README.txt`: the legal boundary displayed inside the archive.

The endpoint performs no provider call, GIB submission, financial-seal action,
or electronic-signature action. It fails closed when the fiscal period is open,
the journal is empty/unbalanced, an account is missing, an entry number is
duplicated, or an unexplained sequence gap exists.

## External compliance boundary

GIB states that official journal and general-ledger files are prepared in
XBRL-GL format, validated against the published schema and schematron, signed
or sealed, paired with signed/sealed berats, submitted, and retained with the
GIB-approved berats. GIB also requires the generating software and each new
version to complete software compatibility approval.

Current primary references:

- <https://www.edefter.gov.tr/edeftermevzuat.html>
- <https://www.edefter.gov.tr/dosyalar/kilavuzlar/e-Defter_Yazilim_Uyumluluk_Onay_Kilavuzu_V.1.7.pdf>

Until Syroce completes that external approval and certificate integration,
product copy and API headers must continue to label this output as a source
package with `official_edefter=false`.
