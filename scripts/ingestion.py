import time
import pandas as pd
import json
import os
from kafka import KafkaProducer

# Configurazione
KAFKA_TOPIC = "tennis-live"
KAFKA_SERVER = "kafka:9092"
DATA_PATH = "/app/data/2025.csv"

def main():
    print("⏳ Attendo 10 secondi che Kafka sia pronto...")
    time.sleep(10)

    try:
        # Creazione Producer
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_SERVER,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            api_version=(0, 10, 1) 
        )
        print("✅ Connesso a Kafka!")
    except Exception as e:
        print(f"❌ Errore connessione Kafka: {e}")
        return

    if not os.path.exists(DATA_PATH):
        print(f"❌ Errore: File {DATA_PATH} non trovato.")
        return

    print(f"🎾 Leggo {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    
    df.columns = df.columns.str.strip().str.replace(' ', '_')

    print(f"🚀 Inizio streaming di {len(df)} partite (1 ogni 0.5 secondi)...")

    for index, row in df.iterrows():
        match_data = row.to_dict()
        
        producer.send(KAFKA_TOPIC, match_data)
        
        print(f"📡 [LIVE] {match_data.get('Winner_Name')} vs {match_data.get('Loser_Name')}")
        time.sleep(0.5)

    print("✅ Streaming completato.")
    producer.flush()
    producer.close()

if __name__ == "__main__":
    main()