import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, when, row_number
from pyspark.sql.window import Window
from pyspark.ml.feature import VectorAssembler, StandardScaler, StringIndexer
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.evaluation import MulticlassClassificationEvaluator
from pyspark.ml import Pipeline
from pymongo import MongoClient
import itertools
import pandas as pd 

# CONFIGURAZIONE
MONGO_URI = "mongodb://mongo:27017/"
DB_NAME = "tennis_db"
COLL_METRICS = "batch_model_metrics"

def get_spark_session():
    return SparkSession.builder \
        .appName("TennisBatchLayer_Full") \
        .master("local[*]") \
        .config("spark.mongodb.output.uri", f"{MONGO_URI}{DB_NAME}.{COLL_METRICS}") \
        .getOrCreate()

def load_and_prep_data(spark):
    data_path = "/app/data/*.csv"
    spark_df = spark.read.option("header", "true").option("inferSchema", "true").csv(data_path)
    
    # Pulizia e Casting
    df = spark_df.withColumn("Winner_Rank", col("Winner_Rank").cast("int")) \
           .withColumn("Loser_Rank", col("Loser_Rank").cast("int")) \
           .withColumn("Winner_Rank_Points", col("Winner_Rank_Points").cast("int")) \
           .withColumn("Loser_Rank_Points", col("Loser_Rank_Points").cast("int")) \
           .na.drop(subset=["Winner_Rank", "Loser_Rank"])

    # Creazione Dataset Bilanciato (Vittoria=1, Sconfitta=0)
    df_win = df.select(
        (col("Loser_Rank") - col("Winner_Rank")).alias("Rank_Diff"),
        (col("Winner_Rank_Points") - col("Loser_Rank_Points")).alias("Points_Diff"),
        col("Surface"),
        lit(1.0).alias("label")
    )
    df_loss = df.select(
        (col("Winner_Rank") - col("Loser_Rank")).alias("Rank_Diff"),
        (col("Loser_Rank_Points") - col("Winner_Rank_Points")).alias("Points_Diff"),
        col("Surface"),
        lit(0.0).alias("label")
    )
    
    full_dataset = df_win.union(df_loss)
    
    return full_dataset, spark_df 

def train_and_evaluate(df):
    print("🧠 Addestramento Modello Spark MLlib...")
    
    indexer = StringIndexer(inputCol="Surface", outputCol="Surface_Index", handleInvalid="keep")
    
    assembler = VectorAssembler(inputCols=["Rank_Diff", "Points_Diff", "Surface_Index"], outputCol="features")
    
    scaler = StandardScaler(inputCol="features", outputCol="scaledFeatures")
    lr = LogisticRegression(featuresCol="scaledFeatures", labelCol="label", maxIter=10)
    
    pipeline = Pipeline(stages=[indexer, assembler, scaler, lr])
    
    train_data, test_data = df.randomSplit([0.8, 0.2], seed=42)
    model = pipeline.fit(train_data)
    predictions = model.transform(test_data)
    
    evaluator = MulticlassClassificationEvaluator(metricName="accuracy")
    accuracy = evaluator.evaluate(predictions)
    
    cm_counts = predictions.groupBy("label", "prediction").count().collect()
    
    cm = {"TP": 0, "TN": 0, "FP": 0, "FN": 0}
    for row in cm_counts:
        l, p, c = row["label"], row["prediction"], row["count"]
        if l == 1.0 and p == 1.0: cm["TP"] = c
        elif l == 0.0 and p == 0.0: cm["TN"] = c
        elif l == 0.0 and p == 1.0: cm["FP"] = c
        elif l == 1.0 and p == 0.0: cm["FN"] = c

    print(f"🎯 Accuratezza: {accuracy:.2%} | Matrice: {cm}")
    return model, accuracy, cm

def get_defending_champions(df):

    pdf = df.select("Tourney_Name", "Tourney_Date", "Winner_Name", "Surface").toPandas()
    
    pdf["Tourney_Date"] = pd.to_datetime(pdf["Tourney_Date"], errors='coerce')
    
    # 1. Mappa Superfici (Tutti i tornei disponibili nel dataset)
    # Ordiniamo per data decrescente per prendere la superficie più recente (utile se è cambiata)
    pdf_sorted = pdf.sort_values("Tourney_Date", ascending=False)
    pdf_latest_surf = pdf_sorted.drop_duplicates(subset=["Tourney_Name"])
    surf_map = dict(zip(pdf_latest_surf["Tourney_Name"], pdf_latest_surf["Surface"]))

    # 2. Mappa Difensori (Solo vincitori 2025)
    pdf_2025 = pdf[pdf["Tourney_Date"].dt.year == 2025]
    pdf_2025 = pdf_2025.sort_values("Tourney_Date", ascending=False)
    pdf_latest_def = pdf_2025.drop_duplicates(subset=["Tourney_Name"])
    def_map = dict(zip(pdf_latest_def["Tourney_Name"], pdf_latest_def["Winner_Name"]))
    
    return def_map, surf_map

def simulate_2026_season_dynamic(spark, model, df_full):
    print("🔮 Simulazione Sinner vs Alcaraz 2026 (Dynamic)...")
    
    def_map, surf_map = get_defending_champions(df_full)
    
    # Iteriamo su TUTTI i tornei conosciuti (da surf_map), non solo quelli del 2025
    sorted_tourneys = sorted(surf_map.keys())
    
    sinner_pts, sinner_rnk = 11830, 1
    alcaraz_pts, alcaraz_rnk = 9500, 2
    
    sim_data = []
    
    for t_name in sorted_tourneys:
        surf = surf_map.get(t_name, "Hard")
        defender = def_map.get(t_name, "-")
        
        sim_data.append({
            "Tourney": t_name, 
            "Surface": surf,
            "Rank_Diff": alcaraz_rnk - sinner_rnk,
            "Points_Diff": sinner_pts - alcaraz_pts, 
            "Defender": defender
        })

    sim_sdf = spark.createDataFrame(pd.DataFrame(sim_data))
    
    preds = model.transform(sim_sdf)
    rows = preds.select("Tourney", "Surface", "Defender", "probability").collect()
    
    results = []
    for row in rows:
        t_name = row["Tourney"]
        surf = row["Surface"]
        defender = row["Defender"]
        
        prob_sinner = float(row["probability"][1])
        
        if defender == "Jannik Sinner": prob_sinner += 0.05
        if defender == "Carlos Alcaraz": prob_sinner -= 0.05
        
        if surf == "Clay": 
            prob_sinner -= 0.15 
        if surf == "Grass":
            prob_sinner -= 0.05
        if surf == "Hard":
            prob_sinner += 0.05
            
        prob_sinner = max(0.01, min(0.99, prob_sinner))
        
        winner = "SINNER" if prob_sinner > 0.5 else "ALCARAZ"
        q_sinner = round(1 / prob_sinner, 2)
        q_alcaraz = round(1 / (1 - prob_sinner), 2)
        
        def_str = "-"
        if defender == "Jannik Sinner": def_str = "SINNER"
        if defender == "Carlos Alcaraz": def_str = "ALCARAZ"
        
        results.append({
            "TORNEO": t_name,
            "SUPERFICIE": surf,
            "DEFEND 25": def_str,
            "FAVORITO": winner,
            "Q. SINNER": q_sinner,
            "Q. ALCARAZ": q_alcaraz
        })
        
    return results

def save_to_mongo(accuracy, cm, predictions_2026):
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        coll = db[COLL_METRICS]
        
        doc = {
            "model_type": "Spark_LogisticRegression_Dynamic",
            "accuracy": accuracy,
            "confusion_matrix": cm, 
            "predictions_2026": predictions_2026, 
            "timestamp": "Latest Run"
        }
        
        coll.delete_many({}) 
        coll.insert_one(doc)
        print("💾 Report completo salvato su MongoDB.")
        client.close()
    except Exception as e:
        print(f"❌ Errore Mongo: {e}")

if __name__ == "__main__":
    spark = get_spark_session()
    
    df, raw_df = load_and_prep_data(spark)
    
    model, acc, cm = train_and_evaluate(df)
    
    preds_2026 = simulate_2026_season_dynamic(spark, model, raw_df)
    
    save_to_mongo(acc, cm, preds_2026)
    
    spark.stop()