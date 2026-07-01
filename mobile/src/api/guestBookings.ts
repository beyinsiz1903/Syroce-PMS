import { api } from './client';

export type GuestBookingHotel = {
  id?: string;
  property_name?: string;
  hotel_name?: string;
  address?: string;
};

export type GuestBookingRoom = {
  room_number?: string;
  room_type?: string;
  floor?: number;
};

export type GuestBooking = {
  id: string;
  tenant_id?: string;
  confirmation_number?: string;
  check_in?: string;
  check_out?: string;
  status?: string;
  guests_count?: number;
  total_amount?: number;
  guest_name?: string;
  qr_code_data?: string;
  can_checkin?: boolean;
  can_communicate?: boolean;
  can_order_services?: boolean;
  hotel?: GuestBookingHotel;
  room?: GuestBookingRoom;
};

export type GuestBookingsResponse = {
  active_bookings: GuestBooking[];
  past_bookings: GuestBooking[];
};

export async function getGuestBookings(): Promise<GuestBookingsResponse> {
  try {
    return await api.get<GuestBookingsResponse>('/api/guest/bookings');
  } catch {
    return { active_bookings: [], past_bookings: [] };
  }
}
