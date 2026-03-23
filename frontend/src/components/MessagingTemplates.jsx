import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { 
  MessageSquare, 
  Phone, 
  Mail,
  Send,
  RefreshCw,
  Copy,
  Edit
} from 'lucide-react';

const MessagingTemplates = () => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [sendModalOpen, setSendModalOpen] = useState(false);
  const [sendData, setSendData] = useState({
    recipient: '',
    variables: {}
  });

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      setLoading(true);
      const response = await axios.get('/messaging/templates');
      setTemplates(response.data.templates || []);
    } catch (error) {
      console.error('Failed to load templates:', error);
      toast.error('Failed to load templates');
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!selectedTemplate || !sendData.recipient) {
      toast.error('Please fill all required fields');
      return;
    }

    try {
      const response = await axios.post('/messaging/send', {
        recipient: sendData.recipient,
        template_id: selectedTemplate.id,
        variables: sendData.variables,
        channel: selectedTemplate.type
      });

      toast.success(
        <div>
          <p className="font-semibold">Message Sent! (Mock)</p>
          <p className="text-xs">{response.data.note}</p>
        </div>
      );
      
      setSendModalOpen(false);
      setSelectedTemplate(null);
      setSendData({ recipient: '', variables: {} });
    } catch (error) {
      toast.error('Failed to send message');
    }
  };

  const getChannelIcon = (type) => {
    switch (type) {
      case 'whatsapp':
        return <MessageSquare className="w-5 h-5 text-green-600" />;
      case 'sms':
        return <Phone className="w-5 h-5 text-purple-600" />;
      case 'email':
        return <Mail className="w-5 h-5 text-blue-600" />;
      default:
        return null;
    }
  };

  const getChannelBadge = (type) => {
    const colors = {
      whatsapp: 'bg-green-100 text-green-700',
      sms: 'bg-purple-100 text-purple-700',
      email: 'bg-blue-100 text-blue-700'
    };
    return colors[type] || 'bg-gray-100 text-gray-700';
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-600 mx-auto" />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center">
              <MessageSquare className="w-5 h-5 mr-2 text-blue-600" />
              Message Templates ({templates.length})
            </CardTitle>
            <div className="flex items-center space-x-2">
              <Button variant="outline" size="sm" onClick={loadTemplates}>
                <RefreshCw className="w-4 h-4 mr-2" />
                Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {/* Channel Tabs */}
          <div className="flex space-x-2 mb-6">
            <Badge className="bg-green-100 text-green-700 hover:bg-green-100">
              <MessageSquare className="w-3 h-3 mr-1" />
              WhatsApp
            </Badge>
            <Badge className="bg-purple-100 text-purple-700 hover:bg-purple-100">
              <Phone className="w-3 h-3 mr-1" />
              SMS
            </Badge>
            <Badge className="bg-blue-100 text-blue-700 hover:bg-blue-100">
              <Mail className="w-3 h-3 mr-1" />
              Email
            </Badge>
          </div>

          {/* Templates List */}
          <div className="space-y-3">
            {templates.map((template) => (
              <Card key={template.id} className="hover:shadow-md transition">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start space-x-3 flex-1">
                      {getChannelIcon(template.type)}
                      <div className="flex-1">
                        <div className="flex items-center space-x-2 mb-2">
                          <h3 className="font-bold text-gray-900">{template.name}</h3>
                          <Badge className={getChannelBadge(template.type)}>
                            {template.type}
                          </Badge>
                        </div>
                        <p className="text-sm text-gray-600 mb-2">{template.content}</p>
                        {template.variables && template.variables.length > 0 && (
                          <div className="flex items-center space-x-2">
                            <span className="text-xs text-gray-500">Variables:</span>
                            {template.variables.map((v, idx) => (
                              <Badge key={idx} variant="outline" className="text-xs">
                                {v}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex space-x-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          navigator.clipboard.writeText(template.content);
                          toast.success('Template copied to clipboard');
                        }}
                      >
                        <Copy className="w-4 h-4" />
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => {
                          setSelectedTemplate(template);
                          setSendModalOpen(true);
                        }}
                      >
                        <Send className="w-4 h-4 mr-1" />
                        Send
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {templates.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              No templates available
            </div>
          )}
        </CardContent>
      </Card>

      {/* Send Message Modal */}
      {sendModalOpen && selectedTemplate && (
        <Card className="border-2 border-blue-500">
          <CardHeader>
            <CardTitle className="flex items-center">
              {getChannelIcon(selectedTemplate.type)}
              <span className="ml-2">Send: {selectedTemplate.name}</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">
                Recipient ({selectedTemplate.type === 'email' ? 'Email' : 'Phone'})
              </label>
              <Input
                placeholder={selectedTemplate.type === 'email' ? 'email@example.com' : '+1234567890'}
                value={sendData.recipient}
                onChange={(e) => setSendData({ ...sendData, recipient: e.target.value })}
              />
            </div>

            {selectedTemplate.variables && selectedTemplate.variables.length > 0 && (
              <div>
                <label className="text-sm font-medium mb-2 block">Variables</label>
                <div className="space-y-2">
                  {selectedTemplate.variables.map((varName) => (
                    <div key={varName}>
                      <label className="text-xs text-gray-600">{varName}</label>
                      <Input
                        placeholder={`Enter ${varName}`}
                        value={sendData.variables[varName] || ''}
                        onChange={(e) =>
                          setSendData({
                            ...sendData,
                            variables: { ...sendData.variables, [varName]: e.target.value }
                          })
                        }
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div>
              <label className="text-sm font-medium mb-2 block">Preview</label>
              <Textarea
                value={selectedTemplate.content}
                readOnly
                className="bg-gray-50"
                rows={4}
              />
            </div>

            <div className="flex space-x-2">
              <Button onClick={handleSendMessage} className="flex-1">
                <Send className="w-4 h-4 mr-2" />
                Send Message (Mock)
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setSendModalOpen(false);
                  setSelectedTemplate(null);
                  setSendData({ recipient: '', variables: {} });
                }}
              >
                Cancel
              </Button>
            </div>

            <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
              <p className="text-xs text-yellow-700">
                ⚠️ <strong>Mock Mode:</strong> This is a demonstration. Real WhatsApp/SMS integration 
                requires API keys and setup with providers like Twilio, WhatsApp Business API, etc.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Info Banner */}
      <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
        <CardContent className="p-4">
          <div className="flex items-start space-x-3">
            <div className="bg-blue-100 p-2 rounded-full">
              <MessageSquare className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">💬 Multi-Channel Messaging</h4>
              <p className="text-sm text-gray-600">
                Send automated messages via WhatsApp, SMS, and Email. 
                Templates support dynamic variables for personalization. 
                <strong> Production integration requires API setup.</strong>
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default MessagingTemplates;
