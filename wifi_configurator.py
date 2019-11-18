import time
import os
import json
from flash_reader import FlashReader
from wifi.IWList import IWList

CONFIG_FILE = "/etc/flashconfig-wifi.json"
INTERFACES_FILE = "/etc/network/interfaces"
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
        if msgtype == 1:
            self.handle_wifi(input)
        elif msgtype == 3:
            self.handle_command(input)

    def read_wifi_config(self):
        return json.load(file(CONFIG_FILE))
    
    def inspect_wifi_type(self, network):
        lister = IWList("wlan0", network)
        data = lister.getData()

        for cellId, cellData in data.items():
            if cellData["ESSID"] == network:
                # print "found cell data", cellData
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

        print "bringing up wlan0..."
        cstring = "ifup wlan0"
        uptext = os.popen(cstring).read()
        
        print "network should be back up!"

    def set_new_wifi(self, network, password):
        f = open(CONFIG_FILE, 'w')
        f.write(json.dumps({'network': network, 'password': password}))
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
            self.reload_wifi()

    def update_wifi(self, network, password):
        print "setting wifi with", network, password
        self.set_new_wifi(network, password)
            
    def handle_wifi(self, input):
        print "handling wifi on", input
        networkLen = input[1]
        network = bytearray(input[2:networkLen+2]).decode('utf-8')
        passwordLen = input[networkLen+3]
        password = bytearray(input[networkLen+4:networkLen+4+passwordLen]).decode('utf-8')
        self.update_wifi(network, password)
        

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
