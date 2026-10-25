# Audit verification during concurrent requests

The verifier captures the tenant's durable sequence/hash commitment **before**
reading hot and archive rows. Both cursors are bounded to that sequence. The
captured tip is still checked against the last persisted row, preserving deleted
tail detection; a newer tip observed afterwards is disclosed, not compared to
an older cursor as though a record was deleted.

`as_of_seq` is the verification horizon, `last_seq` is the last examined row,
`observed_latest_seq` is the later state read, and `concurrent_appends` means
additional events require a subsequent scan. This is an append-only
sequence-prefix check, **not** a Mongo snapshot transaction or certification of
events arriving later. Unchained/invalid-sequence records remain fail-visible.
A changed hash without sequence advancement, state regression/deletion, and
missing/invalid genesis commitment cannot become a clean result.

The UI requests the permitted 50,000-row bound and displays the horizon. A
truncated scan is visibly incomplete, not a green whole-chain acceptance.
Existing content-hash/link errors, unchained gaps and deleted tails still fail.
No historical record is changed or resealed, and no write-side contract changes.

The underlying best-effort non-transactional writer can reserve a tip before its
row is persisted. A scan captured exactly in that interval may still report an
incomplete tip; do not treat a later successful read as permission to erase the
first observation. The financial deposit/refund writer already commits its chain
state and event together in the financial transaction. This change addresses the
observed **advanced-after-cursor** race, not every possible write/read failure.
