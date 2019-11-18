import time
import os
import json
from flash_reader import FlashReader
from wifi.IWList import IWList

CONFIG_FILE = "/etc/flashconfig-wifi.json"
HOSTNAME_FILE = "/etc/hostname"
INTERFACES_FILE = "/etc/wpa_supplicant/wpa_supplicant.conf"
INTERFACES_FILE_TEMPLATE = os.path.dirname(os.path.realpath(__file__)) + "/wpa_supplicant.conf"

WPA_TEMPLATE = """
	ssid="%s"
	psk="%s"
	key_mgmt=WPA-PSK
"""

OPEN_TEMPLATE = """
	ssid="%s"
	key_mgmt=NONE
"""

class CommandHandler:
    def handle_input(self, input):
        msgtype = input[0]
        if msgtype == 0:
            self.handle_wifi(input)
        elif msgtype == 10:
            self.handle_command(input)

    def read_wifi_config(self):
        return json.load(file(CONFIG_FILE))
    
    def inspect_wifi_type(self, network):
        lister = IWList("wlan0", network)
        data = lister.getData()

        for cellId, cellData in data.items():
            if cellData["ESSID"] == network:
                print "found cell data", cellData
                if cellData["Encryption"] != "on":
                    return 'open'
                else:
                    if "WPA" in cellData["IE"]["IE"]:
                        return 'wpa'
                    else:
                        return 'wep'

        print "network not found:", network
        return None

    def reload_wifi(self):
        cstring = "ifdown wlan0"
        print "bringing down wlan0..."
        downtext = os.popen(cstring).read()

        time.sleep(5)

        print "bringing up wlan0..."
        cstring = "ifup wlan0"
        uptext = os.popen(cstring).read()
        
        print "network should be back up!"
        
        cstring = "hostname --file /etc/hostname"
        hntext = os.popen(cstring).read()
        
        print "hostname set!"

    def set_new_wifi(self, network, password, hostname):
        f = open(CONFIG_FILE, 'w')
        f.write(json.dumps({'network': network, 'password': password, 'hostname': hostname}))
        f.close()

        wifiDetails = None

        wifiType = self.inspect_wifi_type(network)
        if wifiType is 'wpa':
            wifiDetails = WPA_TEMPLATE % (network, password)
        elif wifiType is 'open':
            wifiDetails = OPEN_TEMPLATE % (network)
        
        if wifiDetails is not None:
            template = open(INTERFACES_FILE_TEMPLATE).read()
            f = open(INTERFACES_FILE, "w")
            f.write(template % (wifiDetails))
            f.close()
            if len(hostname) > 0:
              f = open(HOSTNAME_FILE, "w")
              f.write(hostname + "\n")
              f.close()
            self.reload_wifi()

    def confirm_up(self, key):
        num_tries = 10
        while num_tries > 0:
          num_tries -= 1
          cstring = "hostname -I"
          iptext = os.popen(cstring).read()
          iplist = [ip for ip in iptext.split(' ') if len(ip) < 16]
          if len(iplist) > 0:
            cstring = "curl --connect-timeout 3 -X POST http://stds.zamfi.net/%s?%s" % (key, "IP%20"+'%20'.join(iplist))
            confirmtext = os.popen(cstring).read()
            if confirmtext.strip() == 'ok':
              return
          time.sleep(5)

    def update_wifi(self, network, password, hostname, key):
        print "setting wifi with", network, password, hostname, key
        self.set_new_wifi(network, password, hostname)
        self.confirm_up(key)
            
    def handle_wifi(self, input):
        print "handling wifi on", input
        networkLen = input[1]
        networkIndex = 2
        network = bytearray(input[networkIndex:networkIndex+networkLen]).decode('utf-8').strip()
        passwordLen = input[networkIndex+networkLen+1]
        passwordIndex = networkIndex+networkLen+2
        password = bytearray(input[passwordIndex:passwordIndex+passwordLen]).decode('utf-8').strip()
        hostnameLen = input[passwordIndex+passwordLen+1]
        hostnameIndex = passwordIndex+passwordLen+2
        hostname = bytearray(input[hostnameIndex:hostnameIndex+hostnameLen]).decode('utf-8').strip()
        keyLen = input[hostnameIndex+hostnameLen+1]
        keyIndex = hostnameIndex+hostnameLen+2
        key = bytearray(input[keyIndex:keyIndex+keyLen]).decode('utf-8')

        self.update_wifi(network, password, hostname, key)
        

    def handle_command(self, input):
        command = bytearray(input[2:2+input[1]]).decode('utf-8')
        if command == "shutdown":
            os.popen("shutdown -h now")

    def listen(self, inputPin):
        def handle_input(bytes):
            self.handle_input(bytes)

        self.reader = FlashReader(inputPin, handle_input)

if __name__ == "__main__":
    ch = CommandHandler()
    ch.listen(26)

    print "Listening..."

    while True:
        time.sleep(1)
