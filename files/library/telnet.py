#!/usr/bin/python
import re
import subprocess

host = "127.0.0.1"
port = 5555
telnet_delay = ".3"

def getZwaveBundlesInfo():
    command = "{ echo 'ss'; sleep %s; } | telnet %s %s" % (telnet_delay, host, port)
    ss_response = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True).stdout.read()
    
    zwave_info_search = re.compile(ur'(\d{2,4})\s+(\w+)\s+org.openhab.binding.(zwave\d*)')
    zwave_info = re.findall(zwave_info_search, ss_response)

    json = {}
    for result in zwave_info:
        json[result[2]] = { "id":result[0] , "status":result[1] }

    return json

def startBundleByID(bundle_id):
    command = "{ echo 'start %s'; sleep %s; } | telnet %s %s" % (bundle_id, telnet_delay, host, port)
    start_response = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True).stdout.read()
    return start_response

def stopBundleByID(bundle_id):
    command = "{ echo 'stop %s'; sleep %s; } | telnet %s %s" % (bundle_id, telnet_delay, host, port)
    start_response = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True).stdout.read()
    return start_response
