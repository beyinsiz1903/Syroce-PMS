import { TabsContent } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Plus, User } from 'lucide-react';

const GuestsTab = ({ guests, setOpenDialog, setSelectedGuest360, loadGuest360, setNewBooking, t }) => {
  return (
    <TabsContent value="guests" className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold" data-testid="guests-tab-title">Guests ({guests.length})</h2>
        <Button onClick={() => setOpenDialog('guest')} data-testid="add-guest-btn">
          <Plus className="w-4 h-4 mr-2" />
          Add Guest
        </Button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {guests.map((guest) => (
          <Card key={guest.id} data-testid={`guest-card-${guest.id}`}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">{guest.name}</CardTitle>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setSelectedGuest360(guest.id);
                    loadGuest360(guest.id);
                  }}
                  data-testid={`guest-profile-btn-${guest.id}`}
                >
                  <User className="w-4 h-4 mr-2" />
                  Profile
                </Button>
              </div>
              <CardDescription>{guest.email}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="space-y-2">
                <div><strong>Phone:</strong> {guest.phone || 'N/A'}</div>
                <div><strong>ID Number:</strong> {guest.id_number || 'N/A'}</div>
                <div><strong>Address:</strong> {guest.address || 'N/A'}</div>
              </div>
              <div className="flex gap-2 pt-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setNewBooking(prev => ({...prev, guest_id: guest.id}));
                    setOpenDialog('newbooking');
                  }}
                  data-testid={`guest-new-booking-btn-${guest.id}`}
                >
                  <Plus className="w-4 h-4 mr-2" />
                  New Booking
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </TabsContent>
  );
};

export default GuestsTab;
