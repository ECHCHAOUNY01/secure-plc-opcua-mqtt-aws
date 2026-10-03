"""Publish one QoS 1 message with verified TLS (Paho 2.x)."""
import getpass
import os
import ssl
import threading
import uuid

import paho.mqtt.client as mqtt


def main():
    broker = os.environ["MQTT_HOST"]
    username = os.environ["MQTT_USERNAME"]
    password = os.getenv("MQTT_PASSWORD") or getpass.getpass("MQTT password: ")
    connected = threading.Event()
    failures = []

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            failures.append(str(reason_code))
        connected.set()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"python_pub_{uuid.uuid4().hex[:12]}")
    client.on_connect = on_connect
    client.username_pw_set(username, password)
    client.tls_set_context(ssl.create_default_context(cafile=os.environ["MQTT_CA_FILE"]))
    client.connect(broker, 8883, 60)
    client.loop_start()
    try:
        if not connected.wait(15):
            raise TimeoutError("No MQTT CONNACK received within 15 seconds")
        if failures:
            raise RuntimeError(f"Broker rejected connection: {failures[0]}")
        topic = os.getenv("MQTT_TOPIC", "factory/test")
        message = client.publish(topic, '{"temperature": 25.4}', qos=1, retain=False)
        message.wait_for_publish(timeout=15)
        if not message.is_published():
            raise TimeoutError("No publish acknowledgement received within 15 seconds")
        print(f"Broker acknowledged message on {topic}")
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
