import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { FileText, Upload, Trash2, Loader2, BookOpen, Search, AlertCircle } from 'lucide-react';

const AIKnowledgeBase = () => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await axios.get('/ai/knowledge');
      setDocuments(res.data.documents || []);
    } catch (err) {
      console.error(err);
      if (err.response?.status === 503) {
        setError("AI Bilgi Bankası (ChromaDB) şu anda aktif değil veya sunucuya bağlanılamıyor.");
      } else {
        setError(err.response?.data?.detail || "Dökümanlar yüklenirken bir hata oluştu.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!file.name.endsWith('.pdf') && !file.name.endsWith('.txt')) {
      alert("Sadece PDF ve TXT dosyaları desteklenmektedir.");
      return;
    }

    try {
      setUploading(true);
      setError(null);
      
      const formData = new FormData();
      formData.append('file', file);
      
      await axios.post('/ai/knowledge/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      await fetchDocuments();
      e.target.value = ''; // Reset input
    } catch (err) {
      console.error(err);
      if (err.response?.status === 503) {
        setError("AI Bilgi Bankası (ChromaDB) şu anda aktif değil veya sunucuya bağlanılamıyor.");
      } else {
        setError(err.response?.data?.detail || "Yükleme sırasında hata oluştu.");
      }
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (source) => {
    if (!window.confirm(`${source} dosyasını silmek istediğinize emin misiniz?`)) return;
    
    try {
      setLoading(true);
      await axios.delete(`/ai/knowledge/${source}`);
      await fetchDocuments();
    } catch (err) {
      console.error(err);
      setError("Silme işlemi başarısız.");
      setLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6 h-full flex flex-col">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-indigo-600" />
            AI Bilgi Bankası (Knowledge Base)
          </h2>
          <p className="text-slate-500 mt-1">
            Yapay zekanın otel politikaları, sıkça sorulan sorular (SSS) ve prosedürler hakkında bilgi sahibi olmasını sağlayın.
          </p>
        </div>
        
        <div>
          <input 
            type="file" 
            id="kb-upload" 
            className="hidden" 
            accept=".pdf,.txt"
            onChange={handleFileUpload}
            disabled={uploading}
          />
          <label htmlFor="kb-upload">
            <Button as="span" disabled={uploading} className="bg-indigo-600 hover:bg-indigo-700 text-white cursor-pointer">
              {uploading ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Yükleniyor...</>
              ) : (
                <><Upload className="w-4 h-4 mr-2" /> Döküman Ekle</>
              )}
            </Button>
          </label>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-xl flex items-center gap-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <p className="text-sm font-medium">{error}</p>
        </div>
      )}

      <Card className="flex-1 shadow-sm border-slate-200 overflow-hidden flex flex-col">
        <CardHeader className="bg-slate-50 border-b border-slate-100 pb-4">
          <CardTitle className="text-lg">Yüklü Dökümanlar</CardTitle>
          <CardDescription>
            Chatbot, buradaki dökümanları kullanarak misafir sorularına yanıt verir.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0 overflow-y-auto flex-1">
          {loading && !uploading ? (
            <div className="flex flex-col items-center justify-center p-12 h-64 text-slate-500">
              <Loader2 className="w-8 h-8 animate-spin mb-4 text-indigo-500" />
              Yükleniyor...
            </div>
          ) : documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-12 h-64 text-slate-500 text-center">
              <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
                <FileText className="w-8 h-8 text-slate-400" />
              </div>
              <h3 className="text-lg font-semibold text-slate-700 mb-1">Döküman Bulunamadı</h3>
              <p className="text-sm max-w-md">
                Henüz yapay zekaya öğretilmiş bir döküman yok. Sağ üstteki "Döküman Ekle" butonunu kullanarak PDF veya metin dosyaları yükleyebilirsiniz.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {documents.map((doc, idx) => (
                <li key={idx} className="p-4 hover:bg-slate-50 transition-colors flex items-center justify-between group">
                  <div className="flex items-center gap-4">
                    <div className="p-3 bg-indigo-50 text-indigo-600 rounded-xl">
                      <FileText className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-slate-800">{doc.source}</h4>
                      <div className="flex items-center gap-2 mt-1 text-xs font-medium text-slate-500">
                        <span className="uppercase bg-slate-100 px-2 py-0.5 rounded">{doc.type}</span>
                        <span>•</span>
                        <span>{doc.chunks} vektör parçası</span>
                      </div>
                    </div>
                  </div>
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    className="text-red-500 hover:text-red-700 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => handleDelete(doc.source)}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default AIKnowledgeBase;
