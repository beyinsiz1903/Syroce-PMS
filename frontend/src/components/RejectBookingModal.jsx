// frontend/src/components/RejectBookingModal.jsx
import React, { useMemo, useState, useEffect } from "react";

const REASONS = [
  { code: "NO_AVAILABILITY", label: "No availability" },
  { code: "PRICE_MISMATCH", label: "Price mismatch" },
  { code: "OVERBOOK", label: "Overbook" },
  { code: "POLICY", label: "Policy" },
  { code: "OTHER", label: "Other" },
];

export default function RejectBookingModal({ open, booking, onClose, onSubmit, busy }) {
  const defaultCode = useMemo(() => REASONS[0].code, []);
  const [reasonCode, setReasonCode] = useState(defaultCode);
  const [reasonNote, setReasonNote] = useState("");

  useEffect(() => {
    if (open) {
      setReasonCode(defaultCode);
      setReasonNote("");
    }
  }, [open, defaultCode]);

  if (!open) return null;

  const bookingId = booking?.id || booking?.booking_id || "";

  const handleSubmit = async () => {
    await onSubmit?.({ reason_code: reasonCode, reason_note: reasonNote || null });
  };

  return (
    <div style={styles.backdrop} onClick={busy ? undefined : onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <div style={{ fontWeight: 700 }}>Reject booking</div>
          <button onClick={onClose} disabled={busy} style={styles.xBtn}>
            
          </button>
        </div>

        <div style={styles.body}>
          <div style={styles.meta}>
            <div style={{ opacity: 0.75, fontSize: 12 }}>Booking</div>
            <div style={{ fontFamily: "monospace" }}>{bookingId}</div>
          </div>

          <label style={styles.label}>Reason</label>
          <select
            value={reasonCode}
            onChange={(e) => setReasonCode(e.target.value)}
            disabled={busy}
            style={styles.select}
          >
            {REASONS.map((r) => (
              <option key={r.code} value={r.code}>
                {r.label}
              </option>
            ))}
          </select>

          <label style={styles.label}>Note (optional)</label>
          <textarea
            value={reasonNote}
            onChange={(e) => setReasonNote(e.target.value)}
            disabled={busy}
            maxLength={500}
            rows={4}
            style={styles.textarea}
            placeholder="Add a short note (max 500 chars)"
          />
        </div>

        <div style={styles.footer}>
          <button onClick={onClose} disabled={busy} style={styles.secondaryBtn}>
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={busy} style={styles.dangerBtn}>
            {busy ? "Rejecting..." : "Reject"}
          </button>
        </div>
      </div>
    </div>
  );
}

const styles = {
  backdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.35)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 16,
    zIndex: 9999,
  },
  modal: {
    width: "min(560px, 100%)",
    background: "#fff",
    borderRadius: 12,
    overflow: "hidden",
    boxShadow: "0 12px 40px rgba(0,0,0,0.25)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 14px",
    borderBottom: "1px solid rgba(0,0,0,0.08)",
  },
  xBtn: {
    border: "none",
    background: "transparent",
    fontSize: 16,
    cursor: "pointer",
  },
  body: { padding: 14 },
  meta: {
    marginBottom: 12,
    padding: 10,
    borderRadius: 10,
    background: "rgba(0,0,0,0.04)",
  },
  label: { display: "block", fontSize: 12, opacity: 0.8, marginTop: 10, marginBottom: 6 },
  select: { width: "100%", padding: 10, borderRadius: 10, border: "1px solid rgba(0,0,0,0.15)" },
  textarea: {
    width: "100%",
    padding: 10,
    borderRadius: 10,
    border: "1px solid rgba(0,0,0,0.15)",
    resize: "vertical",
  },
  footer: {
    display: "flex",
    justifyContent: "flex-end",
    gap: 10,
    padding: 14,
    borderTop: "1px solid rgba(0,0,0,0.08)",
  },
  secondaryBtn: {
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid rgba(0,0,0,0.15)",
    background: "#fff",
    cursor: "pointer",
  },
  dangerBtn: {
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid rgba(0,0,0,0.15)",
    background: "#ffe5e5",
    cursor: "pointer",
    fontWeight: 600,
  },
};
