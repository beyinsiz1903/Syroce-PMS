import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { MessageSquare, Plus, User } from 'lucide-react';
import { toast } from 'sonner';

const CRMNotes = ({ guestId }) => {
  const [notes, setNotes] = useState([]);
  const [newNote, setNewNote] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (guestId) {
      loadNotes();
    }
  }, [guestId]);

  const loadNotes = async () => {
    try {
      const response = await axios.get(`/crm/guest/${guestId}/notes`);
      setNotes(response.data.notes || []);
    } catch (error) {
      console.error('Failed to load notes:', error);
      // Mock data for demo
      setNotes([
        {
          id: '1',
          content: 'Misafir yüksek kattaki odaları tercih ediyor',
          created_by: 'Ayşe Yılmaz',
          created_at: new Date().toISOString(),
          category: 'preference'
        },
        {
          id: '2',
          content: 'Allergisi var, yastık seçimine dikkat',
          created_by: 'Mehmet Kaya',
          created_at: new Date(Date.now() - 86400000).toISOString(),
          category: 'health'
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleAddNote = async () => {
    if (!newNote.trim()) {
      toast.error('⚠️ Not boş olamaz');
      return;
    }

    try {
      await axios.post(`/crm/guest/${guestId}/note`, {
        content: newNote,
        category: 'general'
      });
      toast.success('✓ Not eklendi');
      setNewNote('');
      loadNotes();
    } catch (error) {
      toast.error('✗ Not eklenemedi');
    }
  };

  const categoryColors = {
    preference: 'bg-blue-500',
    health: 'bg-red-500',
    general: 'bg-gray-500',
    vip: 'bg-purple-500'
  };

  if (loading) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center text-lg">
          <MessageSquare className="w-5 h-5 mr-2" />
          CRM Notları
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Add Note */}
        <div className="mb-4">
          <textarea
            className="w-full p-2 border rounded-lg text-sm"
            rows="3"
            placeholder="Misafir hakkında not ekleyin..."
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
          />
          <Button
            size="sm"
            className="mt-2 w-full bg-blue-600 hover:bg-blue-700"
            onClick={handleAddNote}
          >
            <Plus className="w-4 h-4 mr-1" />
            Not Ekle
          </Button>
        </div>

        {/* Notes List */}
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {notes.length === 0 ? (
            <p className="text-center text-gray-500 text-sm py-4">Henüz not yok</p>
          ) : (
            notes.map((note) => (
              <div key={note.id} className="p-3 bg-gray-50 rounded-lg">
                <div className="flex items-start justify-between mb-2">
                  <Badge className={categoryColors[note.category] || 'bg-gray-500'}>
                    {note.category}
                  </Badge>
                  <span className="text-xs text-gray-500">
                    {new Date(note.created_at).toLocaleDateString('tr-TR')}
                  </span>
                </div>
                <p className="text-sm text-gray-800 mb-2">{note.content}</p>
                <div className="flex items-center text-xs text-gray-500">
                  <User className="w-3 h-3 mr-1" />
                  {note.created_by}
                </div>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default CRMNotes;
