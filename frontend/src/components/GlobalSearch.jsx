import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Search, User, Calendar, Home, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';

const GlobalSearch = ({ onSelectResult }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState({ guests: [], bookings: [], rooms: [] });
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (query.length < 2) {
      setResults({ guests: [], bookings: [], rooms: [] });
      return;
    }

    const searchTimeout = setTimeout(async () => {
      setLoading(true);
      try {
        const [guestsRes, bookingsRes, roomsRes] = await Promise.all([
          axios.get(`/pms/guests?search=${query}`).catch(() => ({ data: [] })),
          axios.get(`/pms/bookings?search=${query}`).catch(() => ({ data: [] })),
          axios.get(`/pms/rooms?search=${query}`).catch(() => ({ data: [] }))
        ]);

        setResults({
          guests: guestsRes.data.slice(0, 3),
          bookings: bookingsRes.data.slice(0, 3),
          rooms: roomsRes.data.slice(0, 3)
        });
      } catch (error) {
        console.error('Search error:', error);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(searchTimeout);
  }, [query]);

  const totalResults = results.guests.length + results.bookings.length + results.rooms.length;

  return (
    <div className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
        <Input
          type="text"
          placeholder="Search guests, bookings, rooms..."
          className="pl-10 pr-10"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
        />
        {query && (
          <button
            className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
            onClick={() => {
              setQuery('');
              setResults({ guests: [], bookings: [], rooms: [] });
              setIsOpen(false);
            }}
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {isOpen && query.length >= 2 && (
        <Card className="absolute z-50 w-full mt-2 max-h-96 overflow-y-auto shadow-lg">
          <CardContent className="p-2">
            {loading ? (
              <div className="text-center py-4 text-gray-500">Searching...</div>
            ) : totalResults === 0 ? (
              <div className="text-center py-4 text-gray-500">No results found</div>
            ) : (
              <div className="space-y-2">
                {/* Guests */}
                {results.guests.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-gray-500 px-2 py-1">GUESTS</div>
                    {results.guests.map((guest) => (
                      <button
                        key={guest.id}
                        className="w-full text-left px-3 py-2 hover:bg-gray-100 rounded flex items-center gap-2"
                        onClick={() => {
                          onSelectResult?.({ type: 'guest', data: guest });
                          setIsOpen(false);
                          setQuery('');
                        }}
                      >
                        <User className="w-4 h-4 text-blue-500" />
                        <div>
                          <div className="font-medium">{guest.name}</div>
                          <div className="text-xs text-gray-500">{guest.email || guest.phone}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                {/* Bookings */}
                {results.bookings.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-gray-500 px-2 py-1">BOOKINGS</div>
                    {results.bookings.map((booking) => (
                      <button
                        key={booking.id}
                        className="w-full text-left px-3 py-2 hover:bg-gray-100 rounded flex items-center gap-2"
                        onClick={() => {
                          onSelectResult?.({ type: 'booking', data: booking });
                          setIsOpen(false);
                          setQuery('');
                        }}
                      >
                        <Calendar className="w-4 h-4 text-green-500" />
                        <div>
                          <div className="font-medium">Booking #{booking.id.slice(0, 8)}</div>
                          <div className="text-xs text-gray-500">
                            {new Date(booking.check_in).toLocaleDateString()} - {new Date(booking.check_out).toLocaleDateString()}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                {/* Rooms */}
                {results.rooms.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-gray-500 px-2 py-1">ROOMS</div>
                    {results.rooms.map((room) => (
                      <button
                        key={room.id}
                        className="w-full text-left px-3 py-2 hover:bg-gray-100 rounded flex items-center gap-2"
                        onClick={() => {
                          onSelectResult?.({ type: 'room', data: room });
                          setIsOpen(false);
                          setQuery('');
                        }}
                      >
                        <Home className="w-4 h-4 text-purple-500" />
                        <div>
                          <div className="font-medium">Room {room.room_number}</div>
                          <div className="text-xs text-gray-500 capitalize">{room.room_type} - {room.status}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default GlobalSearch;
