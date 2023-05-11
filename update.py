from pyzabbix import ZabbixAPI
import requests
import logging
import datetime
import paramiko
import time



date = datetime.datetime.now()
# Set up a connection to the Zabbix API
logging.basicConfig(filename='gwlog_v3.log', encoding='utf-8', level=logging.DEBUG)
zabbix_url = ""
zabbix_user = ""
zabbix_password = ""
zapi = ZabbixAPI(zabbix_url)
zapi.login(zabbix_user, zabbix_password)
logging.debug('Logged in at : ' + str(date))

# Declare the hostgroup here
gid = ""
# Declare the hostgroup for configuration failure
failed_gid = ""

# Get hosts from zabbix
hosts = zapi.host.get(output=["host", "interfaces"], groupids=gid, selectInterfaces=["ip"])
count = len(hosts)
failed_count = 0
active_count = 0
print(hosts) # debug ///////////////////////////////////////////////////////
print("########   Total hosts:  " + str(count) + "   ##########")
time_start = time.time()

# Iterate through each host retrieved
for host in hosts:
    active_count += 1
    host_time_start = time.time()
    hostname = host["host"][5:]
    hostid = host["hostid"]
    ip = host["interfaces"][0]["ip"] # Vessel ssh ip
    print(hostname + " " + ip) # debug ////////////////////////////////////
    url = "remote API" + hostname + ".json"
    print(url) # debug ///////////////////////////////////////////////////

    try:
        # Get JSON file
        response = requests.get(url)
        # If successful, iterate through each available GW
        if response.status_code == 200:

            # Set up the SSH client and connect to the remote host
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                print("Connecting to host...")  # debug /////////////////////////////////////////////
                client.connect(ip, username="", password="", timeout=60)
                # Create a new SSH channel and invoke a shell
                print("Connected! Invoking shell......") # debug ////////////////////////////////////
                channel = client.invoke_shell()
                channel.settimeout(60)
                print("Complete....") # debug ////////////////////////////////////
                # Edit mode
                channel.send("edit\n")
                time.sleep(2)
                print("Edit mode....")  # debug ////////////////////////////////////
                for interface in response.json()["interfaces"]["interfaces"]:
                    if interface["gateway"]:
                        print(interface["gateway"]) # debug/////////////////////

                        # Send the commands to the remote shell
                        channel.send("set security address-book global address " + interface["gateway"] + " " +
                            interface["gateway"] + "/32\n")
                        print("Added address....")  # debug ////////////////////////////////////
                        time.sleep(2)
                        channel.send("set security address-book global address-set White_NETs address " +
                            interface["gateway"] + "\n")
                        print("Whitelisted address....")  # debug ////////////////////////////////////
                        time.sleep(2)

                # Commit changes
                channel.send("commit\n")
                print("Committing changes....")  # debug ////////////////////////////////////

                # Wait for the commands to complete and collect the output
                output = ""
                while True:
                    try:
                        output += channel.recv(1024).decode("utf-8")
                    except Exception as e:
                        print(e)  # debug /////////////////////////////////////
                        break

                last_occurence = output.rfind("[edit]")
                second_last_occurence = output.rfind("#", 0, last_occurence)
                last_new_line_occurence = output.rfind("\n")
                command_output = output[second_last_occurence+8:last_occurence]


                print("Output:    ........  .........")
                print(command_output)


                # Close the SSH connection
                print("Closing channel....")  # debug ////////////////////////////////////
                channel.close()
                client.close()
                print("Complete!....")  # debug ////////////////////////////////////

                """ Remove from configuration_error group if needed"""
                if gid == failed_gid:
                    host = zapi.host.get(output=["hostid"], hostids=hostid, selectGroups="Extend")
                    # List with all group ids in order to update existing groups
                    existing_group_ids = [group["groupid"] for group in host[0]["groups"]]
                    existing_group_ids.remove(failed_gid)
                    # Update existing host, removed from configuration_error group
                    print("Updating inventory....")  # debug ////////////////////////////////////
                    # Update inventory Primary POC Notes with results
                    inventory = {"poc_1_notes": output,
                                 "poc_2_name": command_output}
                    print("Removing host from configuration_error group....")  # debug ///////////////////
                    zapi.host.update(hostid=hostid, inventory=inventory, inventory_mode=1,
                                     groups=[{"groupid": gid} for gid in existing_group_ids])
                    print("Complete!....")  # debug ////////////////////////////////////
                else:
                    # Update inventory Primary POC Notes with results
                    print("Updating inventory....")  # debug ////////////////////////////////////
                    inventory = {"poc_1_notes": output,
                                 "poc_2_name": command_output}
                    zapi.host.update(hostid=hostid, inventory=inventory, inventory_mode=1)
                    print("Complete!....")  # debug ////////////////////////////////////

            except Exception as e:
                print(e) # debug /////////////////////////////////////////////////////////
                # Add error message to poc 1 notes
                inventory = {"poc_1_notes": str(e)}
                # Retrieve host group information
                host = zapi.host.get(output=["hostid"], hostids=hostid, selectGroups="Extend")
                # List with all group ids in order to update existing groups
                existing_group_ids = [group["groupid"] for group in host[0]["groups"]]
                if failed_gid not in existing_group_ids:
                    existing_group_ids.append(failed_gid)
                # Update existing host, added to configuration_error group
                zapi.host.update(hostid=hostid, inventory=inventory, inventory_mode=1,
                                 groups=[{"groupid": grpid} for grpid in existing_group_ids])
                print("Updated host groups and inventory info.....")
                print("Added to configuration_error group....")
                failed_count += 1


        # Status code != 200 log event
        else:
            print(response.status_code)
            logging.warning("Status code: " + str(response.status_code))
            inventory = {"poc_1_notes": "Could not obtain JSON file: " + str(response.status_code)}
            # Retrieve host group information
            host = zapi.host.get(output=["hostid"], hostids=hostid, selectGroups="Extend")
            # List with all group ids in order to update existing groups
            existing_group_ids = [group["groupid"] for group in host[0]["groups"]]
            if failed_gid not in existing_group_ids:
                existing_group_ids.append(failed_gid)
            # Update existing host, added to configuration_error group
            zapi.host.update(hostid=hostid, inventory=inventory, inventory_mode=1,
                             groups=[{"groupid": grpid} for grpid in existing_group_ids])
            print("Updated host groups and inventory info.....")
            print("Added to configuration_error group....")
            failed_count += 1

    except Exception as e:
        print(e)
        # Update inventory primary poc notes in case of error
        inventory = {"poc_1_notes": "Could not obtain JSON file"}
        # Retrieve host group information
        host = zapi.host.get(output=["hostid"], hostids=hostid, selectGroups="Extend")
        # List with all group ids in order to update existing groups
        existing_group_ids = [group["groupid"] for group in host[0]["groups"]]
        if failed_gid not in existing_group_ids:
            existing_group_ids.append(failed_gid)
        # Update existing host, added to configuration_error group
        zapi.host.update(hostid=hostid, inventory=inventory, inventory_mode=1,
                         groups=[{"groupid": grpid} for grpid in existing_group_ids])
        print("Updated host groups and inventory info.....")
        print("Added to configuration_error group....")
        failed_count += 1

    host_time_needed = time.time() - host_time_start
    minutes = int(host_time_needed // 60)
    seconds = int(host_time_needed % 60)
    print("\n\n")
    print(f"Time needed: {minutes:02d}:{seconds:02d} ")
    print("\n\n")
    print("Completed so far: " + str(active_count) + " , of which failed: " + str(failed_count))
    print("\n\n")


time_needed = time.time() - time_start
hours = int(time_needed // 3600)
minutes = int((time_needed % 3600) // 60)
seconds = int(time_needed % 60)
print("\n\n")
print(f"Total time needed: {hours:02d}:{minutes:02d}:{seconds:02d} ")
