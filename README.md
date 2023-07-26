# brMeshMQTT
This is a simple MQTT to brMesh (Broadlink Fastcon) gateway.
It is not a real-world ready app, just a proof of concept.

HomeAssistant video: https://youtu.be/gQ_EAsYz9jI

I have bought MELPO flood lights from Amazon and found they are based on some weird Broadlink mesh, with no direct control possible.
Special thanks goes to Moody for his initial research, read his blog here:
https://mooody.me/posts/2023-04/reverse-the-fastcon-ble-protocol/
(with translator)

To use this MQTT->brMesh gateway you first need to setup your devices, using Android phone.
Or at least the first one. When first device added - Android app generates unique Mesh key.
All subsequent devices would use this initial key.

It is possible to handle device registration directly, without an app, but it is outside the scope of this research/poc.

To get the key you need to run "adb logcat | grep jyq", send some commands and wait for a string like
```jyq_helper: getPayloadWithInnerRetry---> payload:220300000000000000000000,  key: b2fd16aa```

Where **b2fd16aa** would be your mesh key.
Second byte in the payload string is light's ID in the mesh, ID 3 in this case.

I have used Ubuntu Linux host with the following Realtek USB stick:

```2550:8761 Realtek Bluetooth Radio```

I have no idea if other adapters work.

This "gateway" would connect to your MQTT server and subscribe to **brMesh** topic.
Expected control messages are: brMesh/deviceId/set { json payload }

Examples:
```
brMesh/3/set { "state": "OFF" } 
brMesh/3/set { "state": "ON" } 
brMesh/3/set { "state": "ON", "color": {"r": 255,"g": 0,"b": 25} }
brMesh/3/set { "state": "ON", "color_temp": 500 }
brMesh/3/set { "state": "ON", "brightness": 40 }
```

To register light in HomeAssistant using MQTT, you can issue:

```
mosquitto_pub -h MQTT_SERVER_IP -t 'homeassistant/light/brMesh3/config' -m '{ "name":"brMesh3", "schema":"json", "command_topic":"brMesh/3/set", "rgb":"true", "brightness":"true", "optimistic":"true", "color_temp":"false","effect":"false",  "color_temp":"true"}'
```

All the above examples assume your LED light has ID 3.
All "temperature" settings, but the most left "warm white" are ignored.

For now we use shell invocation of **btmgmt** to set BLE advertising data and it really should be done in a nicer way, programmatically.
