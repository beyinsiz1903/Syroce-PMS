"""
ML Model Trainers for Hotel PMS
Train and save ML models for production use
"""

import json
import os
from datetime import datetime

import joblib
import numpy as np
import xgboost as xgb
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, classification_report, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder


class RMSModelTrainer:
    """
    Revenue Management System Model Trainer
    Trains models for occupancy prediction and dynamic pricing
    """

    def __init__(self, model_dir='ml_models'):
        self.model_dir = model_dir
        self.occupancy_model = None
        self.pricing_model = None
        self.metrics = {}

    def train(self, data_df):
        """
        Train RMS models

        Args:
            data_df: DataFrame with RMS training data

        Returns:
            dict: Training metrics and model info
        """

        # Prepare features for occupancy prediction
        occupancy_features = [
            'day_of_week', 'month', 'season', 'is_weekend', 'is_holiday',
            'days_until_event', 'competitor_avg_rate', 'competitor_occupancy',
            'historical_occupancy_7d', 'historical_occupancy_30d', 'lead_time_bookings',
            'current_price'
        ]

        X_occupancy = data_df[occupancy_features]
        y_occupancy = data_df['occupancy_rate']

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X_occupancy, y_occupancy, test_size=0.2, random_state=42
        )

        # Train occupancy prediction model (XGBoost)
        print("Training occupancy prediction model...")
        self.occupancy_model = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=8,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42
        )

        self.occupancy_model.fit(X_train, y_train)

        # Evaluate occupancy model
        y_pred = self.occupancy_model.predict(X_test)

        occupancy_metrics = {
            'rmse': float(np.sqrt(mean_squared_error(y_test, y_pred))),
            'mae': float(mean_absolute_error(y_test, y_pred)),
            'r2_score': float(r2_score(y_test, y_pred)),
            'mean_error_percentage': float(np.mean(np.abs((y_test - y_pred) / y_test)) * 100)
        }

        print(f"Occupancy Model - RMSE: {occupancy_metrics['rmse']:.4f}, R²: {occupancy_metrics['r2_score']:.4f}")

        # Train dynamic pricing model
        print("Training dynamic pricing model...")

        pricing_features = [
            'day_of_week', 'month', 'season', 'is_weekend', 'is_holiday',
            'days_until_event', 'competitor_avg_rate', 'occupancy_rate',
            'historical_occupancy_7d', 'historical_occupancy_30d'
        ]

        X_pricing = data_df[pricing_features]
        y_pricing = data_df['optimal_price']

        X_train_p, X_test_p, y_train_p, y_test_p = train_test_split(
            X_pricing, y_pricing, test_size=0.2, random_state=42
        )

        self.pricing_model = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=8,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42
        )

        self.pricing_model.fit(X_train_p, y_train_p)

        # Evaluate pricing model
        y_pred_p = self.pricing_model.predict(X_test_p)

        pricing_metrics = {
            'rmse': float(np.sqrt(mean_squared_error(y_test_p, y_pred_p))),
            'mae': float(mean_absolute_error(y_test_p, y_pred_p)),
            'r2_score': float(r2_score(y_test_p, y_pred_p)),
            'mean_error_percentage': float(np.mean(np.abs((y_test_p - y_pred_p) / y_test_p)) * 100)
        }

        print(f"Pricing Model - RMSE: {pricing_metrics['rmse']:.2f}, R²: {pricing_metrics['r2_score']:.4f}")

        # Save models
        self.save_models()

        # Store metrics
        self.metrics = {
            'occupancy_model': occupancy_metrics,
            'pricing_model': pricing_metrics,
            'training_samples': len(data_df),
            'features': {
                'occupancy': occupancy_features,
                'pricing': pricing_features
            },
            'trained_at': datetime.now().isoformat(),
            'model_version': '1.0'
        }

        # Save metrics
        with open(os.path.join(self.model_dir, 'rms_metrics.json'), 'w') as f:
            json.dump(self.metrics, f, indent=2)

        return self.metrics

    def save_models(self):
        """Save trained models to disk"""
        os.makedirs(self.model_dir, exist_ok=True)

        joblib.dump(self.occupancy_model, os.path.join(self.model_dir, 'rms_occupancy_model.pkl'))
        joblib.dump(self.pricing_model, os.path.join(self.model_dir, 'rms_pricing_model.pkl'))

        print(f"Models saved to {self.model_dir}/")

    def load_models(self):
        """Load trained models from disk"""
        self.occupancy_model = joblib.load(os.path.join(self.model_dir, 'rms_occupancy_model.pkl'))
        self.pricing_model = joblib.load(os.path.join(self.model_dir, 'rms_pricing_model.pkl'))

        with open(os.path.join(self.model_dir, 'rms_metrics.json'), 'r') as f:
            self.metrics = json.load(f)

        print("Models loaded successfully")
        return self.metrics


class PersonaModelTrainer:
    """
    Guest Persona Model Trainer
    Trains classification model for guest segmentation
    """

    def __init__(self, model_dir='ml_models'):
        self.model_dir = model_dir
        self.model = None
        self.label_encoder = LabelEncoder()
        self.metrics = {}

    def train(self, data_df):
        """
        Train persona classification model

        Args:
            data_df: DataFrame with guest persona training data

        Returns:
            dict: Training metrics and model info
        """

        # Prepare features
        features = [
            'total_stays', 'avg_spend', 'total_spent', 'avg_lead_time',
            'ota_bookings', 'direct_bookings', 'upsells_accepted',
            'negative_reviews', 'positive_reviews', 'days_since_last_visit',
            'booking_frequency'
        ]

        X = data_df[features]
        y = data_df['persona_type']

        # Encode labels
        y_encoded = self.label_encoder.fit_transform(y)

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
        )

        # Train Random Forest Classifier
        print("Training guest persona classification model...")
        self.model = RandomForestClassifier(
            n_estimators=200,
            max_depth=15,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            class_weight='balanced'
        )

        self.model.fit(X_train, y_train)

        # Evaluate
        y_pred = self.model.predict(X_test)

        accuracy = accuracy_score(y_test, y_pred)

        # Get classification report
        report = classification_report(
            y_test, y_pred,
            target_names=self.label_encoder.classes_,
            output_dict=True,
            zero_division=0
        )

        print(f"Persona Model - Accuracy: {accuracy:.4f}")
        print("\nClassification Report:")
        for persona, metrics in report.items():
            if isinstance(metrics, dict):
                print(f"  {persona}: Precision={metrics.get('precision', 0):.3f}, Recall={metrics.get('recall', 0):.3f}, F1={metrics.get('f1-score', 0):.3f}")

        # Feature importance
        feature_importance = dict(zip(features, self.model.feature_importances_))
        feature_importance = {k: float(v) for k, v in sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)}

        # Save models
        self.save_models()

        # Store metrics
        self.metrics = {
            'accuracy': float(accuracy),
            'classification_report': report,
            'feature_importance': feature_importance,
            'training_samples': len(data_df),
            'features': features,
            'persona_types': list(self.label_encoder.classes_),
            'trained_at': datetime.now().isoformat(),
            'model_version': '1.0'
        }

        # Save metrics
        with open(os.path.join(self.model_dir, 'persona_metrics.json'), 'w') as f:
            json.dump(self.metrics, f, indent=2)

        return self.metrics

    def save_models(self):
        """Save trained models to disk"""
        os.makedirs(self.model_dir, exist_ok=True)

        joblib.dump(self.model, os.path.join(self.model_dir, 'persona_model.pkl'))
        joblib.dump(self.label_encoder, os.path.join(self.model_dir, 'persona_label_encoder.pkl'))

        print(f"Models saved to {self.model_dir}/")

    def load_models(self):
        """Load trained models from disk"""
        self.model = joblib.load(os.path.join(self.model_dir, 'persona_model.pkl'))
        self.label_encoder = joblib.load(os.path.join(self.model_dir, 'persona_label_encoder.pkl'))

        with open(os.path.join(self.model_dir, 'persona_metrics.json'), 'r') as f:
            self.metrics = json.load(f)

        print("Models loaded successfully")
        return self.metrics


class PredictiveMaintenanceModelTrainer:
    """
    Predictive Maintenance Model Trainer
    Trains classification model for equipment failure prediction
    """

    def __init__(self, model_dir='ml_models'):
        self.model_dir = model_dir
        self.risk_model = None
        self.days_model = None
        self.label_encoder = LabelEncoder()
        self.equipment_encoder = LabelEncoder()
        self.metrics = {}

    def train(self, data_df):
        """
        Train predictive maintenance models

        Args:
            data_df: DataFrame with predictive maintenance training data

        Returns:
            dict: Training metrics and model info
        """

        # Encode equipment type
        data_df['equipment_type_encoded'] = self.equipment_encoder.fit_transform(data_df['equipment_type'])

        # Prepare features
        features = [
            'equipment_type_encoded', 'temperature', 'vibration_level',
            'error_count_24h', 'usage_hours', 'days_since_maintenance',
            'humidity', 'pressure', 'age_years'
        ]

        X = data_df[features]

        # Train failure risk classifier
        print("Training failure risk classification model...")

        y_risk = self.label_encoder.fit_transform(data_df['failure_risk'])

        X_train, X_test, y_train, y_test = train_test_split(
            X, y_risk, test_size=0.2, random_state=42, stratify=y_risk
        )

        self.risk_model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=8,
            learning_rate=0.05,
            random_state=42
        )

        self.risk_model.fit(X_train, y_train)

        # Evaluate risk model
        y_pred = self.risk_model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)

        report = classification_report(
            y_test, y_pred,
            target_names=self.label_encoder.classes_,
            output_dict=True,
            zero_division=0
        )

        print(f"Risk Model - Accuracy: {accuracy:.4f}")

        # Train days until failure regressor
        print("Training days-until-failure prediction model...")

        y_days = data_df['days_until_failure']

        X_train_d, X_test_d, y_train_d, y_test_d = train_test_split(
            X, y_days, test_size=0.2, random_state=42
        )

        self.days_model = GradientBoostingRegressor(
            n_estimators=200,
            max_depth=8,
            learning_rate=0.05,
            random_state=42
        )

        self.days_model.fit(X_train_d, y_train_d)

        # Evaluate days model
        y_pred_d = self.days_model.predict(X_test_d)

        days_metrics = {
            'rmse': float(np.sqrt(mean_squared_error(y_test_d, y_pred_d))),
            'mae': float(mean_absolute_error(y_test_d, y_pred_d)),
            'r2_score': float(r2_score(y_test_d, y_pred_d))
        }

        print(f"Days Model - RMSE: {days_metrics['rmse']:.2f} days, R²: {days_metrics['r2_score']:.4f}")

        # Feature importance
        feature_importance = dict(zip(features, self.risk_model.feature_importances_))
        feature_importance = {k: float(v) for k, v in sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)}

        # Save models
        self.save_models()

        # Store metrics
        self.metrics = {
            'risk_model': {
                'accuracy': float(accuracy),
                'classification_report': report
            },
            'days_model': days_metrics,
            'feature_importance': feature_importance,
            'training_samples': len(data_df),
            'features': features,
            'risk_levels': list(self.label_encoder.classes_),
            'equipment_types': list(self.equipment_encoder.classes_),
            'trained_at': datetime.now().isoformat(),
            'model_version': '1.0'
        }

        # Save metrics
        with open(os.path.join(self.model_dir, 'maintenance_metrics.json'), 'w') as f:
            json.dump(self.metrics, f, indent=2)

        return self.metrics

    def save_models(self):
        """Save trained models to disk"""
        os.makedirs(self.model_dir, exist_ok=True)

        joblib.dump(self.risk_model, os.path.join(self.model_dir, 'maintenance_risk_model.pkl'))
        joblib.dump(self.days_model, os.path.join(self.model_dir, 'maintenance_days_model.pkl'))
        joblib.dump(self.label_encoder, os.path.join(self.model_dir, 'maintenance_label_encoder.pkl'))
        joblib.dump(self.equipment_encoder, os.path.join(self.model_dir, 'maintenance_equipment_encoder.pkl'))

        print(f"Models saved to {self.model_dir}/")

    def load_models(self):
        """Load trained models from disk"""
        self.risk_model = joblib.load(os.path.join(self.model_dir, 'maintenance_risk_model.pkl'))
        self.days_model = joblib.load(os.path.join(self.model_dir, 'maintenance_days_model.pkl'))
        self.label_encoder = joblib.load(os.path.join(self.model_dir, 'maintenance_label_encoder.pkl'))
        self.equipment_encoder = joblib.load(os.path.join(self.model_dir, 'maintenance_equipment_encoder.pkl'))

        with open(os.path.join(self.model_dir, 'maintenance_metrics.json'), 'r') as f:
            self.metrics = json.load(f)

        print("Models loaded successfully")
        return self.metrics


class HKSchedulerModelTrainer:
    """
    Housekeeping Scheduler Model Trainer
    Trains regression models for staffing optimization
    """

    def __init__(self, model_dir='ml_models'):
        self.model_dir = model_dir
        self.staff_model = None
        self.hours_model = None
        self.metrics = {}

    def train(self, data_df):
        """
        Train HK scheduler models

        Args:
            data_df: DataFrame with HK scheduler training data

        Returns:
            dict: Training metrics and model info
        """

        # Prepare features
        features = [
            'day_of_week', 'is_weekend', 'season', 'total_rooms',
            'occupied_rooms', 'checkout_rooms', 'stayover_rooms',
            'vip_rooms', 'occupancy_rate', 'avg_room_type_points'
        ]

        X = data_df[features]

        # Train staff prediction model
        print("Training staff requirements prediction model...")

        y_staff = data_df['staff_needed']

        X_train, X_test, y_train, y_test = train_test_split(
            X, y_staff, test_size=0.2, random_state=42
        )

        self.staff_model = RandomForestRegressor(
            n_estimators=200,
            max_depth=15,
            min_samples_split=5,
            random_state=42
        )

        self.staff_model.fit(X_train, y_train)

        # Evaluate staff model
        y_pred = self.staff_model.predict(X_test)

        staff_metrics = {
            'rmse': float(np.sqrt(mean_squared_error(y_test, y_pred))),
            'mae': float(mean_absolute_error(y_test, y_pred)),
            'r2_score': float(r2_score(y_test, y_pred)),
            'mean_error_percentage': float(np.mean(np.abs((y_test - y_pred) / y_test)) * 100)
        }

        print(f"Staff Model - RMSE: {staff_metrics['rmse']:.2f} staff, R²: {staff_metrics['r2_score']:.4f}")

        # Train hours prediction model
        print("Training hours estimation model...")

        y_hours = data_df['estimated_hours']

        X_train_h, X_test_h, y_train_h, y_test_h = train_test_split(
            X, y_hours, test_size=0.2, random_state=42
        )

        self.hours_model = RandomForestRegressor(
            n_estimators=200,
            max_depth=15,
            min_samples_split=5,
            random_state=42
        )

        self.hours_model.fit(X_train_h, y_train_h)

        # Evaluate hours model
        y_pred_h = self.hours_model.predict(X_test_h)

        hours_metrics = {
            'rmse': float(np.sqrt(mean_squared_error(y_test_h, y_pred_h))),
            'mae': float(mean_absolute_error(y_test_h, y_pred_h)),
            'r2_score': float(r2_score(y_test_h, y_pred_h)),
            'mean_error_percentage': float(np.mean(np.abs((y_test_h - y_pred_h) / y_test_h)) * 100)
        }

        print(f"Hours Model - RMSE: {hours_metrics['rmse']:.2f} hours, R²: {hours_metrics['r2_score']:.4f}")

        # Feature importance
        feature_importance = dict(zip(features, self.staff_model.feature_importances_))
        feature_importance = {k: float(v) for k, v in sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)}

        # Save models
        self.save_models()

        # Store metrics
        self.metrics = {
            'staff_model': staff_metrics,
            'hours_model': hours_metrics,
            'feature_importance': feature_importance,
            'training_samples': len(data_df),
            'features': features,
            'trained_at': datetime.now().isoformat(),
            'model_version': '1.0'
        }

        # Save metrics
        with open(os.path.join(self.model_dir, 'hk_scheduler_metrics.json'), 'w') as f:
            json.dump(self.metrics, f, indent=2)

        return self.metrics

    def save_models(self):
        """Save trained models to disk"""
        os.makedirs(self.model_dir, exist_ok=True)

        joblib.dump(self.staff_model, os.path.join(self.model_dir, 'hk_staff_model.pkl'))
        joblib.dump(self.hours_model, os.path.join(self.model_dir, 'hk_hours_model.pkl'))

        print(f"Models saved to {self.model_dir}/")

    def load_models(self):
        """Load trained models from disk"""
        self.staff_model = joblib.load(os.path.join(self.model_dir, 'hk_staff_model.pkl'))
        self.hours_model = joblib.load(os.path.join(self.model_dir, 'hk_hours_model.pkl'))

        with open(os.path.join(self.model_dir, 'hk_scheduler_metrics.json'), 'r') as f:
            self.metrics = json.load(f)

        print("Models loaded successfully")
        return self.metrics
