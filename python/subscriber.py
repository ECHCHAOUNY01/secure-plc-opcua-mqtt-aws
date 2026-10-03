"""Subscribe with verified TLS; reconnects resubscribe (Paho 2.x)."""
import getpass
import os
import ssl
import uuid

import paho.mqtt.client as mqtt


def main():
    broker = os.environ["MQTT_HOST"]
    username = os.environ["MQTT_USERNAME"]
    password = os.getenv("MQTT_PASSWORD") or getpass.getpass("MQTT password: ")
    topic = os.getenv("MQTT_TOPIC", "factory/#")
    failures = []

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            failures.append(f"Connection rejected: {reason_code}")
            client.disconnect()
            return
        result, _ = client.subscribe(topic, qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            failures.append(f"Subscribe failed: {result}")
            client.disconnect()

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            failures.append(f"Subscription rejected: {reason_codes}")
            client.disconnect()
        else:
            print(f"Subscribed to {topic}", flush=True)

    def on_message(client, userdata, message):
        print(message.topic, message.payload.decode("utf-8", errors="replace"), flush=True)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"python_sub_{uuid.uuid4().hex[:12]}")
    client.username_pw_set(username, password)
    client.tls_set_context(ssl.create_default_context(cafile=os.environ["MQTT_CA_FILE"]))
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.connect(broker, 8883, 60)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
    if failures:
        raise RuntimeError("; ".join(failures))


if __name__ == "__main__":
    main()
