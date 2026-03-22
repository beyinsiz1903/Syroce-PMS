"""Real ML Model Training Module
- Dynamic Pricing Model (trained on hotel data)
- No-Show Prediction Model
- Upsell Propensity Scoring
- NLP Sentiment Analysis
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from datetime import datetime, timezone
import numpy as np

router = APIRouter(prefix="/api/ml", tags=["ML/AI Models"])

# ============= ML Model Implementations =============

class PricingModel:
    """Dynamic pricing model trained on hotel booking data"""
    def __init__(self):
        self.is_trained = False
        self.model = None
        self.metrics = {}
    
    def train(self, data: list):
        """Train pricing model on historical booking data"""
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import LabelEncoder
        from sklearn.metrics import mean_absolute_error, r2_score
        
        if len(data) < 10:
            return {"error": "Yeterli veri yok (minimum 10 kayit)", "trained": False}
        
        le_room = LabelEncoder()
        le_channel = LabelEncoder()
        LabelEncoder()
        
        features = []
        targets = []
        
        for d in data:
            try:
                rate = float(d.get("rate", d.get("total_amount", 0)))
                if rate <= 0:
                    continue
                
                room_type = le_room.fit_transform([d.get("room_type", "Standard")])[0] if d.get("room_type") else 0
                channel = le_channel.fit_transform([d.get("channel", "direct")])[0] if d.get("channel") else 0
                
                # Extract date features
                check_in = d.get("check_in", "")
                if check_in:
                    try:
                        dt = datetime.fromisoformat(str(check_in).replace('Z', '+00:00'))
                        day_of_week = dt.weekday()
                        month = dt.month
                        is_weekend = 1 if day_of_week >= 5 else 0
                    except (ValueError, TypeError):
                        day_of_week = 0
                        month = 1
                        is_weekend = 0
                else:
                    day_of_week = 0
                    month = 1
                    is_weekend = 0
                
                features.append([room_type, channel, day_of_week, month, is_weekend])
                targets.append(rate)
            except (ValueError, TypeError):
                continue
        
        if len(features) < 10:
            return {"error": "Yeterli gecerli veri yok", "trained": False}
        
        X = np.array(features)
        y = np.array(targets)
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        self.model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
        self.model.fit(X_train, y_train)
        
        predictions = self.model.predict(X_test)
        self.metrics = {
            "mae": round(float(mean_absolute_error(y_test, predictions)), 2),
            "r2_score": round(float(r2_score(y_test, predictions)), 4),
            "training_samples": len(X_train),
            "test_samples": len(X_test),
            "feature_importance": {
                "room_type": round(float(self.model.feature_importances_[0]), 4),
                "channel": round(float(self.model.feature_importances_[1]), 4),
                "day_of_week": round(float(self.model.feature_importances_[2]), 4),
                "month": round(float(self.model.feature_importances_[3]), 4),
                "is_weekend": round(float(self.model.feature_importances_[4]), 4)
            }
        }
        self.is_trained = True
        return {"trained": True, "metrics": self.metrics}
    
    def predict(self, room_type: int = 0, channel: int = 0, day_of_week: int = 0, month: int = 1, is_weekend: int = 0):
        if not self.is_trained or self.model is None:
            return None
        features = np.array([[room_type, channel, day_of_week, month, is_weekend]])
        return float(self.model.predict(features)[0])


class NoShowModel:
    """No-show prediction model"""
    def __init__(self):
        self.is_trained = False
        self.model = None
        self.metrics = {}
    
    def train(self, data: list):
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
        
        if len(data) < 20:
            return {"error": "Yeterli veri yok (minimum 20 kayit)", "trained": False}
        
        features = []
        targets = []
        
        for d in data:
            try:
                is_noshow = 1 if d.get("status") in ["no_show", "noshow", "cancelled"] else 0
                
                lead_days = 0
                if d.get("created_at") and d.get("check_in"):
                    try:
                        created = datetime.fromisoformat(str(d["created_at"]).replace('Z', '+00:00'))
                        checkin = datetime.fromisoformat(str(d["check_in"]).replace('Z', '+00:00'))
                        lead_days = (checkin - created).days
                    except (ValueError, TypeError):
                        pass
                
                channel_code = hash(d.get("channel", "direct")) % 10
                room_type_code = hash(d.get("room_type", "Standard")) % 10
                nights = d.get("nights", 1)
                total_amount = float(d.get("total_amount", d.get("rate", 0)))
                
                features.append([lead_days, channel_code, room_type_code, nights, total_amount])
                targets.append(is_noshow)
            except (ValueError, TypeError):
                continue
        
        if len(features) < 20:
            return {"error": "Yeterli gecerli veri yok", "trained": False}
        
        X = np.array(features)
        y = np.array(targets)
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        self.model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        self.model.fit(X_train, y_train)
        
        predictions = self.model.predict(X_test)
        self.metrics = {
            "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
            "precision": round(float(precision_score(y_test, predictions, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, predictions, zero_division=0)), 4),
            "f1_score": round(float(f1_score(y_test, predictions, zero_division=0)), 4),
            "training_samples": len(X_train),
            "test_samples": len(X_test)
        }
        self.is_trained = True
        return {"trained": True, "metrics": self.metrics}
    
    def predict(self, lead_days=0, channel_code=0, room_type_code=0, nights=1, total_amount=100):
        if not self.is_trained or self.model is None:
            return None
        features = np.array([[lead_days, channel_code, room_type_code, nights, total_amount]])
        proba = self.model.predict_proba(features)[0]
        return {"no_show_probability": round(float(proba[1]) if len(proba) > 1 else 0.0, 4)}


class UpsellModel:
    """Upsell propensity scoring model"""
    def __init__(self):
        self.is_trained = False
        self.model = None
        self.metrics = {}
    
    def train(self, data: list):
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, roc_auc_score
        
        if len(data) < 20:
            return {"error": "Yeterli veri yok", "trained": False}
        
        features = []
        targets = []
        
        for d in data:
            try:
                has_upgrade = 1 if d.get("room_upgrade") or d.get("upsell_accepted") else 0
                
                total_amount = float(d.get("total_amount", d.get("rate", 0)))
                nights = d.get("nights", 1)
                is_returning = 1 if d.get("is_returning_guest") else 0
                channel_code = hash(d.get("channel", "direct")) % 10
                room_type_code = hash(d.get("room_type", "Standard")) % 10
                
                features.append([total_amount, nights, is_returning, channel_code, room_type_code])
                targets.append(has_upgrade)
            except (ValueError, TypeError):
                continue
        
        if len(features) < 20:
            return {"error": "Yeterli gecerli veri yok", "trained": False}
        
        X = np.array(features)
        y = np.array(targets)
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        self.model = GradientBoostingClassifier(n_estimators=100, max_depth=5, random_state=42)
        self.model.fit(X_train, y_train)
        
        predictions = self.model.predict(X_test)
        self.metrics = {
            "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
            "training_samples": len(X_train),
            "test_samples": len(X_test)
        }
        try:
            proba = self.model.predict_proba(X_test)[:, 1]
            self.metrics["auc_roc"] = round(float(roc_auc_score(y_test, proba)), 4)
        except (ValueError, IndexError):
            self.metrics["auc_roc"] = 0.0
        
        self.is_trained = True
        return {"trained": True, "metrics": self.metrics}
    
    def predict(self, total_amount=100, nights=1, is_returning=0, channel_code=0, room_type_code=0):
        if not self.is_trained or self.model is None:
            return None
        features = np.array([[total_amount, nights, is_returning, channel_code, room_type_code]])
        proba = self.model.predict_proba(features)[0]
        return {"upsell_propensity": round(float(proba[1]) if len(proba) > 1 else 0.0, 4)}


class SentimentAnalyzer:
    """NLP Sentiment Analysis for guest reviews"""
    def __init__(self):
        self.is_ready = True
    
    def analyze(self, text: str) -> dict:
        from textblob import TextBlob
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity
        
        if polarity > 0.3:
            sentiment = "positive"
        elif polarity < -0.3:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        return {
            "text": text[:200],
            "sentiment": sentiment,
            "polarity": round(polarity, 4),
            "subjectivity": round(subjectivity, 4),
            "confidence": round(abs(polarity), 4)
        }
    
    def batch_analyze(self, texts: list) -> dict:
        results = [self.analyze(t) for t in texts if t]
        if not results:
            return {"results": [], "summary": {}}
        
        positive = sum(1 for r in results if r["sentiment"] == "positive")
        negative = sum(1 for r in results if r["sentiment"] == "negative")
        neutral = sum(1 for r in results if r["sentiment"] == "neutral")
        avg_polarity = sum(r["polarity"] for r in results) / len(results)
        
        return {
            "results": results,
            "summary": {
                "total": len(results),
                "positive": positive,
                "negative": negative,
                "neutral": neutral,
                "average_polarity": round(avg_polarity, 4),
                "positive_rate": round(positive / len(results) * 100, 1)
            }
        }

# Global model instances
pricing_model = PricingModel()
noshow_model = NoShowModel()
upsell_model = UpsellModel()
sentiment_analyzer = SentimentAnalyzer()

# ============= ENDPOINTS =============
def create_ml_routes(db, get_current_user):
    """Create ML model routes"""
    
    # --- PRICING MODEL ---
    @router.post("/pricing/train")
    async def train_pricing_model(current_user=Depends(get_current_user)):
        """Train dynamic pricing model on hotel's booking data"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        bookings = await db.bookings.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0}
        ).to_list(5000)
        
        result = pricing_model.train(bookings)
        
        # Save model metadata
        await db.ml_models.update_one(
            {"tenant_id": current_user.tenant_id, "model_type": "pricing"},
            {"$set": {
                "tenant_id": current_user.tenant_id,
                "model_type": "pricing",
                "is_trained": result.get("trained", False),
                "metrics": result.get("metrics", {}),
                "training_data_count": len(bookings),
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "trained_by": current_user.id
            }},
            upsert=True
        )
        
        return result
    
    @router.post("/pricing/predict")
    async def predict_price(
        room_type: str = "Standard",
        channel: str = "direct",
        check_in_date: Optional[str] = None,
        current_user=Depends(get_current_user)
    ):
        """Predict optimal price"""
        if not pricing_model.is_trained:
            raise HTTPException(status_code=400, detail="Model henuz egitilmedi. Once /train endpoint'ini kullanin.")
        
        day_of_week = 0
        month = datetime.now().month
        is_weekend = 0
        
        if check_in_date:
            try:
                dt = datetime.fromisoformat(check_in_date)
                day_of_week = dt.weekday()
                month = dt.month
                is_weekend = 1 if day_of_week >= 5 else 0
            except (ValueError, TypeError):
                pass
        
        predicted_price = pricing_model.predict(
            room_type=hash(room_type) % 10,
            channel=hash(channel) % 10,
            day_of_week=day_of_week,
            month=month,
            is_weekend=is_weekend
        )
        
        return {
            "predicted_price": round(predicted_price, 2) if predicted_price else 0,
            "room_type": room_type,
            "channel": channel,
            "model_metrics": pricing_model.metrics
        }
    
    # --- NO-SHOW PREDICTION ---
    @router.post("/noshow/train")
    async def train_noshow_model(current_user=Depends(get_current_user)):
        """Train no-show prediction model"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        bookings = await db.bookings.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0}
        ).to_list(5000)
        
        result = noshow_model.train(bookings)
        
        await db.ml_models.update_one(
            {"tenant_id": current_user.tenant_id, "model_type": "noshow"},
            {"$set": {
                "tenant_id": current_user.tenant_id,
                "model_type": "noshow",
                "is_trained": result.get("trained", False),
                "metrics": result.get("metrics", {}),
                "trained_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        
        return result
    
    @router.post("/noshow/predict")
    async def predict_noshow(
        booking_id: Optional[str] = None,
        lead_days: int = 7,
        channel: str = "direct",
        room_type: str = "Standard",
        nights: int = 1,
        total_amount: float = 100,
        current_user=Depends(get_current_user)
    ):
        """Predict no-show probability"""
        if not noshow_model.is_trained:
            raise HTTPException(status_code=400, detail="Model henuz egitilmedi")
        
        result = noshow_model.predict(
            lead_days=lead_days,
            channel_code=hash(channel) % 10,
            room_type_code=hash(room_type) % 10,
            nights=nights,
            total_amount=total_amount
        )
        
        # Risk level
        prob = result["no_show_probability"]
        risk = "low" if prob < 0.3 else "medium" if prob < 0.6 else "high"
        
        return {
            **result,
            "risk_level": risk,
            "recommendation": {
                "low": "Normal islem",
                "medium": "Garanti odemesi isteyin",
                "high": "On odeme veya kredi karti garantisi zorunlu"
            }.get(risk, ""),
            "model_metrics": noshow_model.metrics
        }
    
    # --- UPSELL PROPENSITY ---
    @router.post("/upsell/train")
    async def train_upsell_model(current_user=Depends(get_current_user)):
        """Train upsell propensity model"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        bookings = await db.bookings.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0}
        ).to_list(5000)
        
        result = upsell_model.train(bookings)
        
        await db.ml_models.update_one(
            {"tenant_id": current_user.tenant_id, "model_type": "upsell"},
            {"$set": {
                "tenant_id": current_user.tenant_id,
                "model_type": "upsell",
                "is_trained": result.get("trained", False),
                "metrics": result.get("metrics", {}),
                "trained_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        
        return result
    
    @router.post("/upsell/score")
    async def score_upsell(
        guest_id: Optional[str] = None,
        total_amount: float = 100,
        nights: int = 1,
        is_returning: bool = False,
        channel: str = "direct",
        room_type: str = "Standard",
        current_user=Depends(get_current_user)
    ):
        """Score upsell propensity for a guest"""
        if not upsell_model.is_trained:
            raise HTTPException(status_code=400, detail="Model henuz egitilmedi")
        
        result = upsell_model.predict(
            total_amount=total_amount,
            nights=nights,
            is_returning=1 if is_returning else 0,
            channel_code=hash(channel) % 10,
            room_type_code=hash(room_type) % 10
        )
        
        propensity = result["upsell_propensity"]
        
        # Generate upsell recommendations based on propensity
        recommendations = []
        if propensity > 0.5:
            recommendations = [
                {"type": "room_upgrade", "description": "Oda yukseltme teklifi", "priority": "high"},
                {"type": "late_checkout", "description": "Gec cikis", "priority": "medium"},
                {"type": "breakfast_package", "description": "Kahvalti paketi", "priority": "medium"}
            ]
        elif propensity > 0.3:
            recommendations = [
                {"type": "breakfast_package", "description": "Kahvalti paketi", "priority": "medium"},
                {"type": "spa_discount", "description": "Spa indirimi", "priority": "low"}
            ]
        
        return {
            **result,
            "recommendations": recommendations,
            "model_metrics": upsell_model.metrics
        }
    
    # --- SENTIMENT ANALYSIS ---
    @router.post("/sentiment/analyze")
    async def analyze_sentiment(
        text: str = "",
        texts: List[str] = [],
        current_user=Depends(get_current_user)
    ):
        """Analyze sentiment of guest reviews/feedback"""
        if text:
            return sentiment_analyzer.analyze(text)
        elif texts:
            return sentiment_analyzer.batch_analyze(texts)
        else:
            raise HTTPException(status_code=400, detail="Metin veya metin listesi gerekli")
    
    @router.get("/sentiment/reviews")
    async def analyze_hotel_reviews(current_user=Depends(get_current_user)):
        """Analyze all hotel reviews"""
        reviews = await db.guest_reviews.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0}
        ).to_list(500)
        
        if not reviews:
            return {"message": "Analiz edilecek yorum bulunamadi", "results": [], "summary": {}}
        
        texts = [r.get("review_text", r.get("comment", "")) for r in reviews]
        analysis = sentiment_analyzer.batch_analyze(texts)
        
        return analysis
    
    # --- MODEL STATUS ---
    @router.get("/models/status")
    async def get_ml_models_status(current_user=Depends(get_current_user)):
        """Get status of all ML models"""
        models = await db.ml_models.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0}
        ).to_list(10)
        
        return {
            "models": {
                "pricing": {
                    "in_memory_trained": pricing_model.is_trained,
                    "db_record": next((m for m in models if m.get("model_type") == "pricing"), None)
                },
                "noshow": {
                    "in_memory_trained": noshow_model.is_trained,
                    "db_record": next((m for m in models if m.get("model_type") == "noshow"), None)
                },
                "upsell": {
                    "in_memory_trained": upsell_model.is_trained,
                    "db_record": next((m for m in models if m.get("model_type") == "upsell"), None)
                },
                "sentiment": {
                    "ready": sentiment_analyzer.is_ready,
                    "type": "TextBlob NLP"
                }
            },
            "tenant_id": current_user.tenant_id
        }
    
    return router
