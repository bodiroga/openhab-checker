#! env python
import subprocess, datetime, os, time, urllib, json
from subprocess import check_output
from threading import Thread
from ConfigParser import ConfigParser
from library import telnet
import paho.mqtt.publish as mqtt_publish
import paho.mqtt.client as mqtt_client

import socket
socket.setdefaulttimeout(10)

############################################
################ PARAMETERS ################
############################################
service_name = "openhab_checker"
current_path = "/".join(os.path.realpath(__file__).split("/")[:-1])
configuration_file = "%s/configuration.ini" %current_path
logfile = "/var/log/openhab-checker.log"
global_variables = {}

def read_socat_log_file(file_path):
    try:
        with open(file_path) as f:
            return eval(f.read())
    except Exception as e:
        print e
        return None

def read_configuration():
    config = ConfigParser()
    config.read(configuration_file)
    for section in config.sections():
        for (variable, value) in config.items(section):
            final_variable = section+"_"+variable
            if "," in value: value = value.split(",")
            global_variables[final_variable] = value

def update_configuration(section, parameter, new_value):
    config = ConfigParser()
    config.read(configuration_file)
    config.set(section, parameter, new_value)
    log("[%s] The %s variable of %s has been changed to %s" %(datetime.datetime.now(), parameter, section, new_value))
    with open(configuration_file, 'w') as configfile:
        config.write(configfile)

def on_connect(client, userdata, flags, rc):
    client.subscribe(global_variables[service_name+'_suscribe_topic_prefix']+"/+")

def on_message(client, userdata, message):
    variable = message.topic.replace(global_variables[service_name+'_suscribe_topic_prefix'],'').replace('/','')
    try:
        global_variables[service_name+"_"+variable] = int(message.payload)
        update_configuration(service_name, variable, int(float(message.payload)))
    except:
        pass

def suscriberService():
    try:
        client = mqtt_client.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(global_variables['global_mqtt_broker_host'], 1883, 60)
        client.loop_forever()
    except:
        log("[%s] Error starting the mqtt suscriber service" %(datetime.datetime.now()))    

###########################################
########### Auxiliary functions ###########
###########################################
def get_pid(name):
    try:
        pidof_result = check_output(["pidof",name])
        return map(int,pidof_result.split())
    except:
        return dict()


def get_uninitialized_zwave_ports():
    uninitialized_ports = []
    for zwave in global_variables[service_name+"_zwave_ports"]:
        path = global_variables[service_name+"_socat_log_path"] + zwave
        if not os.path.exists(path):
            uninitialized_ports.append(zwave)
    return uninitialized_ports

def start_thermoaulas(delay_time):
    global status_ok
    time.sleep(delay_time)
    if status_ok:
        log("[%s] Starting Thermoaulas ..." %(datetime.datetime.now()))
        subprocess.call("/etc/init.d/thermoaulas start", shell=True)

def start_zwave_checker(delay_time):
    global status_ok
    time.sleep(delay_time)
    if status_ok:
        log("[%s] Starting Zwave checker ..." %(datetime.datetime.now()))
        subprocess.call("/etc/init.d/zwave_checker start", shell=True)

def start_all_threads():
    enabled_services = global_variables[service_name+"_enabled_services"]
    if "process" in enabled_services: t_process = Thread(target=check_unique_process).start()
    if "connectivity" in enabled_services: t_connectivity = Thread(target=check_connectivity, args=(global_variables["global_openhab_url"], 1, 4)).start()
    if "events" in enabled_services: t_events = Thread(target=check_events_log).start()
    if "socat" in enabled_services: t_socat = Thread(target=check_socat_log_files).start()        
    if "notifications" in enabled_services: t_mqtt = Thread(target=suscriberService).start()

def log(what):
    f = open(logfile,"a")
    f.write(what)
    f.write("\n")
    f.close()

def touch_persistence_files():
    try:
        persistence_folder = global_variables["global_openhab_path"] + "/configurations/persistence/"
        for persistence_file in os.listdir(persistence_folder):
            if persistence_file.lower().endswith('.persist'):
                persistence_file_path = persistence_folder+persistence_file
                touch_command = "touch %s" % (persistence_file_path)
                response = subprocess.check_output(touch_command, shell=True)
    except:
        log("[%s] Error touching the persistence files" % (datetime.datetime.now()))

def send_openhab_notification_message(message):
    try:
        payload = {}
        payload["time"] = str(datetime.datetime.now())
        payload["message"] = str(message)    
        payload_json = json.dumps(payload)
        mqtt_publish.single(global_variables[service_name+"_openhab_notification_topic"],payload_json)    
    except:
        log("[%s] Error sending a mqtt message" % (datetime.datetime.now()))        


################
## Test 0: Check if openhab has a unique process
################
def check_unique_process():
    global status_ok, process_error
    while status_ok:
        lista = get_pid("java")
        if len(lista) != 1:
            log("     ... Zero or more than one process detected: <%s>...     " %(str(len(lista))))
            process_error = True
            status_ok = False
            return
        time.sleep(float(global_variables[service_name+'_unique_process_check_interval']))


################
## Test 1: Check openhab is alive
#################
def check_connectivity(url, retries, max_retries):
    global status_ok, connectivity_error
    if not status_ok: return
    if retries >= max_retries:
        connectivity_error = True
        status_ok = False
        return
    else:
        try:
            req = urllib.urlopen(url)
            if retries > 1:
                log("     ... False alarm, the connectivity is fine ...     ")
            time.sleep(float(global_variables[service_name+'_connectivity_check_interval']))
            check_connectivity(url, 1, 4)
        except:
            log("     ... Can't connect to " + url + " ... " + str(retries) + " try ...     ")
	    time.sleep(float(global_variables[service_name+'_connectivity_retry_interval']))
	    retries += 1
	    check_connectivity(url, retries, max_retries)


###############
## Test 2: Is the events log file being updated?
###############
def check_events_log():
    global status_ok, events_error
    hang_time = int(1.5*float(global_variables[service_name+'_events_log_check_interval']))
    last_check_time = datetime.datetime.now()
    while status_ok:
        try:
            t = os.path.getmtime("%s/events.log" % "/var/log/openhab")
            modification_date = datetime.datetime.fromtimestamp(t)
            now_time = datetime.datetime.now()
            elapsed_time = now_time - modification_date
            check_difference_time = now_time - last_check_time
            if (elapsed_time.days > 0 or elapsed_time.seconds > int(global_variables[service_name+'_events_log_timeout'])) and check_difference_time.seconds >= hang_time:
                log("[%s]     ... The events.log file has a fake error: %s seconds but %s seconds hang ...     " % (datetime.datetime.now(), elapsed_time.seconds, check_difference_time.seconds))
            if elapsed_time.days > 0 and check_difference_time.seconds < hang_time:
                log("[%s]     ... The events.log file was updated %s days ago ...     " % (datetime.datetime.now(),elapsed_time.days))
                events_error = True
                status_ok = False
                return
            elif elapsed_time.seconds > int(global_variables[service_name+'_events_log_timeout']) and check_difference_time.seconds < hang_time:
                log("[%s]     ... The events.log file was updated %s seconds ago ...     " % (datetime.datetime.now(),elapsed_time.seconds))
                events_error = True
                status_ok = False
                return
            last_check_time = datetime.datetime.now()
            time.sleep(float(global_variables[service_name+'_events_log_check_interval']))
        except:
            log("     ... There is no events.log file ...     ")
            events_error = True
            status_ok = False
            return


###############
## Test 3: Control socat log files
###############
def check_socat_log_files():
    time.sleep(15)
    enabled_services = global_variables[service_name+"_enabled_services"]
    hang_time = 15
    pi_disconnection_time = 60
    global status_ok
    death_ports = []

    try:
        bundles_info = telnet.getZwaveBundlesInfo()
        info = bundles_info
        for socat_log in global_variables[service_name+"_socat_log_files"]:
            socat_log_path = global_variables[service_name+"_zwave_ports_path"]+socat_log
            file_content = read_socat_log_file(socat_log_path)
            corresponding_zwave = file_content["zwave_binding"]
            for key, value in file_content.iteritems():
                info[corresponding_zwave][key] = value
            info[corresponding_zwave]["last_check"] = datetime.datetime.now()
            info[corresponding_zwave]["last_stop"] = datetime.datetime.now()
            info[corresponding_zwave]["last_start"] = datetime.datetime.now()
    except:
        pass

    while status_ok:
        try:
            for socat_log in global_variables[service_name+"_socat_log_files"]:
                socat_log_path = global_variables[service_name+"_zwave_ports_path"]+socat_log
                file_time = datetime.datetime.fromtimestamp(os.path.getmtime(socat_log_path))
                now_time = datetime.datetime.now()
                file_content = read_socat_log_file(socat_log_path)
                if not file_content: continue
                corresponding_zwave = file_content["zwave_binding"]
                zwave_stick_ok = file_content["zwave_stick_status"]
                last_check_time = info[corresponding_zwave]["last_check"]
                difference_time = now_time - file_time
                difference_time_seconds = difference_time.seconds
                difference_time_days = difference_time.days
                check_difference_time = now_time - last_check_time
                if (difference_time.days > 0 or difference_time_seconds > pi_disconnection_time) and check_difference_time.seconds > hang_time :
                    log("[%s] The %s raspberry pi (%s) has a fake disconnection problem: %s seconds but %s seconds hang" % (datetime.datetime.now(), corresponding_zwave, socat_log.replace(".log",""), difference_time_seconds, check_difference_time.seconds))
                if ((difference_time.days > 0 or difference_time.seconds > pi_disconnection_time) and check_difference_time.seconds <= hang_time) or not zwave_stick_ok:
                    if socat_log not in death_ports:
                        death_ports.append(socat_log)
                        corresponding_bundle_id = bundles_info[corresponding_zwave]["id"]
                        log("[%s] The %s raspberry pi (%s) is dead (d: %s, s: %s, c_s: %s, z: %s)" % (datetime.datetime.now(), corresponding_zwave, socat_log.replace(".log",""), difference_time_days, difference_time_seconds, check_difference_time.seconds, zwave_stick_ok))
                        if "notifications" in enabled_services: send_openhab_notification_message("La raspberry pi %s (%s) no se comunica con el servidor" % (corresponding_zwave, socat_log.replace(".log","")))
                        telnet.stopBundleByID(corresponding_bundle_id)
                        info[corresponding_zwave]["last_stop"] = datetime.datetime.now()
                elif check_difference_time.seconds <= hang_time and socat_log in death_ports:
                    death_ports.remove(socat_log)
                    corresponding_bundle_id = bundles_info[corresponding_zwave]["id"]
                    log("[%s] The %s raspberry pi (%s) is recovered" %(datetime.datetime.now(), corresponding_zwave, socat_log.replace(".log","")))
                    if "notifications" in enabled_services: send_openhab_notification_message("La raspberry pi %s (%s) ha reestablecido su conexion con el servidor" % (corresponding_zwave, socat_log.replace(".log","")))
                    time.sleep(12)
                    telnet.startBundleByID(corresponding_bundle_id)
                    info[corresponding_zwave]["last_start"] = datetime.datetime.now()
                info[corresponding_zwave]["last_check"] = datetime.datetime.now()
            time.sleep(4)
        except Exception as e:
            log("[%s] Pi checker error: %s " %(datetime.datetime.now(), e))


        
################
## Restart openhab
###############     
def restart_openhab():
    global status_ok, uninitialized_zwave_ports
    enabled_services = global_variables[service_name+"_enabled_services"]

    if "notifications" in enabled_services: send_openhab_notification_message("Openhab se ha caido a las %s" % (datetime.datetime.now()))

    # Stop thermoaulas
    try:
        if "thermoaulas" in enabled_services: subprocess.call("/etc/init.d/thermoaulas stop", shell=True)
    except:
        log("[%s] Error killing thermoaulas" %(datetime.datetime.now()))

    # Stop zwave_checker        
    try:
        if "zwave_checker" in enabled_services: subprocess.call("/etc/init.d/zwave_checker stop", shell=True)   
    except:
        log("[%s] Error killing zwave_checker" %(datetime.datetime.now()))

    # Kill openhab
    try:
        log("[%s] Killing openhab" %(datetime.datetime.now()))
        lista_pids = get_pid("java")
        for pid in lista_pids:
            for i in range(0,3):
                command = "kill -9 " + str(pid)  + " 2> /dev/null"
                time.sleep(2)
                subprocess.call(command, shell=True)
    except:
        log("[%s] Error killing openhab" %(datetime.datetime.now()))
           
    # Check if zwave ports are ready
    if "socat" in enabled_services:
        wait_time = 0
        uninitialized_zwave_ports = get_uninitialized_zwave_ports()
        while uninitialized_zwave_ports:
            if wait_time > int(global_variables[service_name+"_zwave_ports_timeout"]):
                log( "     ... We have waited %s seconds for the pis, but %s is/are not available ...     " %(wait_time, ', '.join(uninitialized_zwave_ports)))
                if "notifications" in enabled_services: send_openhab_notification_message("Las raspberry pis %s no estan disponibles en este momento" % (', '.join(uninitialized_zwave_ports)))
                break
            if wait_time % 30 == 0:
                log("     ... The zwave ports are not ready yet ... %s/%s seconds     " %(wait_time, global_variables[service_name+'_zwave_ports_timeout']))
            wait_time = wait_time + 10
            time.sleep(10)
            uninitialized_zwave_ports = get_uninitialized_zwave_ports()

    # Launch openhab...
    try:
        log("[%s] Launching openhab" %(datetime.datetime.now()))
        command = "/etc/init.d/openhab restart"
        subprocess.call(command, shell=True)
    except:
        log("[%s] Error launching openhab" %(datetime.datetime.now()))
    time.sleep(120)
    status_ok = True
    if "notifications" in enabled_services: send_openhab_notification_message("Openhab se ha recuperado a las %" % (datetime.datetime.now()))
    log("[%s] Openhab correctly launched" %(datetime.datetime.now()))

    # Restart persistence files
    touch_persistence_files()

    # Restart thermoaulas
    thermoaulas_delay = float(global_variables[service_name+'_thermoaulas_start_delay'])
    if "thermoaulas" in enabled_services: Thread(target=start_thermoaulas, args=(thermoaulas_delay,)).start()
    if "zwave_checker" in enabled_services: Thread(target=start_zwave_checker, args=(thermoaulas_delay,)).start()


################
## Main thread
################
if __name__ == "__main__":    
    # Definition of the control variables
    status_ok = True
    process_error = False
    connectivity_error = False
    events_error = False
    
    log("[%s] Starting Openhab check service" %(datetime.datetime.now()))

    # Load the configuration file and start the configured threads
    read_configuration()
    start_all_threads()

    while True:
        try:
            if not status_ok:
                if process_error:
                    log("[%s] Zero or more than one Openhab process" %(datetime.datetime.now()))
                    restart_openhab()
                elif connectivity_error:
                    log("[%s] Openhab webserver is not responding" %(datetime.datetime.now()))
                    restart_openhab()
                elif events_error:
                    log("[%s] Openhab's event log is dead" %(datetime.datetime.now()))
                    restart_openhab()
                process_error = False
                connectivity_error = False
                events_error = False
                start_all_threads()
            time.sleep(2)
        except Exception as e:
            log("[%s] Checker error: %s " %(datetime.datetime.now(), e))
