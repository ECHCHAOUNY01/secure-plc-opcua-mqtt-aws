# Secure PLC → OPC UA → KEPServerEX → MQTT/TLS → AWS EC2

A reproducible OT-to-cloud lab showing how to:

- Read Siemens PLC data with OPC UA in KEPServerEX
- Publish KEPServer tags with the IoT Gateway MQTT agent
- Host a Mosquitto broker on AWS EC2
- Add MQTT username/password authentication
- Protect MQTT with TLS on port 8883
- Create a private CA and server certificate with OpenSSL
- Trust the CA on Windows/KEPServerEX
- Verify the broker with MQTTX
- Optionally test with Python Paho publisher/subscriber clients

> Security note: do not commit private keys, passwords, or live production credentials to GitHub.

## Final Architecture

```text
Siemens PLC
   │ OPC UA
   ▼
KEPServerEX
   │ IoT Gateway
   │ MQTT over TLS + Username/Password
   ▼
AWS EC2 (Ubuntu + Mosquitto :8883)
   │
   ├── MQTTX
   ├── Python Paho
   ├── Node-RED
   └── Other subscribers
```

## Before you begin

Use an isolated lab with a Siemens CPU/firmware that supports an enabled, licensed OPC UA server, Windows with KEPServerEX OPC UA Client driver and IoT Gateway, MQTTX, and an Ubuntu EC2 instance. Exact Siemens and Kepware menu labels depend on the installed version. Python examples require Python 3.9+ and Paho 2.x.

Replace every `<...>` placeholder before running commands. Keep the EC2 DNS name stable; an address change may require a new certificate. Allow TCP 22 only from your administration IP and TCP 8883 from the public egress IPs of KEPServer and test clients. Keep the PLC endpoint on the private OT network.

This is a lab recipe, not evidence of a tested production deployment. The shared `admin` MQTT account has no built-in administrator role; without topic ACLs, authenticated clients can access all topics. Use separate accounts and topic ACLs before extending the lab to multiple trust boundaries.

## 1. Connect to EC2

On Windows PowerShell:

```powershell
cd C:\Users\<YOUR_USER>\Desktop\AWS_ec2
icacls .\Aws_ec2_keypair.pem /inheritance:r
icacls .\Aws_ec2_keypair.pem /grant:r "$($env:USERNAME):(R)"
ssh -i .\Aws_ec2_keypair.pem ubuntu@<EC2_DNS>
```

![EC2 instance summary with several identifying fields masked](images/Code_Generated_Image%20%281%29.png)

*EC2 instance overview. Use your own instance's public DNS in the commands and certificate SAN.*

## 2. Install Mosquitto and OpenSSL

```bash
sudo apt update
sudo apt install mosquitto mosquitto-clients openssl -y
sudo systemctl status mosquitto
```

## 3. Create MQTT credentials

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd admin
sudo chown mosquitto:mosquitto /etc/mosquitto/passwd
sudo chmod 600 /etc/mosquitto/passwd
```

The `-c` option creates/overwrites the password file. For additional users, omit `-c` to preserve existing accounts.

## 4. Create the CA

```bash
cd /etc/mosquitto
sudo mkdir -p certs
cd certs

sudo openssl genrsa -aes256 -out ca.key 3072
sudo chmod 600 ca.key

sudo openssl req -new -x509 \
  -days 1833 \
  -sha256 \
  -key ca.key \
  -subj "/CN=OT Lab Root CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -out ca.crt
```

This lab generates the CA on EC2 for simplicity. After signing, keep an encrypted backup of the CA key offline and remove the broker copy; production CA signing should happen off the broker. Keep `ca.key` private. `ca.crt` is the public CA certificate distributed to clients.

## 5. Create the server certificate configuration

```bash
sudo vim /etc/mosquitto/certs/server.cnf
```

Use:

```ini
[req]
default_bits = 2048
prompt = no
default_md = sha256
req_extensions = req_ext
distinguished_name = dn

[dn]
CN = <EC2_DNS>

[req_ext]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = <EC2_DNS>
IP.1 = <EC2_PUBLIC_IP>
```

Save in Vim with:

```text
Esc
:wq
Enter
```

## 6. Create and sign the server certificate

```bash
cd /etc/mosquitto/certs
sudo openssl genrsa -out server.key 2048
sudo chmod 600 server.key

sudo openssl req -new \
  -key server.key \
  -out server.csr \
  -config server.cnf

sudo openssl x509 -req \
  -in server.csr \
  -CA ca.crt \
  -CAkey ca.key \
  -CAcreateserial \
  -out server.crt \
  -days 365 \
  -sha256 \
  -extensions req_ext \
  -extfile server.cnf
```

Verify:

```bash
openssl x509 \
  -in server.crt \
  -noout \
  -subject \
  -issuer \
  -ext subjectAltName
```

The SAN must contain the same EC2 hostname used by clients.

## 7. Set certificate permissions

```bash
sudo chown mosquitto:mosquitto server.key server.crt
sudo chmod 600 server.key
sudo chmod 644 server.crt ca.crt
```

## 8. Configure Mosquitto TLS

Create:

```bash
sudo vim /etc/mosquitto/conf.d/secure-mqtt.conf
```

Use:

```conf
listener 8883
protocol mqtt
tls_version tlsv1.2
require_certificate false

cafile /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/server.crt
keyfile /etc/mosquitto/certs/server.key

allow_anonymous false
password_file /etc/mosquitto/passwd
```

Use the supplied [Mosquitto configuration](mosquitto/secure-mqtt.conf.example) and [OpenSSL configuration](openssl/server.cnf.example) as templates. Ensure `/etc/mosquitto/mosquitto.conf` includes `include_dir /etc/mosquitto/conf.d`. Review existing listeners so an older plaintext listener is not left exposed. This recipe uses server-authenticated TLS, not mutual TLS.

Restart and verify:

```bash
sudo systemctl restart mosquitto
sudo systemctl status mosquitto
sudo ss -lntp | grep 8883
sudo journalctl -u mosquitto -n 50 --no-pager
```

## 9. AWS Security Group

Allow inbound:

```text
TCP 22   → My IP
TCP 8883 → My IP
```

Avoid exposing MQTT to `0.0.0.0/0` unless intentionally required.

![AWS security group inbound rules from the supplied lab image](images/Code_Generated_Image.png)

*This image shows broad lab rules, including SSH and MQTT open to `0.0.0.0/0`, plus plaintext port 1883. Follow the restricted source-IP rules above; this image is not the recommended inbound configuration. Remove unused inbound rules.*

## 10. Copy the CA certificate to Windows

Run from Windows PowerShell:

```powershell
scp -i .\Aws_ec2_keypair.pem ubuntu@<EC2_DNS>:/etc/mosquitto/certs/ca.crt .
```

Do not copy `ca.key` or `server.key` to clients.

## 11. Test with MQTTX

Use:

```text
Host: <EC2_DNS>
Port: 8883
SSL/TLS: ON
CA: ca.crt
Server certificate verification: ON
Client certificate/key: empty
Username: admin
Password: <YOUR_PASSWORD>
Client ID: mqttx_windows_01
```

Subscribe to:

```text
#
```

for a first test, or later to your production topic.

## 12. Configure KEPServerEX OPC UA

For the detailed **S7-1500 server certificate / KEPServer Client Driver certificate exchange**, follow [OPC UA certificates and CA setup](docs/opcua-certificates.md). It explains both trust directions, TIA Portal and Kepware settings, and how this differs from the MQTT OpenSSL CA.

1. In TIA Portal, enable the PLC OPC UA server, expose the intended data, and configure a supported secure endpoint and user permissions. Download the configuration to the PLC.
2. In KEPServerEX, create an OPC UA Client channel and select the PLC endpoint, such as `opc.tcp://<PLC_PRIVATE_IP>:4840` (use the port actually configured on the PLC).
3. Select a mutually supported security policy and `SignAndEncrypt`. Configure the PLC user if required.
4. Trust the PLC server certificate in the Kepware OPC UA client configuration, and explicitly trust the Kepware client certificate on the PLC. Verify certificate identities before accepting them. This trust exchange is separate from the MQTT CA created in section 4.
5. Add a device, browse the exposed namespace, and import the required nodes as tags. Confirm good quality and changing values in the OPC Quick Client.

See the [Siemens OPC UA certificate guidance](https://docs.tia.siemens.cloud/r/en-us/v21/configuring-automation-systems/using-opc-ua-communication-s7-1200-s7-1500-s7-1500t-s7-1200-g2/using-the-s7-1500-as-an-opc-ua-server-s7-1500-s7-1200-g2/configuring-the-opc-ua-server-s7-1500-s7-1200-g2/handling-client-and-server-certificates-s7-1500) for device-specific trust handling.

Example PLC nodes:

```text
data_to_kepserver.Motor_data.temp
data_to_kepserver.Motor_data.current
data_to_kepserver.Motor_data.state
```

Confirm KEPServer can read the tags before configuring MQTT.

## 13. Configure the KEPServer IoT Gateway MQTT agent

Under IoT Gateway, create an MQTT Client agent, configure the connection below, and add the PLC tags to the agent's items. Enable the agent and at least one tag, set the publish/update interval for your lab (for example 1000 ms), and apply the changes. See [PTC agent configuration](https://support.ptc.com/help/kepware/features/en/kepware/features/IOTGATEWAY/configure_newagent.html).

Example:

```text
URL:
ssl://<EC2_DNS>:8883

Topic:
factory/plc1/data

QoS:
1

Format:
Wide Format

Client ID:
kepserver_plc_gateway_01

Username:
admin

Password:
<YOUR_PASSWORD>
```

Do not reuse MQTTX or Python Client IDs.

![KEPServer IoT Gateway security properties showing credentials, TLS 1.2, and client certificate disabled](images/ccc976b2-70e9-4019-ad49-00a12809729c.png)

*Security settings reference: unique Client ID, MQTT credentials, TLS 1.2, and client certificate disabled for this server-authenticated TLS setup. This is the MQTT agent configuration; OPC UA application-certificate trust is configured separately.*

## 14. Trust the private CA on Windows

If KEPServer reports:

```text
unable to find valid certification path to requested target
```

import `ca.crt` into the Windows Local Computer trusted root store.

Administrator Command Prompt:

```cmd
certutil -addstore "Root" C:\path\to\ca.crt
```

Or use MMC:

```text
Certificates
→ Computer account
→ Local Computer
→ Trusted Root Certification Authorities
→ Certificates
→ Import
```

Restart/reinitialize the MQTT agents after importing the CA. See the [PTC IoT Gateway manual](https://www.ptc.com/~/media/kepware-store/en/manuals/iot-gateway-manual) for certificate-store behavior and the [MQTT security settings](https://support.ptc.com/help/kepware/features/en/kepware/features/IOTGATEWAY/client_security.html).

If Mosquitto uses server-side TLS plus username/password only, leave the KEPServer MQTT client certificate disabled.

A successful KEPServer event looks like:

```text
MQTT agent 'AWS_e2c' is connected to broker
'ssl://<EC2_DNS>:8883'
```

## 15. Subscribe from MQTTX

Subscribe to the exact KEPServer topic:

```text
factory/plc1/data
```

or use:

```text
#
```

for troubleshooting.

Change a PLC value and confirm the MQTT message arrives.

![MQTTX displaying PLC tag payloads](images/Code_Generated_Image%20%282%29.png)

*The supplied MQTTX image displays PLC tag payloads on `Awse2c/data` with QoS 0. This tutorial uses `factory/plc1/data` and publisher QoS 1; match your subscription to the topic you configure. Received payloads alone do not demonstrate certificate verification settings.*

## 16. Optional Python Paho TLS publisher

From the repository root, create an environment and install Paho:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r python/requirements.txt
$env:MQTT_HOST = "<EC2_DNS>"
$env:MQTT_USERNAME = "admin"
$env:MQTT_CA_FILE = "C:\path\to\ca.crt"
```

The scripts prompt for the password without echoing it. Automation may supply `MQTT_PASSWORD` through its secret manager. `MQTT_TOPIC` optionally overrides the default topic. Keep hostname verification enabled.

Run the subscriber in another terminal first (set the same variables there), then publish:

```powershell
.\.venv\Scripts\python.exe python/publisher.py
```

[Publisher source](python/publisher.py):

```python
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
```

The network loop processes MQTT acknowledgements; the publisher waits for QoS 1 completion before disconnecting, as described in the [Paho client documentation](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html). An acknowledgement confirms broker receipt, not subscriber processing.

## 17. Optional Python Paho TLS subscriber

```powershell
.\.venv\Scripts\python.exe python/subscriber.py
```

Wait for `Subscribed to factory/#`, then publish or change a PLC value. The Python publisher uses `factory/test`; KEPServer uses `factory/plc1/data`. Both match `factory/#`. Each Python process creates a unique Client ID. Stop the subscriber with Ctrl+C.

[Subscriber source](python/subscriber.py):

```python
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
```

## 18. Final pipeline

```text
PLC
↓
OPC UA
↓
KEPServerEX
↓
IoT Gateway
↓
MQTT over TLS :8883
↓
AWS EC2 Mosquitto
↓
MQTTX / Python / Node-RED / other subscribers
```

## 19. Troubleshooting

### TLS hostname mismatch

```text
ERR_TLS_CERT_ALTNAME_INVALID
```

Check:

```bash
openssl x509 -in /etc/mosquitto/certs/server.crt -noout -ext subjectAltName
```

The DNS SAN must match the hostname used by the client.

### KEPServer cannot validate the broker

```text
unable to find valid certification path to requested target
```

Import `ca.crt` into the Windows Local Computer Trusted Root Certification Authorities store.

### Session taken over

Give every MQTT client a unique Client ID.

### Password file cannot be opened

```bash
sudo chown mosquitto:mosquitto /etc/mosquitto/passwd
sudo chmod 600 /etc/mosquitto/passwd
```

### Supplied broker and KEPServer diagnostic images

![Mosquitto terminal output showing a listener and TLS connection errors](images/Code_Generated_Image%20%283%29.png)

*Broker diagnostic output includes TLS unexpected-EOF errors. It also shows manual process commands; use the systemd commands in this tutorial to manage the service.*

![KEPServer tags and event log reference](images/Gemini_Generated_Image_d8lckdd8lckdd8lc.jpeg)

*Supplied KEPServer reference image showing tag configuration and connection/trust errors. The visible broker endpoint uses port 8887, whereas this tutorial uses 8883. The image contains a public EC2 hostname; review it before publishing. This image is not a clean acceptance-test result.*

<details>
<summary>Additional supplied KEPServer event-log image</summary>

![Alternative KEPServer tags and event log reference](images/Gemini_Generated_Image_qg0ydrqg0ydrqg0y.jpeg)

*An additional supplied variant of the event-log view. Some text appears altered; use the written configuration and actual runtime diagnostics as the authoritative reference.*

</details>

## 20. Repository structure

```text
secure-plc-opcua-mqtt-aws/
|-- README.md
|-- mosquitto/
|   `-- secure-mqtt.conf.example
|-- openssl/
|   `-- server.cnf.example
|-- python/
|   |-- publisher.py
|   |-- subscriber.py
|   `-- requirements.txt
|-- images/                 # supplied lab and reference images
|-- docs/
|   |-- README.md
|   `-- linkedin-post.md
`-- .gitignore
```

The supplied [.gitignore](.gitignore) excludes private keys, certificates, password files, local configs, and Python environments. Ignore rules do not protect secrets already tracked in Git. Review staged content before publishing. See [docs/README.md](docs/README.md) for the supplied image inventory and [the LinkedIn draft](docs/linkedin-post.md) for a short post.

### Acceptance checks

- `systemctl` reports Mosquitto active and port 8883 is listening.
- MQTTX validates the broker certificate using `ca.crt`; an incorrect password is rejected.
- The subscriber receives the Python `factory/test` payload.
- A PLC value change appears on `factory/plc1/data` with the expected tag and quality.
- A client with an untrusted CA or wrong hostname fails TLS verification.

Record your tested PLC/firmware, Ubuntu, Mosquitto, Kepware, MQTTX, and Python/Paho versions when running the lab. These end-to-end checks require your infrastructure and have not been executed as part of preparing these files.

Broker options are documented in the [Mosquitto configuration reference](https://mosquitto.org/man/mosquitto-conf-5.html).

## Result

The completed OT-to-cloud path is:

```text
Siemens PLC
→ OPC UA
→ KEPServerEX
→ MQTT/TLS
→ AWS EC2 Mosquitto
→ MQTT subscribers
```

Security is split into two mechanisms:

```text
TLS certificate
→ server identity + encryption

MQTT username/password
→ client authentication
```
