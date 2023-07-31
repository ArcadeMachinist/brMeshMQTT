from __future__ import print_function

my_mqtt_server = "10.42.42.2"            # Your MQTT server IP
my_key = [0xaa, 0xbb, 0xcc, 0xdd]        # See README how to get your secret key
default_key = [0x5e, 0x36, 0x7b, 0xc4]   
DEFAULT_BLE_FASTCON_ADDRESS = [0xC1, 0xC2, 0xC3]
BLE_CMD_RETRY_CNT = 1;
BLE_CMD_ADVERTISE_LENGTH = 3000; 
SEND_COUNT = 1;
SEND_SEQ = 0;

# Nothing interesting below this line

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
import array
import threading
import time
import asyncio

try:
  from gi.repository import GObject  # python3
  from gi.repository import GLib
except ImportError:
  import gobject as GObject  # python2
from random import randint
import paho.mqtt.client as mqtt
import json

mainloop = None
BLUEZ_SERVICE_NAME = 'org.bluez'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'

# Bluez stuff
class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'
class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'
class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotPermitted'
class InvalidValueLengthException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.InvalidValueLength'
class FailedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.Failed'
class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'
    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids = None
        self.manufacturer_data = None
        self.solicit_uuids = None
        self.service_data = None
        self.local_name = None
        self.include_tx_power = None
        self.data = None
        self.discoverable = None
        dbus.service.Object.__init__(self, bus, self.path)
    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        if self.service_uuids is not None:
            properties['ServiceUUIDs'] = dbus.Array(self.service_uuids,
                                                    signature='s')
        if self.solicit_uuids is not None:
            properties['SolicitUUIDs'] = dbus.Array(self.solicit_uuids,
                                                    signature='s')
        if self.manufacturer_data is not None:
            properties['ManufacturerData'] = dbus.Dictionary(
                self.manufacturer_data, signature='qv')
        if self.service_data is not None:
            properties['ServiceData'] = dbus.Dictionary(self.service_data,
                                                        signature='sv')
        if self.local_name is not None:
            properties['LocalName'] = dbus.String(self.local_name)
        if self.include_tx_power is not None:
            properties['IncludeTxPower'] = dbus.Boolean(self.include_tx_power)
        if self.discoverable is not None:
            properties['Discoverable'] = dbus.Boolean(self.discoverable);
        if self.data is not None:
            properties['Data'] = dbus.Dictionary(
                self.data, signature='yv')
        return {LE_ADVERTISEMENT_IFACE: properties}
    def get_path(self):
        return dbus.ObjectPath(self.path)
    def add_service_uuid(self, uuid):
        if not self.service_uuids:
            self.service_uuids = []
        self.service_uuids.append(uuid)
    def add_solicit_uuid(self, uuid):
        if not self.solicit_uuids:
            self.solicit_uuids = []
        self.solicit_uuids.append(uuid)
    def add_manufacturer_data(self, manuf_code, data):
        if not self.manufacturer_data:
            self.manufacturer_data = dbus.Dictionary({}, signature='qv')
        self.manufacturer_data[manuf_code] = dbus.Array(data, signature='y')
    def add_service_data(self, uuid, data):
        if not self.service_data:
            self.service_data = dbus.Dictionary({}, signature='sv')
        self.service_data[uuid] = dbus.Array(data, signature='y')
    def add_local_name(self, name):
        if not self.local_name:
            self.local_name = ""
        self.local_name = dbus.String(name)
    def add_data(self, ad_type, data):
        if not self.data:
            self.data = dbus.Dictionary({}, signature='yv')
        self.data[ad_type] = dbus.Array(data, signature='y')
    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        print('GetAll')
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        print('returning props')
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]
    @dbus.service.method(LE_ADVERTISEMENT_IFACE,
                         in_signature='',
                         out_signature='')
    def Release(self):
        print('%s: Released!' % self.path)


class brMeshAdvertisement(Advertisement):
    def __init__(self, bus, index, mdata):
        print("Init adv")
        Advertisement.__init__(self, bus, index, 'peripheral')
        #self.add_data(0x27, [0xff])
        self.add_manufacturer_data(0xfff0, mdata)
        self.discoverable = True

def register_ad_cb():
    print('Advertisement registered')
def register_ad_error_cb(error):
    print('Failed to register advertisement: ' + str(error))
    mainloop.quit()
def find_adapter(bus):
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                               DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()
    for o, props in objects.items():
        if LE_ADVERTISING_MANAGER_IFACE in props:
            return o
    return None


# brMesh stuff

def reverse_8(d):
    result = 0
    for k in range(8):
        result |= ((d >> k) & 1) << (7 - k)
    return result

def reverse_16(d):
    result = 0
    for k in range(16):
        result |= ((d >> k) & 1) << (15 - k)
    return result

def crc16(addr, data):
    crc = 0xFFFF

    for i in range(len(addr) - 1, -1, -1):
        crc ^= addr[i] << 8
        for _ in range(4):
            tmp = crc << 1

            if crc & 0x8000 != 0:
                tmp ^= 0x1021

            crc = tmp << 1
            if tmp & 0x8000 != 0:
                crc ^= 0x1021

    for i in range(len(data)):
        crc ^= reverse_8(data[i]) << 8
        for _ in range(4):
            tmp = crc << 1

            if crc & 0x8000 != 0:
                tmp ^= 0x1021

            crc = tmp << 1
            if tmp & 0x8000 != 0:
                crc ^= 0x1021

    crc = (~reverse_16(crc)) & 0xFFFF
    return crc

def get_payload_with_inner_retry(i, data, i2, key, forward, use_22_data):
    global SEND_COUNT, SEND_SEQ
    SEND_COUNT += 1
    SEND_SEQ = SEND_COUNT & 0xff
    safe_key = 0xff
    if key[0] == 0 or key[1] == 0 or key[2] == 0 or key[3] == 0:
        pass
    else:
        safe_key = key[3]
    if use_22_data:
        print("Ooops! use_22_data")
        return -1
    else:
        return package_ble_fastcon_body(i, i2, SEND_SEQ, safe_key, forward, data, key)

def package_ble_fastcon_body(i, i2, sequence, safe_key, forward, data, key):
    body = []
    body.append((i2 & 0b1111) | ((i & 0b111) << 4) | ((forward & 0xff) << 7))
    body.append(sequence & 0xff)
    body.append(safe_key)
    body.append(0)  # checksum (temporary placeholder)

    body += data

    checksum = 0
    for j in range(len(body)):
        if j == 3:
            continue
        checksum = (checksum + body[j]) & 0xff

    body[3] = checksum

    # pad payload with zeros
    for j in range(12 - len(data)):
        body.append(0)

    for j in range(4):
        body[j] = default_key[j & 3] ^ body[j]

    for j in range(12):
        body[4 + j] = my_key[j & 3] ^ body[4 + j]

    return body

def get_rf_payload(addr, data):
    data_offset = 0x12
    inverse_offset = 0x0f
    result_data_size = data_offset + len(addr) + len(data)
    resultbuf = [0] * (result_data_size + 2)

    # some hardcoded values
    resultbuf[0x0f] = 0x71
    resultbuf[0x10] = 0x0f
    resultbuf[0x11] = 0x55
    
    print("")
    print("get_rf_payload")
    print("------------------------")
    print("addr:", bytes(addr).hex())
    print("data:", bytes(data).hex())

    # reverse copy the address
    for i in range(len(addr)):
        resultbuf[data_offset + len(addr) - i - 1] = addr[i]

    resultbuf[data_offset + len(addr):data_offset + len(addr) + len(data)] = data[:]

    for i in range(inverse_offset, inverse_offset + len(addr) + 3):
        resultbuf[i] = reverse_8(resultbuf[i])

    print("inverse_offset:", inverse_offset)
    print("inverse_offset addr.len + 3:", (inverse_offset + len(addr) + 3))

    crc = crc16(addr, data)
    resultbuf[result_data_size] = crc & 0xFF
    resultbuf[result_data_size + 1] = (crc >> 8) & 0xFF
    return resultbuf


def whitening_init(val, ctx): 
    v0 = [(val >> 5) & 1, (val >> 4) & 1, (val >> 3) & 1, (val >> 2) & 1]
    ctx[0] = 1
    ctx[1] = v0[0]
    ctx[2] = v0[1]
    ctx[3] = v0[2]
    ctx[4] = v0[3]
    ctx[5] = (val >> 1) & 1
    ctx[6] = val & 1

def whitening_encode(data, ctx):
    result = list(data)
    for i in range(len(result)):
        varC = ctx[3]
        var14 = ctx[5]
        var18 = ctx[6]
        var10 = ctx[4]
        var8 = var14 ^ ctx[2]
        var4 = var10 ^ ctx[1]
        _var = var18 ^ varC
        var0 = _var ^ ctx[0]

        c = result[i]
        result[i] = ((c & 0x80) ^ ((var8 ^ var18) << 7)) & 0xFF
        result[i] += ((c & 0x40) ^ (var0 << 6)) & 0xFF
        result[i] += ((c & 0x20) ^ (var4 << 5)) & 0xFF
        result[i] += ((c & 0x10) ^ (var8 << 4)) & 0xFF
        result[i] += ((c & 0x08) ^ (_var << 3)) & 0xFF
        result[i] += ((c & 0x04) ^ (var10 << 2)) & 0xFF
        result[i] += ((c & 0x02) ^ (var14 << 1)) & 0xFF
        result[i] += ((c & 0x01) ^ (var18 << 0)) & 0xFF

        ctx[2] = var4
        ctx[3] = var8
        ctx[4] = var8 ^ varC
        ctx[5] = var0 ^ var10
        ctx[6] = var4 ^ var14
        ctx[0] = var8 ^ var18
        ctx[1] = var0

    return result    

def do_generate_command(i, data, key, _retry_count, _send_interval, forward, use_default_adapter, use_22_data, i2):

    i2_ = max(i2, 0)
    payload = get_payload_with_inner_retry(i, data, i2_, key, forward, use_22_data)

    payload = get_rf_payload(DEFAULT_BLE_FASTCON_ADDRESS, payload)

    whiteningContext = [0] * 7
    whitening_init(0x25, whiteningContext)
    payload = whitening_encode(payload, whiteningContext)
    payload = payload[0x0f:]
    return payload

def shutdown(timeout):
    print('Advertising for {} seconds...'.format(timeout))
    time.sleep(timeout)
    mainloop.quit()

def single_control(addr, key, data, delay):
    global mainloop
    # Implement your single_control function here
    # You can replace this function with your implementation to control the light
    print("Reached single_control: ", str(addr));
    result = []
    result.append(2 | (((0xFFFFFFF & (len(data) + 1)) << 4) & 0xFF))
    result.append(addr & 0xFF)
    result += data

    ble_adv_data = [] #[0x02, 0x01, 0x1A, 0x1B, 0xFF, 0xF0, 0xFF]
    ble_adv_cmd = ble_adv_data + do_generate_command(5,
                                                    result,
                                                    key,
                                                    BLE_CMD_RETRY_CNT,
                                                    BLE_CMD_ADVERTISE_LENGTH,
                                                    True,  # forward?
                                                    True,  # use_default_adapter
                                                    (addr > 256) & 0xFF,  # use_22_data
                                                    (addr // 256) & 0xFF  # i2
                                                    )
    print("Adv-Cmd          : btmgmt add-adv -d 02011a1bfff0ff" + bytes(ble_adv_cmd).hex() + " 1")

    # BlueZ party time
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter = find_adapter(bus)
    if not adapter:
        print('LEAdvertisingManager1 interface not found')
        return
    adapter_props = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                   "org.freedesktop.DBus.Properties");
    adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))
    ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                LE_ADVERTISING_MANAGER_IFACE)
    br_advertisement = brMeshAdvertisement(bus, 0, ble_adv_cmd)
    mainloop = GLib.MainLoop()
    ad_manager.RegisterAdvertisement(br_advertisement.get_path(), {},
                                     reply_handler=register_ad_cb,
                                     error_handler=register_ad_error_cb)

    threading.Thread(target=shutdown, args=(0.1,)).start()
    mainloop.run()
    ad_manager.UnregisterAdvertisement(br_advertisement)
    print('Advertisement unregistered')
    dbus.service.Object.remove_from_connection(br_advertisement)


# Our Light class
class Light:
    def __init__(self, mesh_key, device_id):
        self.id = int(device_id)
        self.key = mesh_key

    def setOnOff(self, on, brightness):
        print("brightness:", str(brightness))
        command = [0] * 1
        command[0] = 0
        if on:
            command[0] = 128 + (int(brightness) & 127)
        single_control(self.id, self.key, command, 0)

    def Brightness(self, on, brightness):
        command = [0] * 1
        command[0] = 0
        if on:
            command[0] = int(brightness) & 127
        threading.Thread(target=single_control, args=(self.id, self.key, command, 0), kwargs={}).start()
       # single_control(self.id, self.key, command, 0)

    def WarmWhite(self, on, brightness, i5, i6):
        command = [0] * 6
        command[0] = 0
        command[4] = i5 & 0xFF
        command[5] = i6 & 0xFF
        if on:
            command[0] = 128 + (int(brightness) & 127)
        single_control(self.id, self.key, command, 0)

    def Colored(self, on, brightness, r, g, b, abs):
        command = [0] * 6
        color_normalization = 1
        command[0] = 0
        if on:
            command[0] += 128
        command[0] += int(brightness) & 127
        if not abs:
            color_normalization = 255.0 / (r + g + b)
        command[1] = int((b * color_normalization) & 0xFF)
        command[2] = int((r * color_normalization) & 0xFF)
        command[3] = int((g * color_normalization) & 0xFF)
        single_control(self.id, self.key, command, 0)

def on_mqtt_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    client.subscribe("brMesh/#")

def on_mqtt_message(client, userdata, msg):
    print("Got message");
    print(msg.topic+" "+str(msg.payload))
    topic = msg.topic
    payload = msg.payload
    if "/" in topic:
        topic_talks = topic.split("/")
        print(topic_talks)
        if topic_talks[0] == "brMesh":
            light = topic_talks[1]
            if topic_talks[2] == "set":
                myLight = Light(my_key, int(light))
                brightness = 0
                print(payload.decode())
                payload = json.loads(payload.decode())
                print(payload)
                if "brightness" in payload:
                    # Map HA 3..255 brightness range to brMesh 1..127
                    nb = (payload["brightness"] - 3) * (127 - 1) / (255 - 3) + 1
                    print("nb: " + str(nb))
                    myLight.Brightness(1, nb)
                elif "color" in payload:
                    print("color")
                    myLight.Colored(1, brightness, payload["color"]["r"], payload["color"]["g"], payload["color"]["b"], True)
                elif "color_temp" in payload:
                    print("color_temp")
                    if payload["color_temp"] == 500:
                        print("color_temp_500")
                        myLight.WarmWhite(1, brightness, 127, 127)
                else:
                    if "state" in payload:
                        if payload["state"] == "ON":  # last state
                            print("ON")
                            myLight.setOnOff(1, brightness)
                        else:
                            print("OFF")
                            myLight.setOnOff(0, 0)

client = mqtt.Client()
client.on_connect = on_mqtt_connect
client.on_message = on_mqtt_message

client.connect(my_mqtt_server, 1883, 60)

client.loop_forever()
