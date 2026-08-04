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
    { department_code: "rooms", label: "Housekeeping", icon: "sparkles" },
    { department_code: "fnb", label: "Food", icon: "utensils" }
  ],
  services: [
    { service_code: "TOWEL", department_code: "rooms", label: "Towel", input_type: "quantity", is_chargeable: false },
    { service_code: "WATER", department_code: "fnb", label: "Water", input_type: "one_tap", is_chargeable: true, charge_warning: "Extra charge" },
    { service_code: "WAKEUP", department_code: "rooms", label: "Wake Up", input_type: "time" },
    { service_code: "PIZZA", department_code: "fnb", label: "Pizza", input_type: "single_choice", input_config: { options: [{code: "large", label: "Large"}] } },
    { service_code: "BURGER", department_code: "fnb", label: "Burger", input_type: "multi_choice", input_config: { options: [{code: "cheese", label: "Cheese"}, {code: "bacon", label: "Bacon"}] } },
  ]
};

describe('RoomRequestPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, 'language', { value: 'tr-TR', configurable: true });
  });

  it('renders loading initially', () => {
    axios.get.mockImplementation(() => new Promise(() => {}));
    axios.post.mockImplementation(() => new Promise(() => {}));
    renderComponent();
    expect(document.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('exact 404 catalogue falls back to legacy mode', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.reject({ response: { status: 404 } });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText("Ne için talep oluşturuyorsunuz?")).toBeInTheDocument();
      // Legacy department buttons
      expect(screen.getByText("Kat Hizmetleri")).toBeInTheDocument(); // from translated DEPT_LABELS
    });
  });

  it('403 catalogue shows unavailable, not legacy UI', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.reject({ response: { status: 403 } });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });
    
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText("Hizmet Kullanılamıyor")).toBeInTheDocument();
      expect(screen.queryByText("Ne için talep oluşturuyorsunuz?")).not.toBeInTheDocument();
    });
  });

  it('valid catalogue renders departments', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.resolve({ data: mockCatalogue, status: 200 });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      if (url.includes('/thread')) return Promise.reject();
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });

    renderComponent();
    await waitFor(() => {
      expect(screen.getByText("Housekeeping")).toBeInTheDocument();
      expect(screen.getByText("Food")).toBeInTheDocument();
    });
  });

  it('selecting a department renders its services', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.resolve({ data: mockCatalogue, status: 200 });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });

    renderComponent();
    await waitFor(() => screen.getByTestId("dept-rooms"));
    
    fireEvent.click(screen.getByTestId("dept-rooms"));
    
    await waitFor(() => {
      expect(screen.getByTestId("service-TOWEL")).toBeInTheDocument();
      expect(screen.getByTestId("service-WAKEUP")).toBeInTheDocument();
      // food items should not be visible
      expect(screen.queryByTestId("service-WATER")).not.toBeInTheDocument();
    });
  });

  it('adds items to cart and submits structured payload', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/catalogue')) return Promise.resolve({ data: mockCatalogue, status: 200 });
      if (url.includes('/room-qr/tenant1/room1')) return Promise.resolve({ data: mockMeta });
      return Promise.reject();
    });
    axios.post.mockResolvedValue({ data: { session_token: "guest123" } });

    renderComponent();
    
    // Select rooms
    await waitFor(() => screen.getByTestId("dept-rooms"));
    fireEvent.click(screen.getByTestId("dept-rooms"));
    
    // Increase towel quantity
    await waitFor(() => screen.getByTestId("service-TOWEL"));
    const towelAddBtn = screen.getByTestId("service-TOWEL").querySelectorAll("button")[1]; // + button
    fireEvent.click(towelAddBtn);
    fireEvent.click(towelAddBtn); // qty 2

    // Check sticky cart
    await waitFor(() => {
      expect(screen.getByTestId("sticky-cart")).toHaveTextContent("2 seçim");
    });
    
    // Go to review
    fireEvent.click(screen.getByText("Talebi İncele"));
    
    await waitFor(() => {
      expect(screen.getByTestId("review-item-TOWEL")).toBeInTheDocument();
    });

    // Mock submit
    axios.post.mockImplementation((url, data) => {
      if (url.includes('/submit')) {
        return Promise.resolve({ data: {} });
      }
      return Promise.resolve({ data: { session_token: "guest123" } });
    });

    fireEvent.click(screen.getByText("Talebi Gönder"));
    
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining("/submit"),
        expect.objectContaining({
          language: "tr",
          items: [
            {
              service_code: "TOWEL",
              value: { quantity: 2 },
              note: undefined
            }
          ],
          idempotency_key: expect.any(String)
        }),
        expect.objectContaining({ headers: { "X-Guest-Session": "guest123" } })
      );
    });
  });
});
