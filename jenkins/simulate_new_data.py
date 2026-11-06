import pandas as pd
import numpy as np
from pathlib import Path

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent.parent
REFERENCE_PATH = BASE_DIR / "data" / "raws" / "fraud_600k.csv"
NEW_DATA_PATH = BASE_DIR / "data" / "raws" / "new_data.csv"

def simulate_drift(df):
    """
    Simule un drift réaliste sur les données de fraude.
    On modifie les distributions pour simuler un changement de comportement.
    """
    df_new = df.copy()

    print("🔧 Simulation du drift en cours...")

    # 1. Les fraudeurs font maintenant des montants beaucoup plus élevés
    df_new['amt'] = df_new['amt'] * np.random.uniform(5, 15, size=len(df_new))
    print("   ✅ amt : multiplié par 5-15x")

    # 2. La population des villes change (migration vers grandes villes)
    df_new['city_pop'] = df_new['city_pop'] * np.random.uniform(3, 8, size=len(df_new))
    print("   ✅ city_pop : multiplié par 3-8x")

    # 3. Les transactions viennent de nouvelles localisations géographiques
    df_new['merch_lat'] = df_new['merch_lat'] + np.random.normal(10, 5, size=len(df_new))
    df_new['merch_long'] = df_new['merch_long'] + np.random.normal(10, 5, size=len(df_new))
    print("   ✅ merch_lat/long : déplacés géographiquement")

    # 4. Les catégories changent (nouvelles habitudes d'achat)
    categories = df_new['category'].unique()
    # Inverser la distribution des catégories
    df_new['category'] = np.random.choice(
        categories,
        size=len(df_new),
        p=np.ones(len(categories)) / len(categories)  # distribution uniforme
    )
    print("   ✅ category : distribution uniformisée")

    return df_new


def main():
    print("=" * 50)
    print("🎭 Simulation de Nouvelles Données (avec Drift)")
    print("=" * 50)

    # 1. Charger les données de référence
    print(f"\n📂 Chargement de {REFERENCE_PATH}...")
    if not REFERENCE_PATH.exists():
        print(f"❌ Fichier non trouvé: {REFERENCE_PATH}")
        return

    df = pd.read_csv(REFERENCE_PATH)
    print(f"   ✅ {len(df)} lignes chargées")

    # 2. Prendre un échantillon de 50k lignes
    df_sample = df.sample(n=50000, random_state=42)
    print(f"   ✅ Échantillon de 50 000 lignes")

    # 3. Simuler le drift
    print("\n")
    df_new = simulate_drift(df_sample)

    # 4. Sauvegarder
    NEW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_new.to_csv(NEW_DATA_PATH, index=False)
    print(f"\n✅ Nouvelles données sauvegardées : {NEW_DATA_PATH}")
    print(f"   - Lignes : {len(df_new)}")
    print("=" * 50)
    print("\n🚀 Lance maintenant le pipeline Jenkins pour voir le drift détecté !")


if __name__ == "__main__":
    main()