import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { FileText, Wrench, Package, Plus } from 'lucide-react';

/**
 * Room Notes Manager
 * Track issues, mini-bar updates, maintenance due dates
 */
const RoomNotesManager = ({ roomId, roomNumber }) => {
  const [notes, setNotes] = useState([
    { type: 'issue', text: 'TV remote not working', created: '2025-11-19', status: 'open' },
    { type: 'minibar', text: 'Mini-bar restocked', created: '2025-11-19', status: 'done' }
  ]);
  const [newNote, setNewNote] = useState('');
  const [noteType, setNoteType] = useState('issue');

  const addNote = async () => {
    if (!newNote.trim()) return;

    try {
      await axios.post('/rooms/add-note', {
        room_id: roomId,
        type: noteType,
        text: newNote
      });

      setNotes([{ type: noteType, text: newNote, created: new Date().toISOString().split('T')[0], status: 'open' }, ...notes]);
      setNewNote('');
      toast.success('Note added');
    } catch (error) {
      toast.error('Failed to add note');
    }
  };

  const getNoteIcon = (type) => {
    switch(type) {
      case 'issue': return <Wrench className="w-4 h-4 text-red-600" />;
      case 'minibar': return <Package className="w-4 h-4 text-blue-600" />;
      case 'maintenance': return <FileText className="w-4 h-4 text-orange-600" />;
      default: return <FileText className="w-4 h-4" />;
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Room {roomNumber} - Notes</span>
          <Badge variant="outline">Next Maintenance: Dec 15</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Add Note */}
        <div className="space-y-2">
          <div className="flex gap-2">
            <select
              value={noteType}
              onChange={(e) => setNoteType(e.target.value)}
              className="border rounded px-3 py-2 text-sm"
            >
              <option value="issue">Issue</option>
              <option value="minibar">Mini-bar Update</option>
              <option value="maintenance">Maintenance</option>
            </select>
            <Textarea
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
              placeholder="Add note..."
              rows={2}
              className="flex-1"
            />
            <Button onClick={addNote} size="sm">
              <Plus className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Notes List */}
        <div className="space-y-2">
          {notes.map((note, idx) => (
            <div key={idx} className="p-3 bg-gray-50 rounded border-l-4 border-gray-300">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-2">
                  {getNoteIcon(note.type)}
                  <div>
                    <p className="text-sm">{note.text}</p>
                    <p className="text-xs text-gray-500">{note.created}</p>
                  </div>
                </div>
                <Badge className={note.status === 'open' ? 'bg-orange-500' : 'bg-green-500'}>
                  {note.status}
                </Badge>
              </div>
            </div>
          ))}
        </div>

        {/* Mini-bar Last Update */}
        <div className="p-3 bg-blue-50 border border-blue-200 rounded text-sm">
          <strong>Mini-bar Last Update:</strong> Today, 14:30
        </div>
      </CardContent>
    </Card>
  );
};

export default RoomNotesManager;