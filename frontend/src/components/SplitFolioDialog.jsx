import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Split, Users, DollarSign, CheckCircle, XCircle } from 'lucide-react';

const SplitFolioDialog = ({ folio, onClose, onSuccess }) => {
  const [splitType, setSplitType] = useState('even');
  const [numFolios, setNumFolios] = useState(2);
  const [processing, setProcessing] = useState(false);

  const handleSplit = async () => {
    if (numFolios < 2 || numFolios > 10) {
      toast.error('Number of folios must be between 2 and 10');
      return;
    }

    try {
      setProcessing(true);
      const response = await axios.post(`/folio/${folio.id}/split`, {
        folio_id: folio.id,
        split_type: splitType,
        split_data: {
          num_folios: numFolios
        }
      });

      toast.success(
        <div>
          <p className="font-semibold">Folio Split Successfully!</p>
          <p className="text-xs">{response.data.new_folios.length} new folios created</p>
        </div>
      );
      
      if (onSuccess) onSuccess();
      if (onClose) onClose();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to split folio');
    } finally {
      setProcessing(false);
    }
  };

  return (
    <Card className="border-2 border-blue-500 max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle className="flex items-center">
          <Split className="w-5 h-5 mr-2 text-blue-600" />
          Split Folio - {folio.folio_number}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Folio Info */}
        <div className="p-4 bg-gray-50 rounded-lg">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-gray-600">Folio Number</p>
              <p className="font-bold">{folio.folio_number}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Guest</p>
              <p className="font-bold">{folio.guest_name || 'N/A'}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Room</p>
              <p className="font-bold">{folio.room_number || 'N/A'}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Total Balance</p>
              <p className="font-bold text-green-600">${folio.balance?.toFixed(2) || '0.00'}</p>
            </div>
          </div>
        </div>

        {/* Split Type Selection */}
        <div>
          <label className="text-sm font-medium mb-3 block">Split Method</label>
          <div className="grid grid-cols-3 gap-3">
            <Card
              className={`cursor-pointer hover:shadow-md transition ${
                splitType === 'even' ? 'border-2 border-blue-500 bg-blue-50' : ''
              }`}
              onClick={() => setSplitType('even')}
            >
              <CardContent className="p-4 text-center">
                <Users className="w-8 h-8 mx-auto mb-2 text-blue-600" />
                <p className="font-semibold text-sm">Even Split</p>
                <p className="text-xs text-gray-600 mt-1">Divide equally</p>
              </CardContent>
            </Card>

            <Card className="cursor-not-allowed opacity-50">
              <CardContent className="p-4 text-center">
                <DollarSign className="w-8 h-8 mx-auto mb-2 text-gray-400" />
                <p className="font-semibold text-sm">Custom Split</p>
                <p className="text-xs text-gray-600 mt-1">Coming soon</p>
              </CardContent>
            </Card>

            <Card className="cursor-not-allowed opacity-50">
              <CardContent className="p-4 text-center">
                <Split className="w-8 h-8 mx-auto mb-2 text-gray-400" />
                <p className="font-semibold text-sm">By Item</p>
                <p className="text-xs text-gray-600 mt-1">Coming soon</p>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Number of Folios */}
        {splitType === 'even' && (
          <div>
            <label className="text-sm font-medium mb-2 block">
              Number of Folios to Create
            </label>
            <div className="flex items-center space-x-4">
              <Input
                type="number"
                min="2"
                max="10"
                value={numFolios}
                onChange={(e) => setNumFolios(parseInt(e.target.value) || 2)}
                className="w-32"
              />
              <div className="flex-1 text-sm text-gray-600">
                {numFolios > 1 && (
                  <p>
                    Each folio will receive approximately{' '}
                    <strong className="text-green-600">
                      ${((folio.balance || 0) / numFolios).toFixed(2)}
                    </strong>
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Preview */}
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <h4 className="font-semibold text-blue-900 mb-2">Split Preview</h4>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span>Original Folio:</span>
              <span className="font-medium">{folio.folio_number}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span>Will become:</span>
              <Badge variant="outline">Split (Closed)</Badge>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span>New Folios:</span>
              <span className="font-medium">{numFolios} folios</span>
            </div>
            <div className="flex items-center justify-between text-sm font-semibold text-blue-700">
              <span>Total Balance:</span>
              <span>${folio.balance?.toFixed(2) || '0.00'}</span>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex space-x-3">
          <Button
            onClick={handleSplit}
            disabled={processing || !splitType}
            className="flex-1"
          >
            <CheckCircle className="w-4 h-4 mr-2" />
            {processing ? 'Splitting...' : 'Confirm Split'}
          </Button>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={processing}
          >
            <XCircle className="w-4 h-4 mr-2" />
            Cancel
          </Button>
        </div>

        {/* Warning */}
        <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
          <p className="text-xs text-yellow-700">
            ⚠️ <strong>Warning:</strong> This action cannot be undone. The original folio 
            will be marked as "split" and new folios will be created with distributed charges.
          </p>
        </div>
      </CardContent>
    </Card>
  );
};

export default SplitFolioDialog;
