"""
Soak Test System Monitor — Syroce Hotel PMS
=============================================
Arka planda çalışarak sistem metriklerini toplar:
  - Backend process bellek kullanımı
  - MongoDB bellek kullanımı  
  - Yanıt süreleri (key endpoint'ler için)
  - Hata oranları

Çalıştırma:
  python load_tests/soak_monitor.py &
"""
import json
import os
import time
import subprocess
import requests
from datetime import datetime


API_URL = os.environ.get("SOAK_API_URL", "http://localhost:8001")
INTERVAL_SEC = int(os.environ.get("SOAK_MONITOR_INTERVAL", "30"))
OUTPUT_PATH = "/app/test_reports/soak_system_metrics.json"

HEALTH_ENDPOINTS = [
    "/api/pms/rooms?limit=5",
    "/api/arrivals/today",
    "/api/metrics/operational",
    "/api/audit/timeline?limit=5",
    "/api/production/maturity/score",
]


def get_process_memory():
    """Get backend Python process memory usage."""
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True
        )
        total_rss = 0
        for line in result.stdout.split("\n"):
            if "uvicorn" in line or "python" in line.lower():
                parts = line.split()
                if len(parts) > 5:
                    try:
                        rss_kb = int(parts[5])
                        total_rss += rss_kb
                    except ValueError:
                        pass
        return total_rss / 1024  # MB
    except Exception:
        return 0


def get_mongo_memory():
    """Get MongoDB process memory usage."""
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if "mongod" in line:
                parts = line.split()
                if len(parts) > 5:
                    try:
                        return int(parts[5]) / 1024  # MB
                    except ValueError:
                        pass
        return 0
    except Exception:
        return 0


def get_token():
    try:
        res = requests.post(f"{API_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        }, timeout=10)
        if res.status_code == 200:
            return res.json().get("access_token")
    except Exception:
        pass
    return None


def probe_endpoints(token):
    """Probe key endpoints and record latency + status."""
    results = []
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    for ep in HEALTH_ENDPOINTS:
        try:
            start = time.time()
            res = requests.get(f"{API_URL}{ep}", headers=headers, timeout=15)
            latency_ms = (time.time() - start) * 1000
            results.append({
                "endpoint": ep,
                "status": res.status_code,
                "latency_ms": round(latency_ms, 1),
                "ok": res.status_code == 200,
            })
        except Exception as e:
            results.append({
                "endpoint": ep,
                "status": 0,
                "latency_ms": 0,
                "ok": False,
                "error": str(e),
            })
    return results


def collect_snapshot(token):
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "backend_memory_mb": round(get_process_memory(), 1),
        "mongo_memory_mb": round(get_mongo_memory(), 1),
        "endpoint_probes": probe_endpoints(token),
    }


def analyze_metrics(snapshots):
    """Analyze collected snapshots for anomalies."""
    if len(snapshots) < 2:
        return {"status": "insufficient_data", "issues": []}

    issues = []

    # Memory leak detection: check if memory is monotonically increasing
    memories = [s["backend_memory_mb"] for s in snapshots if s["backend_memory_mb"] > 0]
    if len(memories) >= 5:
        first_quarter = sum(memories[:len(memories)//4]) / (len(memories)//4)
        last_quarter = sum(memories[-len(memories)//4:]) / (len(memories)//4)
        growth_pct = ((last_quarter - first_quarter) / max(first_quarter, 1)) * 100
        if growth_pct > 50:
            issues.append({
                "type": "memory_leak_suspected",
                "severity": "HIGH",
                "detail": f"Backend memory grew {growth_pct:.1f}% ({first_quarter:.0f}MB -> {last_quarter:.0f}MB)",
            })

    # Latency degradation: compare early vs late probes
    early_latencies = []
    late_latencies = []
    for s in snapshots[:len(snapshots)//3]:
        for p in s["endpoint_probes"]:
            if p["ok"]:
                early_latencies.append(p["latency_ms"])
    for s in snapshots[-len(snapshots)//3:]:
        for p in s["endpoint_probes"]:
            if p["ok"]:
                late_latencies.append(p["latency_ms"])

    if early_latencies and late_latencies:
        early_avg = sum(early_latencies) / len(early_latencies)
        late_avg = sum(late_latencies) / len(late_latencies)
        if late_avg > early_avg * 1.5 and late_avg > 500:
            issues.append({
                "type": "latency_degradation",
                "severity": "MEDIUM",
                "detail": f"Avg latency degraded: {early_avg:.0f}ms -> {late_avg:.0f}ms",
            })

    # Error rate check
    total_probes = 0
    failed_probes = 0
    for s in snapshots:
        for p in s["endpoint_probes"]:
            total_probes += 1
            if not p["ok"]:
                failed_probes += 1

    if total_probes > 0:
        error_rate = (failed_probes / total_probes) * 100
        if error_rate > 5:
            issues.append({
                "type": "high_error_rate",
                "severity": "HIGH",
                "detail": f"Probe error rate: {error_rate:.1f}% ({failed_probes}/{total_probes})",
            })

    verdict = "PASS" if not any(i["severity"] == "HIGH" for i in issues) else "FAIL"
    return {"status": verdict, "issues": issues}


def main():
    print(f"[SoakMonitor] Starting system monitor (interval={INTERVAL_SEC}s)")
    print(f"[SoakMonitor] API: {API_URL}")
    print(f"[SoakMonitor] Output: {OUTPUT_PATH}")

    token = get_token()
    if not token:
        print("[SoakMonitor] WARNING: Could not get auth token")

    snapshots = []
    try:
        while True:
            snapshot = collect_snapshot(token)
            snapshots.append(snapshot)

            analysis = analyze_metrics(snapshots)

            report = {
                "monitor_type": "soak_system_monitor",
                "total_snapshots": len(snapshots),
                "latest_snapshot": snapshot,
                "analysis": analysis,
                "snapshots": snapshots[-100:],  # Keep last 100
            }

            with open(OUTPUT_PATH, "w") as f:
                json.dump(report, f, indent=2, default=str)

            mem = snapshot["backend_memory_mb"]
            probe_ok = sum(1 for p in snapshot["endpoint_probes"] if p["ok"])
            probe_total = len(snapshot["endpoint_probes"])
            avg_lat = sum(p["latency_ms"] for p in snapshot["endpoint_probes"] if p["ok"]) / max(probe_ok, 1)

            print(f"[SoakMonitor] {snapshot['timestamp'][:19]} | "
                  f"Mem: {mem:.0f}MB | "
                  f"Probes: {probe_ok}/{probe_total} OK | "
                  f"Avg Latency: {avg_lat:.0f}ms | "
                  f"Issues: {len(analysis['issues'])}")

            time.sleep(INTERVAL_SEC)

    except KeyboardInterrupt:
        print("\n[SoakMonitor] Stopped. Final report saved.")
        analysis = analyze_metrics(snapshots)
        report = {
            "monitor_type": "soak_system_monitor",
            "total_snapshots": len(snapshots),
            "analysis": analysis,
            "snapshots": snapshots[-100:],
        }
        with open(OUTPUT_PATH, "w") as f:
            json.dump(report, f, indent=2, default=str)


if __name__ == "__main__":
    main()
