This is Python implementation of the gateway.

After I was unable to figure out how to compose BLE adverisment frame with JS - I decided to rewrite in Python.

Unlike NodeJS implementation, this one talks to BlueZ using DBus.
That means we are not invoking exec() to set the advertisment every time.

But it comes with a major downside: You have to patch and recompile BlueZ.
By default Linux BlueZ would put flags at the end of the Advertising Payload, while iOS and Android would do flags in front of everything else.
Looks like Broadcom's firmware understands it only with flags being in the front, thus we need to modify BlueZ.

Please use **hack-ble-flags.patch** to compile BlueZ from source.

Credit goes to Moody https://github.com/moodyhunter/repo/blob/main/moody/bluez-ble-patched/hack-ble-flags.patch

Place **bluez-brmesh.conf** in /etc/dbus-1/system.d/ and replace 1000 with uid of the user you would be running the gateway under.


TODO: 
* Command queueing
  
