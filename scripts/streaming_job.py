import os
import shutil
import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, sum as _sum
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pymongo import MongoClient

checkpoint_dir = "/app/data/checkpoint_new_v2"
if os.path.exists(checkpoint_dir):
    try:
        shutil.rmtree(checkpoint_dir)
        print(f"🧹 Checkpoint rimosso: {checkpoint_dir}")
    except Exception as e:
        print(f"⚠️ Errore pulizia checkpoint: {e}")

os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 pyspark-shell'

MONGO_URI = "mongodb://mongo:27017/"
DB_NAME = "tennis_db"
COLL_NAME = "realtime_stats"

print("🔥 Avvio Spark Structured Streaming...")

spark = SparkSession.builder \
    .appName("TennisSpeedLayer") \
    .master("spark://spark-master:7077") \
    .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
    .config("spark.sql.streaming.checkpointLocation", checkpoint_dir) \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# Definizione Schema
schema = StructType([
    StructField("Tourney_Name", StringType(), True),
    StructField("Tourney_Date", StringType(), True),
    StructField("Tourney_Level", StringType(), True),
    StructField("Surface", StringType(), True),
    StructField("Draw_Size", IntegerType(), True),
    StructField("Winner_Name", StringType(), True),
    StructField("Loser_Name", StringType(), True),
    StructField("Score", StringType(), True),
    StructField("Round", StringType(), True),
    StructField("W_Ace", IntegerType(), True),
    StructField("Minutes", DoubleType(), True),
    StructField("W_ServicePoints", IntegerType(), True),
    StructField("W_1stIn", IntegerType(), True),
    StructField("W_1stWon", IntegerType(), True),
    StructField("W_2ndWon", IntegerType(), True),
    StructField("L_ServicePoints", IntegerType(), True),
    StructField("L_1stIn", IntegerType(), True),
    StructField("L_1stWon", IntegerType(), True),
    StructField("L_2ndWon", IntegerType(), True),
    StructField("L_Ace", IntegerType(), True),
    StructField("W_DoubleFault", IntegerType(), True),
    StructField("L_DoubleFault", IntegerType(), True),
    StructField("Best_of", IntegerType(), True),
    StructField("Winner_Nat", StringType(), True),
    StructField("Loser_Nat", StringType(), True),
    StructField("Indoor_Outdoor", StringType(), True),
    StructField("W_BreakPointSaved", IntegerType(), True),
    StructField("W_BreakPointFaced", IntegerType(), True),
    StructField("L_BreakPointSaved", IntegerType(), True),
    StructField("L_BreakPointFaced", IntegerType(), True),
    StructField("Winner_Rank", IntegerType(), True),
    StructField("Loser_Rank", IntegerType(), True),
    StructField("Winner_Age", DoubleType(), True),
    StructField("Loser_Age", DoubleType(), True),
    StructField("Winner_Seed", IntegerType(), True),
    StructField("Winner_Hand", StringType(), True),
    StructField("Loser_Hand", StringType(), True),
    StructField("Winner_Ht", IntegerType(), True),
    StructField("Loser_Ht", IntegerType(), True),
    StructField("Winner_Rank_Points", IntegerType(), True),
    StructField("Loser_Rank_Points", IntegerType(), True)
])

raw_stream = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka:9092") \
    .option("subscribe", "tennis-live") \
    .option("startingOffsets", "earliest") \
    .option("failOnDataLoss", "false") \
    .load()

parsed_stream = raw_stream.selectExpr("CAST(value AS STRING)") \
    .select(from_json(col("value"), schema).alias("data")) \
    .select("data.*")
def write_to_mongo(batch_df, epoch_id):
    if not batch_df.isEmpty():
        try:
            pdf = batch_df.toPandas()
            data_dict = pdf.to_dict("records")
            client = MongoClient(MONGO_URI)
            db = client[DB_NAME]
            db["realtime_matches"].insert_many(data_dict)
            client.close()
            print(f"💾 [MONGO] Batch {epoch_id} salvato ({len(data_dict)} match).")
        except Exception as e:
            print(f"❌ Errore Mongo: {e}")

query = parsed_stream.writeStream \
    .outputMode("append") \
    .option("checkpointLocation", checkpoint_dir) \
    .foreachBatch(write_to_mongo) \
    .trigger(processingTime='1 seconds') \
    .start()

print("🚀 Speed Layer in ascolto...")
query.awaitTermination()