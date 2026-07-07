import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Softphone from "../Softphone";
import axios from "axios";

vi.mock("axios");

function makeMockJwt(expSecondsFromNow) {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(JSON.stringify({
    exp: Math.floor(Date.now() / 1000) + expSecondsFromNow
  }));
  return `${header}.${payload}.signature`;
}

describe("Softphone frontend user gesture flow", () => {
  let mockGetUserMedia;
  let mockDevice;
  let mockConnect;
  let mockRegister;
  let registeredCallback;

  beforeEach(() => {
    vi.restoreAllMocks();
    
    // Mock getUserMedia
    mockGetUserMedia = vi.fn().mockResolvedValue({
      getTracks: () => [{ stop: vi.fn() }]
    });
    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      value: {
        getUserMedia: mockGetUserMedia
      }
    });

    // Mock AudioContext using standard function to support "new" constructor calls
    const mockAudioContext = {
      state: "suspended",
      resume: vi.fn().mockResolvedValue(undefined)
    };
    window.AudioContext = vi.fn().mockImplementation(function() {
      return mockAudioContext;
    });
    window.webkitAudioContext = vi.fn().mockImplementation(function() {
      return mockAudioContext;
    });

    // Mock axios with fresh token
    axios.post.mockResolvedValue({ data: { token: makeMockJwt(3600) } });
    axios.get.mockResolvedValue({ data: { matched: false } });

    // Mock Twilio.Device
    mockConnect = vi.fn().mockResolvedValue({
      on: vi.fn(),
      disconnect: vi.fn()
    });
    mockRegister = vi.fn().mockImplementation(() => {
      if (registeredCallback) {
        registeredCallback();
      }
      return Promise.resolve();
    });
    
    // Use standard function definition so that it works as a constructor with "new"
    mockDevice = vi.fn().mockImplementation(function(token, options) {
      this.on = vi.fn((event, cb) => {
        if (event === "registered") {
          registeredCallback = cb;
        }
      });
      this.register = mockRegister;
      this.connect = mockConnect;
      this.destroy = vi.fn();
    });

    window.Twilio = {
      Device: mockDevice
    };
  });

  afterEach(() => {
    delete window.Twilio;
    delete window.AudioContext;
    delete window.webkitAudioContext;
  });

  it("does not request microphone or initialize device on page load", () => {
    render(<Softphone user={{ role: "admin" }} />);
    
    // Softphone button is shown
    const button = screen.getByRole("button", { name: "Softphone" });
    expect(button).toBeInTheDocument();

    // But no getUserMedia has been called
    expect(mockGetUserMedia).not.toHaveBeenCalled();
    expect(mockDevice).not.toHaveBeenCalled();
  });

  it("requests microphone permission and resumes AudioContext only after online-button click", async () => {
    render(<Softphone user={{ role: "admin" }} />);
    
    // Open the drawer
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));

    // Click "Müsait (Çevrimiçi Ol)" - wait for background token to fetch
    const onlineBtn = await screen.findByRole("button", { name: /Müsait/ });
    fireEvent.click(onlineBtn);

    await waitFor(() => {
      expect(mockGetUserMedia).toHaveBeenCalledWith({ audio: true });
      expect(mockDevice).toHaveBeenCalled();
      expect(mockRegister).toHaveBeenCalled();
    });
  });

  it("calls Device.connect only after explicit call-button click", async () => {
    render(<Softphone user={{ role: "admin" }} />);
    
    // Open softphone and click online
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    const onlineBtn = await screen.findByRole("button", { name: /Müsait/ });
    fireEvent.click(onlineBtn);

    // Wait until it is registered and shows dialing input
    await screen.findByText("Telefon");
    const dialInput = screen.getByPlaceholderText("+90 5XX XXX XX XX");
    const callBtn = screen.getByRole("button", { name: "Ara" });

    // Enter number
    fireEvent.change(dialInput, { target: { value: "+905555555555" } });

    // Connect must not have been called yet
    expect(mockConnect).not.toHaveBeenCalled();

    // Click call button
    fireEvent.click(callBtn);

    // Connect should be called directly
    expect(mockConnect).toHaveBeenCalledWith({ params: { To: "+905555555555" } });
  });

  it("displays a clear Turkish error if microphone permission is rejected", async () => {
    mockGetUserMedia.mockRejectedValue({ name: "NotAllowedError" });
    
    render(<Softphone user={{ role: "admin" }} />);
    
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    const onlineBtn = await screen.findByRole("button", { name: /Müsait/ });
    fireEvent.click(onlineBtn);

    const errorMsg = await screen.findByText(/Mikrofon izni reddedildi/);
    expect(errorMsg).toBeInTheDocument();
  });

  it("disables button and triggers background refresh if token is expired", async () => {
    const expiredToken = makeMockJwt(-3600); // 1 hour ago
    const freshToken = makeMockJwt(3600); // 1 hour validity
    axios.post.mockReset();
    axios.post.mockResolvedValueOnce({ data: { token: expiredToken } });
    axios.post.mockResolvedValueOnce({ data: { token: freshToken } });

    render(<Softphone user={{ role: "admin" }} />);
    
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));

    // Button should show "Telefon hazırlanıyor..." and be disabled
    const prepareBtn = screen.getByRole("button", { name: /hazırlanıyor/ });
    expect(prepareBtn).toBeDisabled();

    // Verify it started a background refresh
    expect(axios.post).toHaveBeenCalled();

    // Wait until it gets the fresh token and the button becomes enabled
    await waitFor(() => {
      expect(screen.queryByText(/hazırlanıyor/)).not.toBeInTheDocument();
    });
    
    const onlineBtn = screen.getByRole("button", { name: /Müsait/ });
    expect(onlineBtn).not.toBeDisabled();

    // Click should now register device synchronously
    fireEvent.click(onlineBtn);
    expect(mockDevice).toHaveBeenCalled();
    expect(mockRegister).toHaveBeenCalled();
  });

  it("refreshes a near-expiry token when page visibility changes to visible", async () => {
    const nearExpiryToken = makeMockJwt(60); // expires in 60 seconds
    const freshToken = makeMockJwt(3600);
    axios.post.mockReset();
    axios.post.mockResolvedValueOnce({ data: { token: nearExpiryToken } });
    axios.post.mockResolvedValueOnce({ data: { token: freshToken } });

    render(<Softphone user={{ role: "admin" }} />);
    
    // Open the drawer so that token tracking/visibility change listener is registered
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    
    // Clear mock calls to verify visibility change refresh
    axios.post.mockClear();

    // Trigger visibilitychange event
    Object.defineProperty(document, "visibilityState", {
      writable: true,
      value: "visible"
    });
    fireEvent(document, new Event("visibilitychange"));

    // Verify refresh was triggered
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalled();
    });
  });

  it("enforces that activate handler is synchronous and does not trigger SDK loader on click", async () => {
    render(<Softphone user={{ role: "admin" }} />);
    
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    const onlineBtn = await screen.findByRole("button", { name: /Müsait/ });

    // Reset mocks
    mockDevice.mockClear();
    mockRegister.mockClear();

    // Trigger click on Müsait
    fireEvent.click(onlineBtn);

    // Verify Twilio.Device instantiation and register are called synchronously (no yielding)
    expect(mockDevice).toHaveBeenCalled();
    expect(mockRegister).toHaveBeenCalled();
  });
  it("handles Device.connect returning Promise<Call> and registers listeners only on resolved Call", async () => {
    const mockOn = vi.fn();
    const mockDisconnect = vi.fn();
    const mockCall = {
      on: mockOn,
      disconnect: mockDisconnect
    };
    mockConnect.mockResolvedValue(mockCall);

    render(<Softphone user={{ role: "admin" }} />);
    
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    const onlineBtn = await screen.findByRole("button", { name: /Müsait/ });
    fireEvent.click(onlineBtn);

    await screen.findByText("Telefon");
    const dialInput = screen.getByPlaceholderText("+90 5XX XXX XX XX");
    fireEvent.change(dialInput, { target: { value: "+905555555555" } });
    const callBtn = screen.getByRole("button", { name: "Ara" });
    fireEvent.click(callBtn);

    await waitFor(() => {
      expect(mockOn).toHaveBeenCalledWith("disconnect", expect.any(Function));
    });
  });

  it("displays Turkish error on connect rejection", async () => {
    mockConnect.mockRejectedValue(new Error("Bağlantı koptu"));

    render(<Softphone user={{ role: "admin" }} />);
    
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    const onlineBtn = await screen.findByRole("button", { name: /Müsait/ });
    fireEvent.click(onlineBtn);

    await screen.findByText("Telefon");
    const dialInput = screen.getByPlaceholderText("+90 5XX XXX XX XX");
    fireEvent.change(dialInput, { target: { value: "+905555555555" } });
    const callBtn = screen.getByRole("button", { name: "Ara" });
    fireEvent.click(callBtn);

    const errorMsg = await screen.findByText(/Giden çağrı başlatılamadı: Bağlantı koptu/);
    expect(errorMsg).toBeInTheDocument();
  });

  it("clears call ref on disconnect", async () => {
    let disconnectCb;
    const mockCall = {
      on: vi.fn((event, cb) => {
        if (event === "disconnect") {
          disconnectCb = cb;
        }
      }),
      disconnect: vi.fn()
    };
    mockConnect.mockResolvedValue(mockCall);

    render(<Softphone user={{ role: "admin" }} />);
    
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    const onlineBtn = await screen.findByRole("button", { name: /Müsait/ });
    fireEvent.click(onlineBtn);

    await screen.findByText("Telefon");
    const dialInput = screen.getByPlaceholderText("+90 5XX XXX XX XX");
    fireEvent.change(dialInput, { target: { value: "+905555555555" } });
    const callBtn = screen.getByRole("button", { name: "Ara" });
    fireEvent.click(callBtn);

    await waitFor(() => {
      expect(disconnectCb).toBeDefined();
    });

    disconnectCb();

    await screen.findByText("Telefon");
  });

  it("does not start repeated calls if clicked during connecting status", async () => {
    let resolvePromise;
    const delayPromise = new Promise((resolve) => {
      resolvePromise = resolve;
    });
    mockConnect.mockReturnValue(delayPromise);

    render(<Softphone user={{ role: "admin" }} />);
    
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    const onlineBtn = await screen.findByRole("button", { name: /Müsait/ });
    fireEvent.click(onlineBtn);

    await screen.findByText("Telefon");
    const dialInput = screen.getByPlaceholderText("+90 5XX XXX XX XX");
    fireEvent.change(dialInput, { target: { value: "+905555555555" } });
    const callBtn = screen.getByRole("button", { name: "Ara" });
    
    fireEvent.click(callBtn);
    expect(mockConnect).toHaveBeenCalledTimes(1);

    fireEvent.click(callBtn);
    expect(mockConnect).toHaveBeenCalledTimes(1);
  });

  it("disconnects the resolved call immediately if user clicked İptal Et before resolution", async () => {
    let resolveCall;
    const mockCall = {
      disconnect: vi.fn(),
      on: vi.fn()
    };
    const pendingPromise = new Promise((resolve) => {
      resolveCall = resolve;
    });
    mockConnect.mockReturnValue(pendingPromise);

    render(<Softphone user={{ role: "admin" }} />);
    
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    const onlineBtn = await screen.findByRole("button", { name: /Müsait/ });
    fireEvent.click(onlineBtn);

    await screen.findByText("Telefon");
    const dialInput = screen.getByPlaceholderText("+90 5XX XXX XX XX");
    fireEvent.change(dialInput, { target: { value: "+905555555555" } });
    const callBtn = screen.getByRole("button", { name: "Ara" });
    fireEvent.click(callBtn);

    // User clicks "İptal Et" immediately while connecting
    const cancelBtn = screen.getByRole("button", { name: "İptal Et" });
    fireEvent.click(cancelBtn);

    // Confirm UI returns to ready (shows "Ara" button again)
    await screen.findByRole("button", { name: "Ara" });

    // Now resolve the promise with mockCall
    resolveCall(mockCall);

    // Confirm call.disconnect() is invoked immediately on resolution
    await waitFor(() => {
      expect(mockCall.disconnect).toHaveBeenCalled();
    });
  });

  it("sends a WhatsApp message with the correct endpoint URL and payload", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    axios.post.mockImplementation((url) => {
      if (url.includes("token")) {
        return Promise.resolve({ data: { token: makeMockJwt(3600) } });
      }
      return Promise.resolve({ data: { success: true } });
    });

    let acceptCallback;
    const mockCall = {
      parameters: {
        CallSid: "CA12345",
        From: "+905555555555"
      },
      on: vi.fn((event, cb) => {
        if (event === "accept") {
          acceptCallback = cb;
        }
      }),
      disconnect: vi.fn()
    };
    mockConnect.mockResolvedValue(mockCall);

    render(<Softphone user={{ role: "admin" }} />);
    
    // Connect the call
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    const onlineBtn = await screen.findByRole("button", { name: /Müsait/ });
    fireEvent.click(onlineBtn);

    await screen.findByText("Telefon");
    const dialInput = screen.getByPlaceholderText("+90 5XX XXX XX XX");
    fireEvent.change(dialInput, { target: { value: "+905555555555" } });
    const callBtn = screen.getByRole("button", { name: "Ara" });
    fireEvent.click(callBtn);

    // Call has been initiated. Wait for connect promise to resolve and register listeners.
    await waitFor(() => {
      expect(acceptCallback).toBeDefined();
    });
    // Accept the call
    acceptCallback();

    // Now call should be connected
    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "hello_world" } });

    expect(axios.post).toHaveBeenLastCalledWith(
      "/contact-center/voice/live/CA12345/whatsapp",
      {
        phone: "+905555555555",
        template_name: "hello_world",
        language_code: "tr"
      }
    );

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith("WhatsApp mesajı başarıyla gönderildi.");
    });
  });

  it("displays proper error message on WhatsApp send failures", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    
    let whatsappRejectValue;
    axios.post.mockImplementation((url) => {
      if (url.includes("token")) {
        return Promise.resolve({ data: { token: makeMockJwt(3600) } });
      }
      return Promise.reject(whatsappRejectValue);
    });

    let acceptCallback;
    const mockCall = {
      parameters: {
        CallSid: "CA12345",
        From: "+905555555555"
      },
      on: vi.fn((event, cb) => {
        if (event === "accept") {
          acceptCallback = cb;
        }
      }),
      disconnect: vi.fn()
    };
    mockConnect.mockResolvedValue(mockCall);

    render(<Softphone user={{ role: "admin" }} />);
    
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    const onlineBtn = await screen.findByRole("button", { name: /Müsait/ });
    fireEvent.click(onlineBtn);

    await screen.findByText("Telefon");
    const dialInput = screen.getByPlaceholderText("+90 5XX XXX XX XX");
    fireEvent.change(dialInput, { target: { value: "+905555555555" } });
    const callBtn = screen.getByRole("button", { name: "Ara" });
    fireEvent.click(callBtn);

    await waitFor(() => {
      expect(acceptCallback).toBeDefined();
    });
    acceptCallback();

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    const select = screen.getByRole("combobox");

    // Case 1a: 404 generic
    whatsappRejectValue = { response: { status: 404 } };
    fireEvent.change(select, { target: { value: "hello_world" } });
    await waitFor(() => {
      expect(alertSpy).toHaveBeenLastCalledWith("WhatsApp gönderim adresi bulunamadı.");
    });

    // Case 1b: 404 call not found detail
    whatsappRejectValue = { response: { status: 404, data: { detail: "Çağrı bulunamadı." } } };
    fireEvent.change(select, { target: { value: "hello_world" } });
    await waitFor(() => {
      expect(alertSpy).toHaveBeenLastCalledWith("Aktif çağrı kaydı bulunamadı.");
    });

    // Case 2: 503
    whatsappRejectValue = { response: { status: 503 } };
    fireEvent.change(select, { target: { value: "hello_world" } });
    await waitFor(() => {
      expect(alertSpy).toHaveBeenLastCalledWith("WhatsApp servisi yapılandırılmamış.");
    });

    // Case 3: 502
    whatsappRejectValue = { response: { status: 502 } };
    fireEvent.change(select, { target: { value: "hello_world" } });
    await waitFor(() => {
      expect(alertSpy).toHaveBeenLastCalledWith("WhatsApp sağlayıcısı mesajı gönderemedi.");
    });

    // Case 4: custom backend detail
    whatsappRejectValue = { response: { status: 400, data: { detail: "Sınır aşıldı." } } };
    fireEvent.change(select, { target: { value: "hello_world" } });
    await waitFor(() => {
      expect(alertSpy).toHaveBeenLastCalledWith("Sınır aşıldı.");
    });
  });
});
