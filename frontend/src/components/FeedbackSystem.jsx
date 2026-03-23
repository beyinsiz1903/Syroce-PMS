import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Star, MessageCircle, ThumbsUp, ThumbsDown } from 'lucide-react';

const FeedbackSystem = () => {
  const [reviews, setReviews] = useState([]);
  const [stats, setStats] = useState({ avgRating: 0, totalReviews: 0, satisfaction: 0 });

  useEffect(() => {
    loadReviews();
  }, []);

  const loadReviews = async () => {
    try {
      const response = await axios.get('/crm/reviews');
      setReviews(response.data.reviews || []);
      calculateStats(response.data.reviews || []);
    } catch (error) {
      console.error('Failed to load reviews:', error);
    }
  };

  const calculateStats = (reviewsList) => {
    if (reviewsList.length === 0) {
      setStats({ avgRating: 0, totalReviews: 0, satisfaction: 0 });
      return;
    }

    const avgRating = reviewsList.reduce((sum, r) => sum + r.rating, 0) / reviewsList.length;
    const satisfaction = (reviewsList.filter(r => r.rating >= 4).length / reviewsList.length) * 100;

    setStats({
      avgRating: avgRating.toFixed(1),
      totalReviews: reviewsList.length,
      satisfaction: satisfaction.toFixed(0)
    });
  };

  const renderStars = (rating) => {
    return Array.from({ length: 5 }, (_, i) => (
      <Star
        key={i}
        className={`w-4 h-4 ${
          i < rating ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300'
        }`}
      />
    ));
  };

  const respondToReview = async (reviewId) => {
    const response = prompt('Enter your response:');
    if (!response) return;

    try {
      await axios.post(`/crm/reviews/${reviewId}/respond`, { response });
      toast.success('Response sent');
      loadReviews();
    } catch (error) {
      toast.error('Failed to send response');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-2xl font-bold">Guest Feedback & Reviews</h3>
        <p className="text-gray-600">Monitor and respond to guest reviews</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-4xl font-bold text-yellow-500">{stats.avgRating}</div>
            <div className="text-sm text-gray-600 flex justify-center mt-2">
              {renderStars(Math.round(stats.avgRating))}
            </div>
            <div className="text-sm text-gray-500 mt-1">Average Rating</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-4xl font-bold text-blue-600">{stats.totalReviews}</div>
            <div className="text-sm text-gray-600 mt-2">Total Reviews</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-4xl font-bold text-green-600">{stats.satisfaction}%</div>
            <div className="text-sm text-gray-600 mt-2">Satisfaction Rate</div>
            <div className="text-xs text-gray-500">(4+ stars)</div>
          </CardContent>
        </Card>
      </div>

      {/* Reviews List */}
      <div className="space-y-4">
        {reviews.length === 0 ? (
          <Card>
            <CardContent className="text-center py-12">
              <MessageCircle className="w-16 h-16 mx-auto text-gray-400 mb-4" />
              <p className="text-gray-600">No reviews yet</p>
            </CardContent>
          </Card>
        ) : (
          reviews.map((review) => (
            <Card key={review.id} className="hover:shadow-lg transition">
              <CardHeader>
                <div className="flex justify-between items-start">
                  <div>
                    <CardTitle className="text-lg">{review.guest_name}</CardTitle>
                    <div className="flex gap-1 mt-1">{renderStars(review.rating)}</div>
                  </div>
                  <div className="text-xs text-gray-500">
                    {new Date(review.created_at).toLocaleDateString()}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-gray-700 mb-4">{review.comment}</p>
                {review.response ? (
                  <div className="bg-blue-50 p-3 rounded">
                    <div className="text-xs font-semibold text-blue-700 mb-1">Your Response:</div>
                    <p className="text-sm text-gray-700">{review.response}</p>
                  </div>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => respondToReview(review.id)}>
                    <MessageCircle className="w-4 h-4 mr-2" />
                    Respond
                  </Button>
                )}
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
};

export default FeedbackSystem;