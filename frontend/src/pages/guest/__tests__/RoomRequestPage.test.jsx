import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import RoomRequestPage from '../RoomRequestPage';
import axios from 'axios';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import * as dialogs from '@/lib/dialogs';

vi.mock('axios');
vi.mock('@/lib/dialogs', () => ({
  alertDialog: vi.fn(),
}));

const renderComponent = () => {
  return render(
    <MemoryRouter initialEntries={["/room-qr/tenant1/room1?t=dummy_token"]}>
      <Routes>
        <Route path="/room-qr/:tenantId/:roomId" element={<RoomRequestPage />} />
      </Routes>
    </MemoryRouter>
  );
};

const mockMeta = {
  hotel_name: "Test Hotel",
  room_number: "101",
  categories: [
    { id: "legacy1", department: "rooms", labels: { tr: "Eski Temizlik" } }
  ]
};

const mockCatalogue = {
  departments: [
    { department_code: "rooms", labels: { en: "Housekeeping" }, icon: "sparkles" },
    { department_code: "fnb", labels: { en: "Food" }, icon: "utensils" }
  ],
  services: [
    { service_code: "TOWEL", department_code: "rooms", labels: { en: "Towel" }, input_type: "quantity", is_chargeable: false, input_config: { min: 2, max: 5, default: 3 } },
    { service_code: "WATER", department_code: "fnb", labels: { en: "Water" }, input_type: "one_tap", is_chargeable: true, charge_warning: { en: "Extra charge" }, input_config: {} },
    { service_code: "WAKEUP", department_code: "rooms", labels: { en: "Wake Up" }, input_type: "time", input_config: { interval_minutes: 15 } },
    { service_code: "PIZZA", department_code: "fnb", labels: { en: "Pizza" }, input_type: "single_choice", input_config: { options: [{code: "large", labels: { en: "Large", tr: "Büyük" }}] } },
    { service_code: "BURGER", department_code: "fnb", labels: { en: "Burger" }, input_type: "multi_choice", input_config: { min_selections: 1, max_selections: 2, options: [{code: "cheese", labels: { en: "Cheese" }}, {code: "bacon", labels: { en: "Bacon" }}, {code: "tomato", labels: { en: "Tomato" }}] } },
    { service_code: "MEETING", department_code: "rooms", labels: { en: "Meeting" }, input_type: "date", input_config: { min_days_ahead: 1, max_days_ahead: 7 } },
    { service_code: "EVENT", department_code: "rooms", labels: { en: "Event" }, input_type: "datetime", input_config: { min_days_ahead: 0, max_days_ahead: 30, interval_minutes: 30 } }
  ]
};

const getLocalDateString = (offsetDays = 0) => {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const pad = n => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

describe('RoomRequestPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, 'language', { value: 'en-US', configurable: true });
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  // Basic rendering
  it('renders loading initially', () => {
    axios.get.mockImplementation(() => new Promise(() => {}));
    axios.post.mockImplementation(() => new Promise(() => {}));
    renderComponent();
    expect(document.querySelector('.animate-spin')).toBeInTheDocument();
  });

  // Fallbacks
  it('exact 404 legacy fallback', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.reject({ response: { status: 404 } });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText("What is your request about?")).toBeInTheDocument(); // UI.en
    });
  });

  it('403 no legacy', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.reject({ response: { status: 403 } });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText("Service Unavailable")).toBeInTheDocument();
      expect(screen.queryByText("What do you need?")).not.toBeInTheDocument();
    });
  });

  it('500 no legacy', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.reject({ response: { status: 500 } });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText("Unable to open request")).toBeInTheDocument();
    });
  });

  it('network failure no legacy', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.reject(new Error("Network Error"));
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText("Unable to open request")).toBeInTheDocument();
    });
  });

  it('malformed 200 no legacy', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.resolve({ data: { bad: "data" }, status: 200 });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText("Unable to open request")).toBeInTheDocument();
    });
  });

  it('legacy payload regression', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.reject({ response: { status: 404 } });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    
    renderComponent();
    await waitFor(() => screen.getByText("Housekeeping"));
    fireEvent.click(screen.getByText("Housekeeping"));
    await waitFor(() => screen.getByText("legacy1"));
    fireEvent.click(screen.getByText("legacy1"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url, data) => {
      if (url.includes('/submit')) {
        return Promise.resolve({ data: {} });
      }
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining("/submit"),
        expect.objectContaining({
          category: "legacy1",
          priority: "normal"
        }),
        expect.objectContaining({ headers: { "X-Guest-Session": "guest123" } })
      );
    });
  });

  it('guest thread regression', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/thread')) return Promise.resolve({ data: { messages: [{ id: "m1", body: "Hello", sender_type: "team", created_at: "2026-01-01T10:00:00Z" }] } });
      if (url.includes('/catalogue')) return Promise.reject({ response: { status: 404 } });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject({ response: { status: 404 } });
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    renderComponent();
    await waitFor(() => expect(screen.getByText("Hello")).toBeInTheDocument(), { timeout: 3000 });
  });

  // Valid Catalogue Scenarios
  const setupCatalogue = () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.resolve({ data: mockCatalogue, status: 200 });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      if (url.includes('/thread')) return Promise.reject();
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    renderComponent();
  };

  it('renders the localized public catalogue contract instead of internal codes', async () => {
    Object.defineProperty(navigator, 'language', { value: 'tr-TR', configurable: true });
    const localizedCatalogue = {
      departments: [
        { department_code: 'housekeeping', label: 'Kat Hizmetleri', icon: 'sparkles' },
      ],
      services: [
        {
          service_code: 'housekeeping.room_cleaning',
          department_code: 'housekeeping',
          label: 'Oda temizliği',
          description: 'Odanız için temizlik hizmeti talep edin.',
          icon: 'sparkles',
          input_type: 'one_tap',
          input_config: {},
          is_chargeable: false,
        },
      ],
    };

    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.resolve({ data: localizedCatalogue, status: 200 });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      if (url.includes('/thread')) return Promise.reject();
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: 'guest123' } });

    renderComponent();

    await waitFor(() => expect(screen.getByText('Kat Hizmetleri')).toBeInTheDocument());
    expect(screen.queryByText('housekeeping')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('dept-housekeeping'));

    await waitFor(() => expect(screen.getByText('Oda temizliği')).toBeInTheDocument());
    expect(screen.getByText('Odanız için temizlik hizmeti talep edin.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Talebe ekle' })).toBeInTheDocument();
    expect(screen.queryByText('housekeeping.room_cleaning')).not.toBeInTheDocument();
  });

  it('quantity default/min/max and exact payload', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-rooms"));
    fireEvent.click(screen.getByTestId("dept-rooms"));
    
    await waitFor(() => screen.getByTestId("service-TOWEL"));
    const getTowelBtns = () => screen.getByTestId("service-TOWEL").querySelectorAll("button");
    
    // Default is 3
    fireEvent.click(getTowelBtns()[1]);
    expect(screen.getByTestId("qty-TOWEL")).toHaveTextContent("3");
    
    // Add to 5 (max)
    fireEvent.click(getTowelBtns()[1]);
    fireEvent.click(getTowelBtns()[1]);
    expect(screen.getByTestId("qty-TOWEL")).toHaveTextContent("5");
    
    // Should not exceed 5
    expect(getTowelBtns()[1]).toBeDisabled();
    
    // Subtract to 2 (min)
    fireEvent.click(getTowelBtns()[0]);
    fireEvent.click(getTowelBtns()[0]);
    fireEvent.click(getTowelBtns()[0]);
    expect(screen.getByTestId("qty-TOWEL")).toHaveTextContent("2");
    
    // Subtract below min is disabled
    expect(getTowelBtns()[0]).toBeDisabled();
    
    // Test exact payload submission
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining("/submit"),
        expect.objectContaining({
          items: [
            {
              service_code: "TOWEL",
              value: { quantity: 2 }
            }
          ]
        }),
        expect.anything()
      );
    });
  });

  it('explicit remove action', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-rooms"));
    fireEvent.click(screen.getByTestId("dept-rooms"));
    await waitFor(() => screen.getByTestId("service-TOWEL"));
    
    // Add item
    fireEvent.click(screen.getByTestId("service-TOWEL").querySelectorAll("button")[1]);
    expect(screen.getByTestId("qty-TOWEL")).toHaveTextContent("3");
    
    // Click explicit remove button (should be the third button since [-, +, Remove])
    const removeBtn = screen.getByTestId("service-TOWEL").querySelector("button.text-red-500");
    fireEvent.click(removeBtn);
    
    // qty should revert to 0
    expect(screen.getByTestId("qty-TOWEL")).toHaveTextContent("0");
  });

  it('single_choice localized option and payload', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-fnb"));
    fireEvent.click(screen.getByTestId("dept-fnb"));
    
    await waitFor(() => screen.getByTestId("service-PIZZA"));
    // Since language is 'en', we expect 'Large' not 'Büyük'
    expect(screen.getByText("Select an option")).toBeInTheDocument();
    
    fireEvent.click(screen.getByText("Select an option"));
    await waitFor(() => screen.getByText("Large"));
    fireEvent.click(screen.getByText("Large"));
    
    // Submit
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining("/submit"),
        expect.objectContaining({
          items: [
            {
              service_code: "PIZZA",
              value: { selected_options: ["large"] }
            }
          ]
        }),
        expect.anything()
      );
    });
  });

  it('multi_choice min/max and duplicate prevention', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-fnb"));
    fireEvent.click(screen.getByTestId("dept-fnb"));
    
    await waitFor(() => screen.getByTestId("service-BURGER"));
    const cheeseInput = screen.getByLabelText("Cheese");
    const baconInput = screen.getByLabelText("Bacon");
    const tomatoInput = screen.getByLabelText("Tomato");
    
    fireEvent.click(cheeseInput);
    fireEvent.click(baconInput);
    
    // Max is 2, tomato should be disabled
    expect(tomatoInput).toBeDisabled();
    
    // Submit
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining("/submit"),
        expect.objectContaining({
          items: [
            {
              service_code: "BURGER",
              value: { selected_options: ["cheese", "bacon"] }
            }
          ]
        }),
        expect.anything()
      );
    });
  });

  it('date payload and outside range blocked', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-rooms"));
    fireEvent.click(screen.getByTestId("dept-rooms"));
    
    await waitFor(() => screen.getByTestId("service-MEETING"));
    const dateInput = screen.getByTestId("service-MEETING").querySelector('input[type="date"]');
    
    const validDate = getLocalDateString(3); // within 1 to 7 days
    const invalidDateBefore = getLocalDateString(0); // too early
    const invalidDateAfter = getLocalDateString(8); // too late
    
    // Set invalid date before
    fireEvent.change(dateInput, { target: { value: invalidDateBefore } });
    // Still empty or not added to cart, cart count is 0
    expect(screen.queryByTestId("sticky-cart")).not.toBeInTheDocument();
    
    // Set invalid date after
    fireEvent.change(dateInput, { target: { value: invalidDateAfter } });
    expect(screen.queryByTestId("sticky-cart")).not.toBeInTheDocument();
    
    // Set valid date
    fireEvent.change(dateInput, { target: { value: validDate } });
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining("/submit"),
        expect.objectContaining({
          items: [ { service_code: "MEETING", value: { date_value: validDate } } ]
        }),
        expect.anything()
      );
    });
  });

  it('time payload mapped to step and invalid interval blocked', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-rooms"));
    fireEvent.click(screen.getByTestId("dept-rooms"));
    
    await waitFor(() => screen.getByTestId("service-WAKEUP"));
    const timeInput = screen.getByTestId("service-WAKEUP").querySelector('input[type="time"]');
    expect(timeInput).toHaveAttribute("step", "900"); // 15 min * 60
    
    // invalid interval (09:05)
    fireEvent.change(timeInput, { target: { value: "09:05" } });
    expect(screen.queryByTestId("sticky-cart")).not.toBeInTheDocument();
    
    // valid interval (09:15)
    fireEvent.change(timeInput, { target: { value: "09:15" } });
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining("/submit"),
        expect.objectContaining({
          items: [ { service_code: "WAKEUP", value: { time_value: "09:15" } } ]
        }),
        expect.anything()
      );
    });
  });

  it('datetime payload bounds and interval step', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-rooms"));
    fireEvent.click(screen.getByTestId("dept-rooms"));
    
    await waitFor(() => screen.getByTestId("service-EVENT"));
    const dtInput = screen.getByTestId("service-EVENT").querySelector('input[type="datetime-local"]');
    expect(dtInput).toHaveAttribute("step", "1800"); // 30 min * 60
    
    const validDT = getLocalDateString(1) + "T10:30"; // valid date and 30m interval
    const invalidDT_Interval = getLocalDateString(1) + "T10:15"; // invalid interval
    const invalidDT_Before = getLocalDateString(-1) + "T10:30"; // invalid date
    
    // Test interval
    fireEvent.change(dtInput, { target: { value: invalidDT_Interval } });
    expect(screen.queryByTestId("sticky-cart")).not.toBeInTheDocument();
    
    // Test bounds
    fireEvent.change(dtInput, { target: { value: invalidDT_Before } });
    expect(screen.queryByTestId("sticky-cart")).not.toBeInTheDocument();
    
    // Valid
    fireEvent.change(dtInput, { target: { value: validDT } });
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining("/submit"),
        expect.objectContaining({
          items: [ { service_code: "EVENT", value: { datetime_value: validDT } } ]
        }),
        expect.anything()
      );
    });
  });

  it('max 10 unique services', async () => {
    const largeCatalogue = { departments: [{department_code: "d1", labels: {en: "d1"}}], services: [] };
    for (let i = 0; i < 15; i++) {
      largeCatalogue.services.push({ service_code: `S${i}`, department_code: "d1", input_type: "one_tap", input_config: {} });
    }
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.resolve({ data: largeCatalogue, status: 200 });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    renderComponent();
    
    await waitFor(() => screen.getByTestId("dept-d1"));
    fireEvent.click(screen.getByTestId("dept-d1"));
    
    await waitFor(() => screen.getByTestId("service-S0"));
    for (let i = 0; i < 12; i++) {
      const btn = screen.getByTestId(`service-S${i}`).querySelector("button");
      fireEvent.click(btn);
    }
    
    expect(screen.getByTestId("sticky-cart")).toHaveTextContent("10 items");
  });

  it('duplicate service_code updates existing item', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-rooms"));
    fireEvent.click(screen.getByTestId("dept-rooms"));
    
    await waitFor(() => screen.getByTestId("service-TOWEL"));
    const towelPlusBtn = screen.getByTestId("service-TOWEL").querySelectorAll("button")[1];
    fireEvent.click(towelPlusBtn);
    fireEvent.click(towelPlusBtn);
    
    expect(screen.getByTestId("sticky-cart")).toHaveTextContent("4 items"); // min 2, +1 = 3, +1 = 4
  });

  it('per-item note trimming', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-fnb"));
    fireEvent.click(screen.getByTestId("dept-fnb"));
    
    await waitFor(() => screen.getByTestId("service-WATER"));
    fireEvent.click(screen.getByTestId("service-WATER").querySelector("button"));
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByTestId("note-WATER"));
    
    fireEvent.change(screen.getByTestId("note-WATER"), { target: { value: "  Cold please  " } });
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining("/submit"),
        expect.objectContaining({
          items: [ { service_code: "WATER", note: "Cold please" } ]
        }),
        expect.anything()
      );
    });
  });

  it('chargeable warning', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-fnb"));
    fireEvent.click(screen.getByTestId("dept-fnb"));
    
    await waitFor(() => screen.getByTestId("service-WATER"));
    expect(screen.getByText("Extra charge")).toBeInTheDocument();
    
    fireEvent.click(screen.getByTestId("service-WATER").querySelector("button"));
    fireEvent.click(screen.getByText("Review Request"));
    
    await waitFor(() => {
      expect(screen.getByText("This service may be subject to an additional charge.")).toBeInTheDocument();
    });
  });

  it('structured payload allowlist', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-fnb"));
    fireEvent.click(screen.getByTestId("dept-fnb"));
    
    await waitFor(() => screen.getByTestId("service-WATER"));
    fireEvent.click(screen.getByTestId("service-WATER").querySelector("button"));
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    await waitFor(() => {
      const call = axios.post.mock.calls.find(c => c[0].includes('/submit'));
      const payload = call[1];
      expect(Object.keys(payload)).toEqual(expect.arrayContaining(["language", "idempotency_key", "items"]));
      expect(payload).not.toHaveProperty("guest_name");
      expect(payload).not.toHaveProperty("guest_phone");
      expect(payload).not.toHaveProperty("priority");
      expect(payload).not.toHaveProperty("category");
      
      const item = payload.items[0];
      expect(item).not.toHaveProperty("is_chargeable");
      expect(item).not.toHaveProperty("labels");
      expect(item).not.toHaveProperty("catalogueItem");
    });
  });

  it('guest token only in X-Guest-Session', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-fnb"));
    fireEvent.click(screen.getByTestId("dept-fnb"));
    
    await waitFor(() => screen.getByTestId("service-WATER"));
    fireEvent.click(screen.getByTestId("service-WATER").querySelector("button"));
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    await waitFor(() => {
      const call = axios.post.mock.calls.find(c => c[0].includes('/submit'));
      expect(call[1]).not.toHaveProperty("token");
      expect(call[1]).not.toHaveProperty("t");
      expect(call[2].headers).toHaveProperty("X-Guest-Session", "guest123");
    });
  });

  it('retry preserves exact key and payload', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-fnb"));
    fireEvent.click(screen.getByTestId("dept-fnb"));
    
    await waitFor(() => screen.getByTestId("service-WATER"));
    fireEvent.click(screen.getByTestId("service-WATER").querySelector("button"));
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.reject({ response: { status: 500, data: { detail: "Failed" } } });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    
    await waitFor(() => {
      expect(dialogs.alertDialog).toHaveBeenCalledWith({ message: "Failed" });
    });
    
    const call1 = axios.post.mock.calls.find(c => c[0].includes('/submit'));
    const key1 = call1[1].idempotency_key;
    
    // Setup for success on second try
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    
    await waitFor(() => {
      const calls = axios.post.mock.calls.filter(c => c[0].includes('/submit'));
      expect(calls.length).toBe(2);
      expect(calls[1][1].idempotency_key).toBe(key1);
    });
  });

  it('cart edit invalidates old snapshot', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-fnb"));
    fireEvent.click(screen.getByTestId("dept-fnb"));
    
    await waitFor(() => screen.getByTestId("service-WATER"));
    fireEvent.click(screen.getByTestId("service-WATER").querySelector("button"));
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.reject({ response: { status: 500, data: { detail: "Failed" } } });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    
    await waitFor(() => {
      expect(dialogs.alertDialog).toHaveBeenCalledWith({ message: "Failed" });
    });
    
    const call1 = axios.post.mock.calls.find(c => c[0].includes('/submit'));
    const key1 = call1[1].idempotency_key;
    
    // User goes back, edits cart
    fireEvent.click(screen.getByText("Back"));
    await waitFor(() => screen.getByTestId("service-WATER"));
    fireEvent.click(screen.getByTestId("service-WATER").querySelector("button")); // removes
    
    // Add something else
    await waitFor(() => screen.getByTestId("service-PIZZA"));
    fireEvent.click(screen.getByText("Select an option"));
    await waitFor(() => screen.getByText("Large"));
    fireEvent.click(screen.getByText("Large"));
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    
    await waitFor(() => {
      const calls = axios.post.mock.calls.filter(c => c[0].includes('/submit'));
      expect(calls.length).toBe(2);
      expect(calls[1][1].idempotency_key).not.toBe(key1);
    });
  });

  it('same-tick double-click sends once', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-fnb"));
    fireEvent.click(screen.getByTestId("dept-fnb"));
    
    await waitFor(() => screen.getByTestId("service-WATER"));
    fireEvent.click(screen.getByTestId("service-WATER").querySelector("button"));
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    const submitBtn = screen.getByText("Submit Request");
    // Fire double click in same tick
    fireEvent.click(submitBtn);
    fireEvent.click(submitBtn);
    
    await waitFor(() => {
      const calls = axios.post.mock.calls.filter(c => c[0].includes('/submit'));
      expect(calls.length).toBe(1);
    });
  });

  it('409 behavior', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-fnb"));
    fireEvent.click(screen.getByTestId("dept-fnb"));
    
    await waitFor(() => screen.getByTestId("service-WATER"));
    fireEvent.click(screen.getByTestId("service-WATER").querySelector("button"));
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.reject({ response: { status: 409, data: { detail: "Conflict" } } });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    
    await waitFor(() => {
      expect(dialogs.alertDialog).toHaveBeenCalledWith({ message: "Your request may have already been processed or updated. Please try again." });
    });
  });

  it('shows a readable success summary without internal references', async () => {
    setupCatalogue();
    await waitFor(() => screen.getByTestId("dept-fnb"));
    fireEvent.click(screen.getByTestId("dept-fnb"));
    
    await waitFor(() => screen.getByTestId("service-WATER"));
    fireEvent.click(screen.getByTestId("service-WATER").querySelector("button"));
    
    fireEvent.click(screen.getByText("Review Request"));
    await waitFor(() => screen.getByText("Submit Request"));
    
    axios.post.mockImplementation((url) => {
      if (url.includes('/submit')) return Promise.resolve({ data: { submission_reference: "SUB123", request_references: [{ service_code: "WATER", request_reference: "REQ999" }] } });
      return Promise.resolve({ data: { session_token: "guest123" } });
    });
    
    fireEvent.click(screen.getByText("Submit Request"));
    
    await waitFor(() => {
      expect(screen.getByTestId("success-summary")).toHaveTextContent("Water");
      expect(screen.queryByText(/SUB123/)).not.toBeInTheDocument();
      expect(screen.queryByText(/REQ999/)).not.toBeInTheDocument();
      expect(screen.queryByText(/WATER:/)).not.toBeInTheDocument();
    });
  });

  it('malformed department record', async () => {
    const badCatalogue = {
      departments: [{ department_code: "", labels: { en: "Bad" } }],
      services: []
    };
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.resolve({ data: badCatalogue, status: 200 });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    renderComponent();
    await waitFor(() => expect(screen.getByText("Unable to open request")).toBeInTheDocument());
  });

  it('malformed service record', async () => {
    const badCatalogue = {
      departments: [{ department_code: "rooms", labels: { en: "Rooms" } }],
      services: [{ service_code: "S1", department_code: "invalid_dept", input_type: "one_tap", input_config: {} }]
    };
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.resolve({ data: badCatalogue, status: 200 });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    renderComponent();
    await waitFor(() => expect(screen.getByText("Unable to open request")).toBeInTheDocument());
  });

  it('duplicate service_code response', async () => {
    const badCatalogue = {
      departments: [{ department_code: "rooms", labels: { en: "Rooms" } }],
      services: [
        { service_code: "S1", department_code: "rooms", input_type: "one_tap", input_config: {} },
        { service_code: "S1", department_code: "rooms", input_type: "quantity", input_config: {} }
      ]
    };
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.resolve({ data: badCatalogue, status: 200 });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    renderComponent();
    await waitFor(() => expect(screen.getByText("Unable to open request")).toBeInTheDocument());
  });
});
