import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Brain, ThumbsUp, ThumbsDown, AlertCircle, Sparkles, TrendingUp } from 'lucide-react';

/**
 * AI Sentiment Analysis for Guest Reviews
 * Automatically detects sentiment and categorizes issues
 * Demo wow factor: "Negative sentiment detected: cleanliness issue"
 */
const ReviewSentimentAnalysis = ({ reviewText = '', onAnalysisComplete }) => {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState(reviewText);

  const analyzeReview = async () => {
    if (!text.trim()) {
      toast.error('Please enter review text');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post('/reviews/ai-sentiment-analysis', {
        review_text: text
      });
      
      setAnalysis(response.data);
      toast.success('AI Analysis completed!');
      
      if (onAnalysisComplete) {
        onAnalysisComplete(response.data);
      }
    } catch (error) {
      toast.error('AI analysis failed');
      console.error('Sentiment analysis error:', error);
    } finally {
      setLoading(false);
    }
  };

  const getSentimentColor = (sentiment) => {
    switch (sentiment) {
      case 'positive': return 'green';
      case 'negative': return 'red';
      case 'neutral': return 'gray';
      default: return 'blue';
    }
  };

  const getSentimentIcon = (sentiment) => {
    switch (sentiment) {
      case 'positive': return <ThumbsUp className="w-5 h-5" />;
      case 'negative': return <ThumbsDown className="w-5 h-5" />;
      case 'neutral': return <AlertCircle className="w-5 h-5" />;
      default: return <Brain className="w-5 h-5" />;
    }
  };

  return (
    <Card className="border-2 border-blue-300">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="w-5 h-5 text-blue-600" />
          AI Sentiment Analysis
        </CardTitle>
        <CardDescription>
          Automatically detect sentiment and categorize guest feedback
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Input Section */}
        <div>
          <label className="text-sm font-semibold mb-2 block">Review Text:</label>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Enter guest review text for AI analysis..."
            rows={4}
            className="w-full"
          />
        </div>

        {/* Analyze Button */}
        <Button
          onClick={analyzeReview}
          disabled={loading || !text.trim()}
          className="w-full bg-blue-600 hover:bg-blue-700"
        >
          {loading ? (
            <>
              <Brain className="w-4 h-4 mr-2 animate-pulse" />
              Analyzing with AI...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4 mr-2" />
              Analyze with AI
            </>
          )}
        </Button>

        {/* Analysis Results */}
        {analysis && (
          <div className="space-y-4 mt-4 p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg border-2 border-blue-200">
            {/* Overall Sentiment */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`p-3 rounded-full bg-${getSentimentColor(analysis.sentiment)}-100`}>
                  {getSentimentIcon(analysis.sentiment)}
                </div>
                <div>
                  <div className="text-sm text-gray-600">Overall Sentiment</div>
                  <div className="text-xl font-bold capitalize text-gray-900">
                    {analysis.sentiment}
                  </div>
                </div>
              </div>
              <Badge className={`bg-${getSentimentColor(analysis.sentiment)}-500 text-lg px-4 py-2`}>
                {(analysis.confidence * 100).toFixed(0)}% Confidence
              </Badge>
            </div>

            {/* Key Issues Detected */}
            {analysis.issues && analysis.issues.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-orange-600" />
                  Issues Detected:
                </h4>
                <div className="space-y-2">
                  {analysis.issues.map((issue, idx) => (
                    <div key={idx} className="flex items-start gap-2 p-2 bg-white rounded border">
                      <span className={`text-${issue.severity === 'high' ? 'red' : issue.severity === 'medium' ? 'orange' : 'yellow'}-600 font-bold text-xs mt-0.5`}>
                        {issue.severity === 'high' ? '🔴' : issue.severity === 'medium' ? '🟠' : '🟡'}
                      </span>
                      <div className="flex-1">
                        <div className="font-semibold text-sm">{issue.category}</div>
                        <div className="text-xs text-gray-600">{issue.description}</div>
                      </div>
                      <Badge className={`bg-${issue.severity === 'high' ? 'red' : issue.severity === 'medium' ? 'orange' : 'yellow'}-500 text-xs`}>
                        {issue.severity}
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Positive Highlights */}
            {analysis.highlights && analysis.highlights.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                  <ThumbsUp className="w-4 h-4 text-green-600" />
                  Positive Highlights:
                </h4>
                <div className="space-y-2">
                  {analysis.highlights.map((highlight, idx) => (
                    <div key={idx} className="flex items-center gap-2 p-2 bg-green-50 rounded border border-green-200">
                      <span className="text-green-600">✓</span>
                      <div className="flex-1">
                        <div className="font-semibold text-sm text-green-900">{highlight.category}</div>
                        <div className="text-xs text-green-700">{highlight.description}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Action Recommendations */}
            {analysis.recommendations && analysis.recommendations.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-blue-600" />
                  AI Recommendations:
                </h4>
                <ul className="space-y-1">
                  {analysis.recommendations.map((rec, idx) => (
                    <li key={idx} className="text-sm text-gray-700 flex items-start gap-2">
                      <span className="text-blue-600 font-bold">→</span>
                      {rec}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Demo Examples */}
            <div className="mt-4 p-3 bg-purple-100 border-l-4 border-purple-500 rounded text-xs">
              <strong>Example AI Insights:</strong>
              <ul className="list-disc list-inside mt-1 space-y-0.5 text-purple-900">
                <li>"Negative sentiment detected: cleanliness issue"</li>
                <li>"Positive sentiment: staff friendliness"</li>
                <li>"High priority: Room maintenance required"</li>
              </ul>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default ReviewSentimentAnalysis;
