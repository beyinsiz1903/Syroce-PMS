const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

function getToken() {
  return localStorage.getItem('quickid_token');
}

function authHeaders() {
  const token = getToken();
  return token ? { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };
}

async function handleResponse(res) {
  if (res.status === 401) {
    // Don't redirect on login failures
    if (!res.url.includes('/api/auth/login')) {
      localStorage.removeItem('quickid_token');
      localStorage.removeItem('quickid_user');
      window.location.href = '/login';
    }
    const err = await res.json().catch(() => ({ detail: 'Oturum süresi doldu' }));
    throw new Error(typeof err.detail === 'string' ? err.detail : 'Geçersiz e-posta veya şifre');
  }
  if (res.status === 423) {
    // Account locked
    const err = await res.json().catch(() => ({ detail: { message: 'Hesap kilitlendi' } }));
    const detail = err.detail;
    const error = new Error(typeof detail === 'object' ? detail.message : detail);
    error.locked = true;
    error.remaining_minutes = detail?.remaining_minutes;
    throw error;
  }
  if (res.status === 429) {
    throw new Error('İstek limiti aşıldı. Lütfen biraz bekleyin ve tekrar deneyin.');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'İşlem başarısız' }));
    const detail = err.detail;
    if (typeof detail === 'object' && detail.message) {
      const error = new Error(detail.message);
      error.errors = detail.errors;
      error.strength = detail.strength;
      error.fallback_guidance = detail.fallback_guidance;
      error.can_retry = detail.can_retry;
      error.locked = detail.locked;
      throw error;
    }
    throw new Error(typeof detail === 'string' ? detail : 'İşlem başarısız');
  }
  return res.json();
}

export const api = {
  // Auth
  async login(email, password) {
    const res = await fetch(`${BACKEND_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    return handleResponse(res);
  },

  async getMe() {
    const res = await fetch(`${BACKEND_URL}/api/auth/me`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async changePassword(data) {
    const res = await fetch(`${BACKEND_URL}/api/auth/change-password`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  // Users (admin)
  async getUsers() {
    const res = await fetch(`${BACKEND_URL}/api/users`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async createUser(data) {
    const res = await fetch(`${BACKEND_URL}/api/users`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async updateUser(id, data) {
    const res = await fetch(`${BACKEND_URL}/api/users/${id}`, {
      method: 'PATCH', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async deleteUser(id) {
    const res = await fetch(`${BACKEND_URL}/api/users/${id}`, { method: 'DELETE', headers: authHeaders() });
    return handleResponse(res);
  },

  async resetUserPassword(id, newPassword) {
    const res = await fetch(`${BACKEND_URL}/api/users/${id}/reset-password`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify({ new_password: newPassword }),
    });
    return handleResponse(res);
  },

  async unlockUser(id) {
    const res = await fetch(`${BACKEND_URL}/api/users/${id}/unlock`, {
      method: 'POST', headers: authHeaders(),
    });
    return handleResponse(res);
  },

  async getUserLockoutStatus(id) {
    const res = await fetch(`${BACKEND_URL}/api/users/${id}/lockout-status`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async validatePassword(password) {
    const res = await fetch(`${BACKEND_URL}/api/auth/validate-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_password: password }),
    });
    return handleResponse(res);
  },

  // KVKK Settings
  async getKvkkSettings() {
    const res = await fetch(`${BACKEND_URL}/api/settings/kvkk`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async updateKvkkSettings(data) {
    const res = await fetch(`${BACKEND_URL}/api/settings/kvkk`, {
      method: 'PATCH', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async triggerCleanup() {
    const res = await fetch(`${BACKEND_URL}/api/settings/cleanup`, { method: 'POST', headers: authHeaders() });
    return handleResponse(res);
  },

  async anonymizeGuest(id) {
    const res = await fetch(`${BACKEND_URL}/api/guests/${id}/anonymize`, { method: 'POST', headers: authHeaders() });
    return handleResponse(res);
  },

  // Scan
  async scanId(imageBase64, provider = null, smartMode = true) {
    const res = await fetch(`${BACKEND_URL}/api/scan`, {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ image_base64: imageBase64, provider, smart_mode: smartMode }),
    });
    return handleResponse(res);
  },

  async getScans(page = 1, limit = 20) {
    const res = await fetch(`${BACKEND_URL}/api/scans?page=${page}&limit=${limit}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // Duplicate check
  async checkDuplicate(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) query.set(k, v); });
    const res = await fetch(`${BACKEND_URL}/api/guests/check-duplicate?${query.toString()}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // Guests
  async createGuest(data) {
    const res = await fetch(`${BACKEND_URL}/api/guests`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async getGuests(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== null && v !== undefined && v !== '') query.set(k, v); });
    const res = await fetch(`${BACKEND_URL}/api/guests?${query.toString()}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getGuest(id) {
    const res = await fetch(`${BACKEND_URL}/api/guests/${id}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async updateGuest(id, data) {
    const res = await fetch(`${BACKEND_URL}/api/guests/${id}`, {
      method: 'PATCH', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async deleteGuest(id) {
    const res = await fetch(`${BACKEND_URL}/api/guests/${id}`, { method: 'DELETE', headers: authHeaders() });
    return handleResponse(res);
  },

  async checkinGuest(id) {
    const res = await fetch(`${BACKEND_URL}/api/guests/${id}/checkin`, { method: 'POST', headers: authHeaders() });
    return handleResponse(res);
  },

  async checkoutGuest(id) {
    const res = await fetch(`${BACKEND_URL}/api/guests/${id}/checkout`, { method: 'POST', headers: authHeaders() });
    return handleResponse(res);
  },

  async groupCheckin(data) {
    const res = await fetch(`${BACKEND_URL}/api/guests/group-checkin`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  // Audit Trail
  async getGuestAudit(guestId) {
    const res = await fetch(`${BACKEND_URL}/api/guests/${guestId}/audit`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getRecentAudit(limit = 50) {
    const res = await fetch(`${BACKEND_URL}/api/audit/recent?limit=${limit}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // Dashboard
  async getDashboardStats() {
    const res = await fetch(`${BACKEND_URL}/api/dashboard/stats`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // Export
  async exportGuestsJson(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) query.set(k, v); });
    const res = await fetch(`${BACKEND_URL}/api/exports/guests.json?${query.toString()}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  getExportCsvUrl(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) query.set(k, v); });
    return `${BACKEND_URL}/api/exports/guests.csv?${query.toString()}`;
  },

  // KVKK Compliance
  async getVerbisReport() {
    const res = await fetch(`${BACKEND_URL}/api/kvkk/verbis-report`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getDataInventory() {
    const res = await fetch(`${BACKEND_URL}/api/kvkk/data-inventory`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getRetentionWarnings() {
    const res = await fetch(`${BACKEND_URL}/api/kvkk/retention-warnings`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getRightsRequests(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) query.set(k, v); });
    const res = await fetch(`${BACKEND_URL}/api/kvkk/rights-requests?${query.toString()}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async createRightsRequest(data) {
    const res = await fetch(`${BACKEND_URL}/api/kvkk/rights-request`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async processRightsRequest(requestId, data) {
    const res = await fetch(`${BACKEND_URL}/api/kvkk/rights-requests/${requestId}`, {
      method: 'PATCH', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async getGuestKvkkData(guestId) {
    const res = await fetch(`${BACKEND_URL}/api/kvkk/guest-data/${guestId}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getGuestPortableData(guestId) {
    const res = await fetch(`${BACKEND_URL}/api/kvkk/guest-data/${guestId}/portable`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // KVKK Consent Info (public)
  async getKvkkConsentInfo() {
    const res = await fetch(`${BACKEND_URL}/api/kvkk/consent-info`);
    return handleResponse(res);
  },

  // API Guide
  async getApiGuide() {
    const res = await fetch(`${BACKEND_URL}/api/guide`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // Review Queue
  async getReviewQueue(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) query.set(k, v); });
    const res = await fetch(`${BACKEND_URL}/api/scans/review-queue?${query.toString()}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async updateScanReview(scanId, reviewStatus) {
    const res = await fetch(`${BACKEND_URL}/api/scans/${scanId}/review?review_status=${reviewStatus}`, {
      method: 'PATCH', headers: authHeaders(),
    });
    return handleResponse(res);
  },

  // ===== NEW: Biometric Face Matching =====
  async compareFaces(documentImageBase64, selfieImageBase64) {
    const res = await fetch(`${BACKEND_URL}/api/biometric/face-compare`, {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ document_image_base64: documentImageBase64, selfie_image_base64: selfieImageBase64 }),
    });
    return handleResponse(res);
  },

  async getLivenessChallenge() {
    const res = await fetch(`${BACKEND_URL}/api/biometric/liveness-challenge`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async checkLiveness(imageBase64, challengeId, sessionId) {
    const res = await fetch(`${BACKEND_URL}/api/biometric/liveness-check`, {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ image_base64: imageBase64, challenge_id: challengeId, session_id: sessionId }),
    });
    return handleResponse(res);
  },

  // ===== NEW: TC Kimlik =====
  async validateTcKimlik(tcNo) {
    const res = await fetch(`${BACKEND_URL}/api/tc-kimlik/validate`, {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ tc_no: tcNo }),
    });
    return handleResponse(res);
  },

  async createEmniyetBildirimi(guestId) {
    const res = await fetch(`${BACKEND_URL}/api/tc-kimlik/emniyet-bildirimi`, {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ guest_id: guestId }),
    });
    return handleResponse(res);
  },

  async getEmniyetBildirimleri(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) query.set(k, v); });
    const res = await fetch(`${BACKEND_URL}/api/tc-kimlik/emniyet-bildirimleri?${query.toString()}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // ===== NEW: Pre-Checkin =====
  async createPreCheckin(data) {
    const res = await fetch(`${BACKEND_URL}/api/precheckin/create`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async getPreCheckinInfo(tokenId) {
    const res = await fetch(`${BACKEND_URL}/api/precheckin/${tokenId}`);
    return handleResponse(res);
  },

  async preCheckinScan(tokenId, imageBase64, kvkkConsent = false) {
    const res = await fetch(`${BACKEND_URL}/api/precheckin/${tokenId}/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_base64: imageBase64, kvkk_consent: kvkkConsent }),
    });
    return handleResponse(res);
  },

  getPreCheckinQrUrl(tokenId) {
    return `${BACKEND_URL}/api/precheckin/${tokenId}/qr`;
  },

  async listPreCheckins(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) query.set(k, v); });
    const res = await fetch(`${BACKEND_URL}/api/precheckin/list?${query.toString()}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // ===== NEW: Multi-Property =====
  async getProperties(isActive = null) {
    const query = isActive !== null ? `?is_active=${isActive}` : '';
    const res = await fetch(`${BACKEND_URL}/api/properties${query}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async createProperty(data) {
    const res = await fetch(`${BACKEND_URL}/api/properties`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async getProperty(propertyId) {
    const res = await fetch(`${BACKEND_URL}/api/properties/${propertyId}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async updateProperty(propertyId, data) {
    const res = await fetch(`${BACKEND_URL}/api/properties/${propertyId}`, {
      method: 'PATCH', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  // ===== NEW: Kiosk =====
  async createKioskSession(data) {
    const res = await fetch(`${BACKEND_URL}/api/kiosk/session`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async getKioskSessions(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) query.set(k, v); });
    const res = await fetch(`${BACKEND_URL}/api/kiosk/sessions?${query.toString()}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // ===== NEW: Offline Sync =====
  async uploadOfflineData(data) {
    const res = await fetch(`${BACKEND_URL}/api/sync/upload`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async getPendingSyncs(propertyId = null) {
    const query = propertyId ? `?property_id=${propertyId}` : '';
    const res = await fetch(`${BACKEND_URL}/api/sync/pending${query}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async processSync(syncId) {
    const res = await fetch(`${BACKEND_URL}/api/sync/${syncId}/process`, {
      method: 'POST', headers: authHeaders(),
    });
    return handleResponse(res);
  },

  // ===== OCR Providers =====
  async getScanProviders() {
    const res = await fetch(`${BACKEND_URL}/api/scan/providers`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getOcrStatus() {
    const res = await fetch(`${BACKEND_URL}/api/scan/ocr-status`);
    return handleResponse(res);
  },

  async scanWithOcr(imageBase64) {
    const res = await fetch(`${BACKEND_URL}/api/scan/ocr-fallback`, {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ image_base64: imageBase64 }),
    });
    return handleResponse(res);
  },

  async checkImageQuality(imageBase64) {
    const res = await fetch(`${BACKEND_URL}/api/scan/quality-check`, {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ image_base64: imageBase64 }),
    });
    return handleResponse(res);
  },

  async getCostEstimate(providerId) {
    const res = await fetch(`${BACKEND_URL}/api/scan/cost-estimate/${providerId}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // ===== Room Management =====
  async getRooms(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== null && v !== undefined && v !== '') query.set(k, v); });
    const res = await fetch(`${BACKEND_URL}/api/rooms?${query.toString()}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getRoomStats(propertyId = null) {
    const query = propertyId ? `?property_id=${propertyId}` : '';
    const res = await fetch(`${BACKEND_URL}/api/rooms/stats${query}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getRoomTypes() {
    const res = await fetch(`${BACKEND_URL}/api/rooms/types`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async createRoom(data) {
    const res = await fetch(`${BACKEND_URL}/api/rooms`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async updateRoom(roomId, data) {
    const res = await fetch(`${BACKEND_URL}/api/rooms/${roomId}`, {
      method: 'PATCH', headers: authHeaders(), body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  async assignRoom(roomId, guestId) {
    const res = await fetch(`${BACKEND_URL}/api/rooms/assign`, {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ room_id: roomId, guest_id: guestId }),
    });
    return handleResponse(res);
  },

  async autoAssignRoom(guestId, propertyId = null, preferredType = null) {
    const body = { guest_id: guestId };
    if (propertyId) body.property_id = propertyId;
    if (preferredType) body.preferred_type = preferredType;
    const res = await fetch(`${BACKEND_URL}/api/rooms/auto-assign`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(body),
    });
    return handleResponse(res);
  },

  async releaseRoom(roomId, guestId = null) {
    const query = guestId ? `?guest_id=${guestId}` : '';
    const res = await fetch(`${BACKEND_URL}/api/rooms/${roomId}/release${query}`, {
      method: 'POST', headers: authHeaders(),
    });
    return handleResponse(res);
  },

  // ===== Monitoring =====
  async getMonitoringDashboard() {
    const res = await fetch(`${BACKEND_URL}/api/monitoring/dashboard`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getScanStatistics(days = 30) {
    const res = await fetch(`${BACKEND_URL}/api/monitoring/scan-stats?days=${days}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getErrorLog(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== null && v !== undefined) query.set(k, v); });
    const res = await fetch(`${BACKEND_URL}/api/monitoring/error-log?${query.toString()}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getAiCostReport(days = 30) {
    const res = await fetch(`${BACKEND_URL}/api/monitoring/ai-costs?days=${days}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // ===== Backup =====
  async createBackup(description = '') {
    const res = await fetch(`${BACKEND_URL}/api/admin/backup`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify({ description }),
    });
    return handleResponse(res);
  },

  async getBackups() {
    const res = await fetch(`${BACKEND_URL}/api/admin/backups`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async restoreBackup(backupId) {
    const res = await fetch(`${BACKEND_URL}/api/admin/restore`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify({ backup_id: backupId }),
    });
    return handleResponse(res);
  },

  async getBackupSchedule() {
    const res = await fetch(`${BACKEND_URL}/api/admin/backup-schedule`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // ===== Compliance =====
  async getComplianceReports() {
    const res = await fetch(`${BACKEND_URL}/api/compliance/reports`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // ===== Guest Photo =====
  async uploadGuestPhoto(guestId, imageBase64) {
    const res = await fetch(`${BACKEND_URL}/api/guests/${guestId}/photo`, {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ image_base64: imageBase64 }),
    });
    return handleResponse(res);
  },

  async getGuestPhoto(guestId) {
    const res = await fetch(`${BACKEND_URL}/api/guests/${guestId}/photo`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // ===== Form-C =====
  async getFormC(guestId) {
    const res = await fetch(`${BACKEND_URL}/api/tc-kimlik/form-c/${guestId}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  // ===== Guest Restore =====
  async restoreGuest(guestId) {
    const res = await fetch(`${BACKEND_URL}/api/guests/${guestId}/restore`, {
      method: 'POST', headers: authHeaders(),
    });
    return handleResponse(res);
  },

  // ===== PDF Reports =====
  getFormCPdfUrl(guestId) {
    return `${BACKEND_URL}/api/reports/form-c/${guestId}/pdf`;
  },

  getGuestListPdfUrl(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) query.set(k, v); });
    return `${BACKEND_URL}/api/reports/guests/pdf?${query.toString()}`;
  },

  async downloadPdf(url) {
    const token = getToken();
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('PDF indirilemedi');
    const blob = await res.blob();
    return blob;
  },

  // ===== Email Status =====
  async getEmailStatus() {
    const res = await fetch(`${BACKEND_URL}/api/admin/email-status`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async getEmailLog(limit = 50) {
    const res = await fetch(`${BACKEND_URL}/api/admin/email-log?limit=${limit}`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async sendTestEmail() {
    const res = await fetch(`${BACKEND_URL}/api/admin/email-test`, {
      method: 'POST', headers: authHeaders(),
    });
    return handleResponse(res);
  },
};
