import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Softphone from "../Softphone";
import axios from "axios";

vi.mock("axios");

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

    // Mock axios
    axios.post.mockResolvedValue({ data: { token: "mock-token-123" } });

    // Mock Twilio.Device
    mockConnect = vi.fn().mockResolvedValue({
      on: vi.fn(),
      disconnect: vi.fn()
    });
    mockRegister = vi.fn().mockImplementation(() => {
      if (registeredCallback) {
        registeredCallback();
      }
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

    // Click "Müsait (Çevrimiçi Ol)"
    const onlineBtn = screen.getByRole("button", { name: /Müsait/ });
    fireEvent.click(onlineBtn);

    // Verify getUserMedia and AudioContext
    expect(mockGetUserMedia).toHaveBeenCalledWith({ audio: true });
    
    await waitFor(() => {
      expect(mockDevice).toHaveBeenCalled();
      expect(mockRegister).toHaveBeenCalled();
    });
  });

  it("calls Device.connect only after explicit call-button click", async () => {
    render(<Softphone user={{ role: "admin" }} />);
    
    // Open softphone and click online
    fireEvent.click(screen.getByRole("button", { name: "Softphone" }));
    fireEvent.click(screen.getByRole("button", { name: /Müsait/ }));

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
    fireEvent.click(screen.getByRole("button", { name: /Müsait/ }));

    const errorMsg = await screen.findByText(/Mikrofon izni reddedildi/);
    expect(errorMsg).toBeInTheDocument();
  });
});
