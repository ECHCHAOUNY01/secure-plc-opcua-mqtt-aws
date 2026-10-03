**From Siemens PLC data to a secure MQTT broker on AWS EC2**

I built an OT-to-cloud lab connecting:

**Siemens PLC → OPC UA → KEPServerEX → MQTT over TLS → AWS EC2 Mosquitto → MQTTX / Python**

The most useful part was learning how the security layers fit together: TLS verifies the broker's identity and encrypts traffic, while MQTT username/password authentication identifies clients.

The setup covers mutual OPC UA application-certificate trust between the S7-1500 and KEPServerEX, plus a separate private OpenSSL CA for MQTT/TLS, a server certificate with the correct DNS SAN, KEPServerEX IoT Gateway, and MQTTX and Python tests. Troubleshooting hostname mismatches, CA trust, password-file permissions, and duplicate Client IDs made it a valuable learning exercise.

I've documented the commands, configuration, and examples in a step-by-step GitHub tutorial.

GitHub: <YOUR_REPOSITORY_LINK>

#OPCUA #MQTT #KEPServerEX #AWS #IndustrialAutomation #OTSecurity #Python #IIoT
