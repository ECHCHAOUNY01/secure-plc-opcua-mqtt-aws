# S7-1500 and KEPServerEX: OPC UA certificate trust

The S7-1500 is the OPC UA **server**. KEPServerEX uses its OPC UA **Client Driver** to read the PLC. Both applications have an application certificate and private key. Exchange only public certificates; each private key stays with its owner.

| Connection | Identity certificates | Where trust is configured |
| --- | --- | --- |
| PLC to KEPServer OPC UA | PLC server certificate and Kepware Client Driver certificate | PLC trusted clients and Kepware OPC UA trusted servers |
| KEPServer to Mosquitto MQTT/TLS | Mosquitto server certificate signed by the MQTT CA | IoT Gateway's supported trust store; Windows Local Computer roots for the documented KEPServerEX workflow |

Adding the MQTT CA to Windows does not perform the OPC UA trust exchange.

## 1. Create or select the PLC server certificate

In TIA Portal, select the S7-1500 CPU and open **Properties > OPC UA > Server**. Enable the OPC UA server and check its license requirements. Under **Security > Certificates**, select or generate the server application certificate. Enable project security/certificate management if your TIA version requires it. Confirm the certificate's validity dates and the PLC clock.

Use the certificate assigned to the PLC OPC UA server, rather than its web-server certificate. Export its public certificate in a format accepted by Kepware, such as DER `.der` or `.cer`. Compile/download the required hardware and security configuration during an appropriate lab maintenance window. Menu names vary with TIA version and firmware.

See [Siemens' S7-1500 OPC UA client example](https://support.industry.siemens.com/cs/attachments/109737901/109737901_OPC_UA_Client_S7-1500_DOKU_V1_5_en.pdf) for the server certificate and trusted-client configuration.

## 2. Trust the PLC in KEPServerEX

Open **OPC UA Configuration Manager** with administrator privileges. Under **Trusted Servers**, import the PLC's public OPC UA server certificate and verify its identity/fingerprint against the engineering source. This store is used by the OPC UA Client Driver. See [PTC: Trusted Servers](https://support.ptc.com/help/kepware/features/en/kepware/features/OPCUACONFIGMNGR/trusted-servers.html).

## 3. Trust the KEPServer client in the PLC

In the same manager, open **Instance Certificates** and use **Export client driver certificate** in the Client section. Export the Client Driver certificate, not the Kepware Server interface certificate. PTC documents these separate identities in [Instance Certificates](https://support.ptc.com/help/kepware/features/en/kepware/features/OPCUACONFIGMNGR/instance-certificates.html).

In TIA Portal, import this public certificate into the project certificate manager, then assign it to the CPU's OPC UA server **Trusted clients** list. Keep **Automatically accept all client certificates during runtime** disabled. Compile and download the changed security configuration to the CPU. Merely importing a certificate into the project without assigning/downloading it does not establish CPU trust. Follow the installed TIA version's workflow for certificate assignment.

## 4. Connect and verify

Create a Kepware OPC UA Client channel using the PLC's advertised endpoint. Choose a mutually supported policy, such as `Basic256Sha256` where supported, with **SignAndEncrypt**. Configure any required PLC username/password and read permissions separately; application certificate trust does not grant user permissions.

Browse the namespace, add tags, and check good quality and changing values in OPC Quick Client. Check both the Kepware event log and PLC diagnostics if the connection fails:

- Untrusted certificate: check both trust directions and the exact Client Driver identity.
- Invalid time: check certificate expiry and both clocks.
- Hostname/Application URI mismatch: correct the endpoint or issue the correct application certificate; do not bypass validation.
- Connection succeeds but reads fail: check exposed tags and user access rights.

Renewing/reissuing a directly trusted certificate requires updating the peer's trust entry.

## 5. Do I need a CA for OPC UA?

For this lab, directly trusting each application's self-signed certificate is sufficient; an OpenSSL CA is not required for the OPC UA leg. A CA is a certificate authority that signs other certificates. CA-based OPC UA deployments are a separate option requiring compatible certificate import and trust-chain support in the exact PLC firmware, TIA Portal, and Kepware versions.

For a CA-based deployment, create/use a dedicated OT CA on a protected engineering system, issue OPC UA application certificates with the correct Application URI and endpoint identities, install each application certificate with its matching private key using the vendor-supported procedure, and configure CA/issuer trust and any required revocation lists on both peers. Retain application/user authorization restrictions. Do not reuse the MQTT `server.cnf.example`: its server TLS profile is not an OPC UA application certificate profile. Version-specific issuance/import steps should be chosen after recording your TIA, CPU firmware, and Kepware versions.

## 6. Set up the MQTT CA used in this repository

The runnable OpenSSL commands are in [README sections 4-7](../README.md#4-create-the-ca):

1. Generate encrypted `ca.key` and self-signed `ca.crt` with CA constraints.
2. Generate a separate broker `server.key` and CSR using the EC2 DNS SAN in `openssl/server.cnf.example`.
3. Sign the CSR with the CA to produce `server.crt`; verify its SAN and chain.
4. Configure Mosquitto with the broker certificate/key, then distribute only `ca.crt` to MQTT clients.
5. Import that CA for IoT Gateway as described in README section 14. In MQTTX select the CA file; in Python set `MQTT_CA_FILE`.

On EC2, after issuing the certificate:

```bash
cd /etc/mosquitto/certs
openssl verify -CAfile ca.crt -purpose sslserver server.crt
openssl x509 -in server.crt -noout -dates -ext subjectAltName
```

Keep the CA signing key offline after issuance and keep the broker key private. The PLC and OPC UA client do not need the MQTT CA for their separate OPC UA connection.
