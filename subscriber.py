import paho.mqtt.client as mqtt

BROKER = "localhost"
TOPIC = "occ/vehicle"

def on_message(client, userdata, msg):
    print("\nReceived Vehicle Data:")
    print(msg.payload.decode())

client = mqtt.Client()
client.on_message = on_message

client.connect(BROKER, 1883, 60)
client.subscribe(TOPIC)

print("Listening for AGV telemetry...\n")

client.loop_forever()
