import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Upload, Camera, CheckCircle } from 'lucide-react';

/**
 * Passport Scan + OCR
 * Automatic data extraction from passport
 */
const PassportScanOCR = ({ onDataExtracted }) => {
  const [scanning, setScanning] = useState(false);
  const [extractedData, setExtractedData] = useState(null);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setScanning(true);
    const formData = new FormData();
    formData.append('passport_image', file);

    try {
      const response = await axios.post('/guests/passport-ocr', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setExtractedData(response.data);
      toast.success('Passport data extracted!');
      
      if (onDataExtracted) onDataExtracted(response.data);
    } catch (error) {
      toast.error('OCR extraction failed');
    } finally {
      setScanning(false);
    }
  };

  return (
    <Card className="border-2 border-blue-300">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Camera className="w-5 h-5 text-blue-600" />
          Passport Scan + OCR
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
          <input
            type="file"
            accept="image/*"
            onChange={handleFileUpload}
            className="hidden"
            id="passport-upload"
          />
          <label htmlFor="passport-upload" className="cursor-pointer">
            <Upload className="w-12 h-12 mx-auto text-gray-400 mb-2" />
            <p className="text-sm text-gray-600">Click to upload passport photo</p>
            <p className="text-xs text-gray-400">Supports: JPG, PNG, PDF</p>
          </label>
        </div>

        {scanning && (
          <div className="text-center py-4">
            <div className="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full mx-auto mb-2"></div>
            <p className="text-sm text-gray-600">Extracting data...</p>
          </div>
        )}

        {extractedData && (
          <div className="p-4 bg-green-50 border border-green-200 rounded space-y-2">
            <div className="flex items-center gap-2 text-green-700 font-semibold">
              <CheckCircle className="w-4 h-4" />
              Data Extracted Successfully
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-gray-600">Name:</span>
                <p className="font-semibold">{extractedData.name}</p>
              </div>
              <div>
                <span className="text-gray-600">Passport No:</span>
                <p className="font-semibold">{extractedData.passport_number}</p>
              </div>
              <div>
                <span className="text-gray-600">Nationality:</span>
                <p className="font-semibold">{extractedData.nationality}</p>
              </div>
              <div>
                <span className="text-gray-600">Date of Birth:</span>
                <p className="font-semibold">{extractedData.dob}</p>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default PassportScanOCR;