# Kill-switch registry

This registry records the operational switches that protect Exely provider
traffic.  Values are evaluated at runtime; every change must be auditable and
reversed once an incident has ended.

| Flag | Default | Effect |
| --- | --- | --- |
| `ENABLE_EXELY_PRODUCTION` | off | Production Exely reads and writes remain blocked until this flag is explicitly enabled. |
| `DISABLE_EXELY_RESERVATION_SYNC` | off | Immediately stops Exely reservation reads and acknowledgement delivery. |
| `DISABLE_EXELY_ARI_WRITE` | off | Immediately stops Exely availability, rate, and restriction writes. |

Do not use a kill switch to hide a validation, network, or authentication
failure. Record the incident, correct the configuration or dependency, verify
the safe runtime state, then restore the switch to its documented default.
