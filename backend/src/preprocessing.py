import pandas as pd
import numpy as np
import pickle
import os
import warnings
from datetime import datetime
from collections import Counter
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler, LabelEncoder
from imblearn.over_sampling import SMOTE

warnings.filterwarnings('ignore')


class PreprocessingFraud:
    def __init__(self, 
                 data_filename='fraud_600k.csv',
                 test_size=0.2,
                 random_state=42):
        
        # Racine du dépôt : backend/src/preprocessing.py -> trois dirname()
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_path = os.path.join(self.base_dir, 'data', 'raws', data_filename)
        # PROCESSORS_DIR (Docker, Kubernetes) prime sur l'emplacement par défaut du dépôt
        self.processor_dir = os.getenv(
            'PROCESSORS_DIR', os.path.join(self.base_dir, 'artifacts', 'preprocessing'))
        
        self.test_size = test_size
        self.random_state = random_state
        
        # Données
        self.df_raw = None
        self.df_clean = None
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        self.X_train_processed = None
        self.X_test_processed = None
        self.y_train_processed = None
        
        # Processeurs
        self.scaler = RobustScaler()
        self.label_encoders = {}
        self.feature_names = {
            'categorical_features': [],
            'numerical_features': [],
            'all_features': []
        }
        self.smote_config = {'applied': False}
        
        # Colonnes
        self.cols_to_drop = [
            'Unnamed: 0', 'trans_date_trans_time', 'cc_num', 'merchant',
            'first', 'last', 'street', 'trans_num', 'dob', 'unix_time', 'city'
        ]
        self.categorical_features = [
            'category', 'gender', 'state', 'job', 'amt_category', 'day_period'
        ]
        self.target = 'is_fraud'
        
        # Stats
        self.stats = {}
        
        print(f"{'='*70}")
        print(f"INITIALISATION - PreprocessingFraud")
        print(f"{'='*70}")
        print(f"  📁 Base directory: {self.base_dir}")
        print(f"  📁 Données: {self.data_path}")
        print(f"  📦 Processeurs: {self.processor_dir}")
        print(f"  🎲 Random state: {random_state}")
        print(f"  📊 Test size: {test_size*100:.0f}%")
        
        # Vérifier que les chemins existent
        if not os.path.exists(self.data_path):
            print(f"\n⚠️  ATTENTION: Fichier de données non trouvé!")
            print(f"   Attendu: {self.data_path}")
        
        if not os.path.exists(self.processor_dir):
            print(f"\n⚠️  Le dossier preprocessing n'existe pas, il sera créé.")
            os.makedirs(self.processor_dir, exist_ok=True)
    
    def load_raw_data(self):
        """Charge les données brutes depuis le fichier CSV"""
        print(f"\n{'='*80}")
        print("1. CHARGEMENT DES DONNÉES BRUTES")
        print(f"{'='*80}")
        
        try:
            self.df_raw = pd.read_csv(self.data_path)
            print(f"✅ Fichier chargé: {os.path.basename(self.data_path)}")
            print(f"   📊 Dimensions: {self.df_raw.shape[0]:,} lignes × {self.df_raw.shape[1]} colonnes")
            print(f"   💾 Mémoire: {self.df_raw.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
            
            # Stats sur la variable cible
            if self.target in self.df_raw.columns:
                fraud_rate = self.df_raw[self.target].mean() * 100
                n_fraud = self.df_raw[self.target].sum()
                print(f"   🎯 Fraudes: {n_fraud:,} ({fraud_rate:.3f}%)")
                self.stats['fraud_rate_original'] = fraud_rate
            
            return True
            
        except FileNotFoundError:
            print(f"❌ ERREUR: Fichier non trouvé")
            print(f"   Chemin: {self.data_path}")
            print(f"\n💡 Vérifiez que le fichier existe:")
            print(f"   {self.base_dir}/")
            print(f"   └── data/")
            print(f"       └── raws/")
            print(f"           └── fraud_600k.csv")
            return False
        except Exception as e:
            print(f"❌ ERREUR lors du chargement: {e}")
            return False
    
    def load_processors(self):
        """Charge les processeurs existants (si disponibles)"""
        print(f"\n{'='*80}")
        print("2. CHARGEMENT DES PROCESSEURS EXISTANTS")
        print(f"{'='*80}")
        
        processor_files = {
            'scaler': 'scaler.pkl',
            'label_encoders': 'label_encoders.pkl',
            'feature_names': 'feature_names.pkl',
            'smote_config': 'smote_config.pkl'
        }
        
        loaded = {}
        for name, filename in processor_files.items():
            filepath = os.path.join(self.processor_dir, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'rb') as f:
                        loaded[name] = pickle.load(f)
                    print(f"✅ Chargé: {filename}")
                except Exception as e:
                    print(f"⚠️  Erreur lors du chargement de {filename}: {e}")
            else:
                print(f"ℹ️  Non trouvé: {filename} (sera créé)")
        
        # Appliquer les processeurs chargés
        if 'scaler' in loaded:
            self.scaler = loaded['scaler']
        if 'label_encoders' in loaded:
            self.label_encoders = loaded['label_encoders']
        if 'feature_names' in loaded:
            self.feature_names = loaded['feature_names']
        if 'smote_config' in loaded:
            self.smote_config = loaded['smote_config']
        
        return len(loaded)
    
    def clean_data(self):
        """Nettoie les données brutes"""
        print(f"\n{'='*80}")
        print("3. NETTOYAGE DES DONNÉES")
        print(f"{'='*80}")
        
        self.df_clean = self.df_raw.copy()
        
        # Supprimer la colonne d'index si présente
        if 'Unnamed: 0' in self.df_clean.columns:
            self.df_clean = self.df_clean.drop('Unnamed: 0', axis=1)
            print("✅ Colonne 'Unnamed: 0' supprimée")
        
        # Convertir les dates
        self.df_clean['trans_date_trans_time'] = pd.to_datetime(
            self.df_clean['trans_date_trans_time']
        )
        self.df_clean['dob'] = pd.to_datetime(self.df_clean['dob'])
        print("✅ Dates converties en datetime")
        
        # Vérifier les valeurs manquantes
        missing = self.df_clean.isnull().sum().sum()
        if missing > 0:
            print(f"⚠️  {missing} valeurs manquantes détectées")
        else:
            print("✅ Aucune valeur manquante")
        
        print(f"✅ Dataset nettoyé: {self.df_clean.shape[0]:,} × {self.df_clean.shape[1]}")
    
    def engineer_features(self):
        """Crée les nouvelles features"""
        print(f"\n{'='*80}")
        print("4. INGÉNIERIE DES FEATURES")
        print(f"{'='*80}")
        
        initial_cols = self.df_clean.shape[1]
        
        # Features temporelles
        print("\n📅 Features temporelles...")
        self.df_clean['trans_hour'] = self.df_clean['trans_date_trans_time'].dt.hour
        self.df_clean['trans_day'] = self.df_clean['trans_date_trans_time'].dt.day
        self.df_clean['trans_month'] = self.df_clean['trans_date_trans_time'].dt.month
        self.df_clean['trans_year'] = self.df_clean['trans_date_trans_time'].dt.year
        self.df_clean['trans_dayofweek'] = self.df_clean['trans_date_trans_time'].dt.dayofweek
        self.df_clean['is_weekend'] = (self.df_clean['trans_dayofweek'] >= 5).astype(int)
        print("   ✓ 6 features créées (hour, day, month, year, dayofweek, weekend)")
        
        # Âge du client
        print("\n👤 Âge du client...")
        self.df_clean['age'] = (
            self.df_clean['trans_date_trans_time'] - self.df_clean['dob']
        ).dt.days / 365.25
        print(f"   ✓ Âge moyen: {self.df_clean['age'].mean():.1f} ans")
        
        # Distance géographique
        print("\n📍 Distance client-marchand...")
        self.df_clean['distance_km'] = self._haversine_distance(
            self.df_clean['lat'], self.df_clean['long'],
            self.df_clean['merch_lat'], self.df_clean['merch_long']
        )
        print(f"   ✓ Distance moyenne: {self.df_clean['distance_km'].mean():.2f} km")
        
        # Catégories de montant
        print("\n💰 Catégories de montant...")
        self.df_clean['amt_category'] = pd.cut(
            self.df_clean['amt'],
            bins=[0, 50, 100, 200, float('inf')],
            labels=['faible', 'moyen', 'élevé', 'très_élevé']
        )
        print("   ✓ Catégories: faible, moyen, élevé, très_élevé")
        
        # Période de la journée
        print("\n🕐 Période de la journée...")
        self.df_clean['day_period'] = self.df_clean['trans_hour'].apply(
            self._get_period
        )
        print("   ✓ Périodes: matin, après-midi, soirée, nuit")
        
        new_features = self.df_clean.shape[1] - initial_cols
        print(f"\n✅ {new_features} nouvelles features créées!")
        self.stats['new_features'] = new_features
    
    def prepare_data(self):
        """Prépare les données pour l'entraînement"""
        print(f"\n{'='*80}")
        print("5. PRÉPARATION DES DONNÉES")
        print(f"{'='*80}")
        
        # Supprimer les colonnes inutiles
        df_model = self.df_clean.drop(
            columns=[c for c in self.cols_to_drop if c in self.df_clean.columns]
        )
        print(f"✅ {len([c for c in self.cols_to_drop if c in self.df_clean.columns])} colonnes supprimées")
        
        # Séparer X et y
        X = df_model.drop(self.target, axis=1)
        y = df_model[self.target]
        
        print(f"✅ Features (X): {X.shape}")
        print(f"✅ Target (y): {y.shape}")
        print(f"   Taux de fraude: {y.mean()*100:.2f}%")
        
        # Train/test split
        stratify = y if y.sum() > 0 else None
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
            X, y, test_size=self.test_size, random_state=self.random_state,
            stratify=stratify
        )
        
        print(f"\n✅ Train/Test Split:")
        print(f"   Train: {len(self.X_train):,} échantillons ({len(self.X_train)/len(X)*100:.1f}%)")
        print(f"   Test: {len(self.X_test):,} échantillons ({len(self.X_test)/len(X)*100:.1f}%)")
        
        # Sauvegarder les noms de features
        self.feature_names['all_features'] = X.columns.tolist()
    
    def encode_features(self):
      print(f"\n{'='*80}")
      print("6. ENCODAGE DES VARIABLES CATÉGORIELLES")
      print(f"{'='*80}")
    
      for col in self.categorical_features:
        if col in self.X_train.columns:
            # TOUJOURS créer un nouvel encodeur (ignorer les anciens)
            le = LabelEncoder()
            self.X_train[col] = le.fit_transform(self.X_train[col].astype(str))
            self.X_test[col] = le.transform(self.X_test[col].astype(str))
            self.label_encoders[col] = le
            print(f"✅ {col}: {len(le.classes_)} classes encodées")
    
      self.feature_names['categorical_features'] = self.categorical_features
      print(f"\n✅ {len(self.label_encoders)} variables catégorielles encodées")
    
    def scale_features(self):
        """Normalise les variables numériques"""
        print(f"\n{'='*80}")
        print("7. NORMALISATION DES VARIABLES NUMÉRIQUES")
        print(f"{'='*80}")
        
        # Identifier les colonnes numériques
        numeric_cols = self.X_train.select_dtypes(include=[np.number]).columns.tolist()
        self.feature_names['numerical_features'] = numeric_cols
        
        # Copier les DataFrames
        self.X_train_processed = self.X_train.copy()
        self.X_test_processed = self.X_test.copy()
        
        # Normaliser
        self.X_train_processed[numeric_cols] = self.scaler.fit_transform(
            self.X_train[numeric_cols]
        )
        self.X_test_processed[numeric_cols] = self.scaler.transform(
            self.X_test[numeric_cols]
        )
        
        print(f"✅ {len(numeric_cols)} variables numériques normalisées")
        print(f"   Méthode: RobustScaler (robuste aux outliers)")
    
    def apply_smote(self):
        """Applique SMOTE pour équilibrer les classes"""
        print(f"\n{'='*80}")
        print("8. GESTION DU DÉSÉQUILIBRE DES CLASSES (SMOTE)")
        print(f"{'='*80}")
        
        # Distribution avant SMOTE
        counter_before = Counter(self.y_train)
        print(f"\n📊 Distribution AVANT SMOTE:")
        print(f"   Classe 0 (Non-fraude): {counter_before[0]:,}")
        
        if 1 in counter_before and counter_before[1] >= 2:
            print(f"   Classe 1 (Fraude): {counter_before[1]:,}")
            print(f"   Ratio: {counter_before[0]/counter_before[1]:.2f}:1")
            
            # Appliquer SMOTE
            k_neighbors = min(5, counter_before[1] - 1)
            smote = SMOTE(random_state=self.random_state, k_neighbors=k_neighbors)
            
            self.X_train_processed, self.y_train_processed = smote.fit_resample(
                self.X_train_processed, self.y_train
            )
            
            # Distribution après SMOTE
            counter_after = Counter(self.y_train_processed)
            print(f"\n📊 Distribution APRÈS SMOTE:")
            print(f"   Classe 0 (Non-fraude): {counter_after[0]:,}")
            print(f"   Classe 1 (Fraude): {counter_after[1]:,}")
            print(f"   Ratio: 1:1 (équilibré)")
            
            self.smote_config = {
                'applied': True,
                'strategy': 'SMOTE',
                'random_state': self.random_state,
                'k_neighbors': k_neighbors,
                'samples_created': len(self.X_train_processed) - len(self.X_train)
            }
            
            print(f"\n✅ SMOTE appliqué avec succès!")
            print(f"   Échantillons synthétiques: {self.smote_config['samples_created']:,}")
            
        else:
            print(f"   ⚠️  Pas assez de fraudes pour SMOTE")
            self.y_train_processed = self.y_train
            self.smote_config = {'applied': False, 'reason': 'Insufficient fraud samples'}
            print(f"   SMOTE non appliqué")
    
    def save_processors(self):
        """Sauvegarde tous les processeurs"""
        print(f"\n{'='*80}")
        print("9. SAUVEGARDE DES PROCESSEURS")
        print(f"{'='*80}")
        
        # Créer le dossier
        os.makedirs(self.processor_dir, exist_ok=True)
        print(f"📁 Dossier: {self.processor_dir}")
        
        processors = {
            'scaler.pkl': self.scaler,
            'label_encoders.pkl': self.label_encoders,
            'feature_names.pkl': self.feature_names,
            'smote_config.pkl': self.smote_config
        }
        
        for filename, obj in processors.items():
            filepath = os.path.join(self.processor_dir, filename)
            with open(filepath, 'wb') as f:
                pickle.dump(obj, f)
            print(f"✅ {filename}")
        
        # Sauvegarder les données preprocessées
        datasets = {
            'X_train': self.X_train_processed,
            'X_test': self.X_test_processed,
            'y_train': self.y_train_processed,
            'y_test': self.y_test
        }
        filepath = os.path.join(self.processor_dir, 'preprocessed_data.pkl')
        with open(filepath, 'wb') as f:
            pickle.dump(datasets, f)
        print(f"✅ preprocessed_data.pkl")
        
        print(f"\n✅ Tous les processeurs sauvegardés!")
    
    def generate_report(self):
        """Génère un rapport final du preprocessing"""
        print(f"\n{'='*80}")
        print("📊 RAPPORT FINAL DU PREPROCESSING")
        print(f"{'='*80}")
        
        report_text = f"""
🎯 DONNÉES FINALES:
   • Train set: {len(self.X_train_processed):,} échantillons × {self.X_train_processed.shape[1]} features
   • Test set: {len(self.X_test_processed):,} échantillons × {self.X_test_processed.shape[1]} features
   • Features totales: {len(self.feature_names['all_features'])}
   • Features numériques: {len(self.feature_names['numerical_features'])}
   • Features catégorielles: {len(self.feature_names['categorical_features'])}

📈 TRANSFORMATIONS:
   • Nouvelles features créées: {self.stats.get('new_features', 0)}
   • Variables encodées: {len(self.label_encoders)}
   • Variables normalisées: {len(self.feature_names['numerical_features'])}
   • SMOTE appliqué: {'Oui' if self.smote_config['applied'] else 'Non'}
   {f"• Échantillons synthétiques: {self.smote_config.get('samples_created', 0):,}" if self.smote_config['applied'] else ""}

📁 FICHIERS SAUVEGARDÉS:
   • artifacts/preprocessing/scaler.pkl
   • artifacts/preprocessing/label_encoders.pkl
   • artifacts/preprocessing/feature_names.pkl
   • artifacts/preprocessing/smote_config.pkl
   • artifacts/preprocessing/preprocessed_data.pkl

✅ PREPROCESSING TERMINÉ AVEC SUCCÈS!
        """
        
        print(report_text)
        
        # Sauvegarder le rapport
        report_path = os.path.join(self.processor_dir, 'preprocessing_report.txt')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"RAPPORT DE PREPROCESSING\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*80}\n\n")
            f.write(report_text)
        
        print(f"📄 Rapport sauvegardé: {os.path.basename(report_path)}")
    
    def run_preprocessing(self):
        """
        Exécute le pipeline complet de preprocessing
        
        Returns:
        --------
        dict avec les données preprocessées et les processeurs
        """
        print(f"\n{'#'*80}")
        print(f"#{'DÉMARRAGE DU PIPELINE DE PREPROCESSING':^78}#")
        print(f"#{'PreprocessingFraud v1.0':^78}#")
        print(f"{'#'*80}\n")
        
        start_time = datetime.now()
        
        # Étapes du pipeline
        steps = [
            ('Chargement des données', self.load_raw_data),
            ('Chargement des processeurs', self.load_processors),
            ('Nettoyage', self.clean_data),
            ('Ingénierie des features', self.engineer_features),
            ('Préparation', self.prepare_data),
            ('Encodage', self.encode_features),
            ('Normalisation', self.scale_features),
            ('SMOTE', self.apply_smote),
            ('Sauvegarde', self.save_processors),
        ]
        
        for i, (step_name, step_func) in enumerate(steps, 1):
            try:
                result = step_func()
                if result is False:
                    print(f"\n❌ Arrêt du pipeline à l'étape: {step_name}")
                    return None
            except Exception as e:
                print(f"\n❌ ERREUR à l'étape '{step_name}': {e}")
                import traceback
                traceback.print_exc()
                return None
        
        # Générer le rapport
        self.generate_report()
        
        # Temps d'exécution
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        print(f"\n⏱️  Temps d'exécution: {duration:.2f} secondes")
        
        # Retourner les résultats
        return {
            'X_train': self.X_train_processed,
            'X_test': self.X_test_processed,
            'y_train': self.y_train_processed,
            'y_test': self.y_test,
            'scaler': self.scaler,
            'label_encoders': self.label_encoders,
            'feature_names': self.feature_names,
            'smote_config': self.smote_config
        }
    
    # Méthodes utilitaires privées
    
    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calcule la distance Haversine entre deux points"""
        R = 6371  # Rayon de la Terre en km
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))
        return R * c
    
    def _get_period(self, hour):
        """Détermine la période de la journée"""
        if 6 <= hour < 12:
            return 'matin'
        elif 12 <= hour < 18:
            return 'après-midi'
        elif 18 <= hour < 22:
            return 'soirée'
        else:
            return 'nuit'


def main():
    """
    Fonction principale pour exécuter le preprocessing
    """
    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║                                                                  ║
    ║          PREPROCESSING - DÉTECTION DE FRAUDE BANCAIRE            ║
    ║                                                                  ║
    ║                     Cours MLOps — ENET'Com                       ║
    ║                                                                  ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # Créer l'instance avec le fichier fraud_600k.csv
    preprocessor = PreprocessingFraud(
        data_filename='fraud_600k.csv',
        test_size=0.2,
        random_state=42
    )
    
    # Exécuter le preprocessing
    results = preprocessor.run_preprocessing()
    
    if results is not None:
        print(f"\n{'='*80}")
        print("✅ PREPROCESSING RÉUSSI!")
        print(f"{'='*80}")
        print("\nRésultats disponibles:")
        print(f"  • X_train: {results['X_train'].shape}")
        print(f"  • X_test: {results['X_test'].shape}")
        print(f"  • y_train: {results['y_train'].shape}")
        print(f"  • y_test: {results['y_test'].shape}")
        
        print("\n🎯 Prochaines étapes:")
        print("  1. Entraîner des modèles de classification")
        print("  2. Évaluer les performances")
        print("  3. Optimiser les hyperparamètres")
        print("  4. Déployer le meilleur modèle")
        
        return preprocessor, results
    else:
        print("\n❌ Le preprocessing a échoué!")
        return None, None


if __name__ == "__main__":
    preprocessor, results = main()