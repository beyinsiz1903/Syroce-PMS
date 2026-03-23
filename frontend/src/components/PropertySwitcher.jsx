import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { 
  Building2, 
  MapPin, 
  CheckCircle,
  Search,
  Hotel,
  Home
} from 'lucide-react';

const PropertySwitcher = ({ onPropertyChange }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [properties, setProperties] = useState([]);
  const [currentPropertyId, setCurrentPropertyId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    // Load current property from localStorage
    const savedPropertyId = localStorage.getItem('current_property_id');
    if (savedPropertyId) {
      setCurrentPropertyId(savedPropertyId);
    }
  }, []);

  const loadProperties = async () => {
    try {
      setLoading(true);
      const response = await axios.get('/properties/quick-list');
      setProperties(response.data.properties || []);
      
      // Set current property if available from API
      if (response.data.current_property_id) {
        setCurrentPropertyId(response.data.current_property_id);
        localStorage.setItem('current_property_id', response.data.current_property_id);
      }
    } catch (error) {
      console.error('Failed to load properties:', error);
      toast.error('Tesisler yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const handleSwitchProperty = async (propertyId, propertyName) => {
    try {
      await axios.put(`/user/switch-property/${propertyId}`);
      
      // Update local state
      setCurrentPropertyId(propertyId);
      localStorage.setItem('current_property_id', propertyId);
      
      toast.success(`${propertyName} tesisine geçildi`);
      setIsOpen(false);
      
      // Notify parent component
      if (onPropertyChange) {
        onPropertyChange(propertyId);
      }
      
      // Reload page to refresh data for new property
      setTimeout(() => {
        window.location.reload();
      }, 500);
    } catch (error) {
      console.error('Failed to switch property:', error);
      toast.error('Tesis değiştirilemedi');
    }
  };

  const handleOpen = () => {
    setIsOpen(true);
    loadProperties();
  };

  const getPropertyIcon = (type) => {
    switch (type) {
      case 'resort':
        return <Home className="h-5 w-5 text-blue-500" />;
      case 'boutique':
        return <Building2 className="h-5 w-5 text-purple-500" />;
      default:
        return <Hotel className="h-5 w-5 text-green-500" />;
    }
  };

  const filteredProperties = properties.filter(prop =>
    prop.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    prop.location.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const currentProperty = properties.find(p => 
    p.id === currentPropertyId || p.property_id === currentPropertyId
  );

  return (
    <>
      {/* Floating Button */}
      <button
        onClick={handleOpen}
        className="fixed bottom-20 left-4 z-50 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-full p-3 shadow-lg hover:shadow-xl transition-all hover:scale-110"
        title="Tesis Değiştir"
      >
        <Building2 className="h-6 w-6" />
        {properties.length > 1 && (
          <Badge className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full h-5 w-5 flex items-center justify-center p-0 text-xs">
            {properties.length}
          </Badge>
        )}
      </button>

      {/* Property Switcher Modal */}
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Building2 className="h-5 w-5" />
              Tesis Seç
            </DialogTitle>
          </DialogHeader>

          {/* Current Property Badge */}
          {currentProperty && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-5 w-5 text-blue-600" />
                <div>
                  <div className="font-semibold text-blue-900">Aktif Tesis</div>
                  <div className="text-sm text-blue-700">{currentProperty.name}</div>
                </div>
              </div>
            </div>
          )}

          {/* Search */}
          {properties.length > 3 && (
            <div className="mb-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  type="text"
                  placeholder="Tesis ara..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
          )}

          {/* Properties List */}
          {loading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
              <p className="text-gray-500 mt-2">Tesisler yükleniyor...</p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredProperties.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <Building2 className="h-12 w-12 mx-auto mb-2 text-gray-300" />
                  <p>Tesis bulunamadı</p>
                </div>
              ) : (
                filteredProperties.map((property) => {
                  const isActive = property.id === currentPropertyId || property.property_id === currentPropertyId;
                  
                  return (
                    <button
                      key={property.id || property.property_id}
                      onClick={() => !isActive && handleSwitchProperty(
                        property.property_id || property.id, 
                        property.name
                      )}
                      className={`w-full text-left p-4 rounded-lg border-2 transition-all ${
                        isActive 
                          ? 'border-indigo-500 bg-indigo-50 cursor-default' 
                          : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'
                      }`}
                      disabled={isActive}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-3 flex-1">
                          {getPropertyIcon(property.type)}
                          <div className="flex-1">
                            <div className="font-semibold text-gray-900 flex items-center gap-2">
                              {property.name}
                              {isActive && (
                                <CheckCircle className="h-4 w-4 text-indigo-600" />
                              )}
                            </div>
                            <div className="text-sm text-gray-600 flex items-center gap-1 mt-1">
                              <MapPin className="h-3 w-3" />
                              {property.location}
                            </div>
                            <div className="flex items-center gap-2 mt-2">
                              <Badge variant="outline" className="text-xs">
                                {property.type === 'resort' ? 'Resort' : 
                                 property.type === 'boutique' ? 'Butik Otel' : 'Otel'}
                              </Badge>
                              {property.room_count > 0 && (
                                <Badge variant="outline" className="text-xs">
                                  {property.room_count} Oda
                                </Badge>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          )}

          {/* Info */}
          <div className="mt-4 text-xs text-gray-500 text-center">
            Tesis değiştirdiğinizde sayfa yeniden yüklenecektir
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default PropertySwitcher;
