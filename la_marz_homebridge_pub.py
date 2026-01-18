#!/usr/bin/env python3
#Northcliff La Marzocco mqtt Homebridge Manager - 0.6 pub
import asyncio
import json
import time
import logging
import uuid
from pathlib import Path
from datetime import datetime
import aiomqtt

from aiohttp import ClientSession

from pylamarzocco import LaMarzoccoCloudClient, LaMarzoccoMachine
from pylamarzocco.models import ThingDashboardWebsocketConfig
from pylamarzocco.util import InstallationKey, generate_installation_key

from dataclasses import dataclass, field
from typing import Dict, Any
import copy

#logging.basicConfig(level=logging.DEBUG,
logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(name)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s")
LOG = logging.getLogger(__name__)

@dataclass
class StateTracker: # Records previous states to only send homebridge updates upon state changes
    _state: Dict[str, Any] = field(default_factory=dict)
    def update(self, new_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update internal state and return changed values only.
        """
        changed = {
            key: value
            for key, value in new_state.items()
            if self._state.get(key) != value
        }
        # Deep copy protects against shared references
        self._state = copy.deepcopy(new_state)
        return changed

    def snapshot(self) -> Dict[str, Any]:
        return copy.deepcopy(self._state)

# Account Data
SERIAL = "<Your La Marzocco Machine's Serial Number"
USERNAME = "<Your La Marzocco Account User Name>"
PASSWORD = "<Your La Marzocco Account Password>"

# MQTT Broker Setup
MQTT_BROKER_IP_ADDRESS = "<Your mqtt Broker IP Address>"

# Tracked API Messages. All others ignored.
ALLOWED_KEYS = {"dashboard.widgets.0.output.mode", "dashboard.widgets.0.output.status","dashboard.widgets.1.output.status",
                "dashboard.widgets.1.output.target_temperature", "dashboard.widgets.2.output.status", "dashboard.widgets.2.output.target_level",
                "dashboard.widgets.3.output.times.pre_brewing.0.seconds.In", "dashboard.widgets.4.output.scale_connected",
                "dashboard.widgets.4.output.mode", "dashboard.widgets.4.output.doses.dose_1.dose",
                "dashboard.widgets.4.output.doses.dose_2.dose", "dashboard.widgets.6.output.status"}

# Map API fields to readable topics
TOPIC_MAP = {"dashboard.widgets.0.output.mode": "Coffee Brewing Mode", "dashboard.widgets.0.output.status": "Coffee Power",
             "dashboard.widgets.1.output.status": "Coffee Boiler State", "dashboard.widgets.1.output.target_temperature": "Coffee Temp",
             "dashboard.widgets.2.output.status": "Coffee Steam State", "dashboard.widgets.2.output.target_level": "Coffee Steam Level",
             "dashboard.widgets.3.output.times.pre_brewing.0.seconds.In": "Coffee Puck Prep Time",
             "dashboard.widgets.4.output.scale_connected": "Coffee BBW Connected", "dashboard.widgets.4.output.mode": "Coffee Dose",
             "dashboard.widgets.4.output.doses.dose_1.dose": "Coffee BBW 1", "dashboard.widgets.4.output.doses.dose_2.dose": "Coffee BBW 2",
             "dashboard.widgets.6.output.status": "Coffee Backflush"}

# Homebridge mqtt field formats
homebridge_coffee_power_format = {"name": "Coffee Power", "service_name": "Coffee Power", "characteristic": 'On'}
homebridge_coffee_steam_format = {"name": "Coffee Steam", "service_name": "Coffee Steam", "characteristic": 'On'}
homebridge_coffee_backflush_format = {"name": "Coffee Backflush", "service_name": "Coffee Backflush", "characteristic": 'On'}
homebridge_coffee_action_backflush_format = {"name": "Coffee Action Backflush", "service_name": "Coffee Action Backflush", "characteristic": 'MotionDetected'}
homebridge_coffee_dose1_format = {"name": "Coffee Dose 1", "service_name": "Coffee Dose 1", "characteristic": 'On'}
homebridge_coffee_dose2_format = {"name": "Coffee Dose 2", "service_name": "Coffee Dose 2", "characteristic": 'On'}
homebridge_coffee_continuous_format = {"name": "Coffee Continuous", "service_name": "Coffee Continuous", "characteristic": 'On'}
homebridge_coffee_steam1_format = {"name": "Coffee Steam 1", "service_name": "Coffee Steam 1", "characteristic": 'On'}
homebridge_coffee_steam2_format = {"name": "Coffee Steam 2", "service_name": "Coffee Steam 2", "characteristic": 'On'}
homebridge_coffee_steam3_format = {"name": "Coffee Steam 3", "service_name": "Coffee Steam 3", "characteristic": 'On'}
homebridge_coffee_current_temp_format = {"name": "Coffee Temp", "service_name": "Coffee Temp", "characteristic": 'CurrentTemperature'}
homebridge_coffee_target_temp_format = {"name": "Coffee Temp", "service_name": "Coffee Temp", "characteristic": 'TargetTemperature'}
homebridge_coffee_current_temp_state_format = {"name": "Coffee Temp", "service_name": "Coffee Temp", "characteristic": 'CurrentHeatingCoolingState'}
homebridge_coffee_target_temp_state_format = {"name": "Coffee Temp", "service_name": "Coffee Temp", "characteristic": 'TargetHeatingCoolingState'}
homebridge_coffee_current_bbw1_format = {"name": "Coffee BBW 1", "service_name": "Coffee BBW 1", "characteristic": 'CurrentTemperature'}
homebridge_coffee_target_bbw1_format = {"name": "Coffee BBW 1", "service_name": "Coffee BBW 1", "characteristic": 'TargetTemperature'}
homebridge_coffee_current_bbw1_state_format = {"name": "Coffee BBW 1", "service_name": "Coffee BBW 1", "characteristic": 'CurrentHeatingCoolingState'}
homebridge_coffee_target_bbw1_state_format = {"name": "Coffee BBW 1", "service_name": "Coffee BBW 1", "characteristic": 'TargetHeatingCoolingState'}
homebridge_coffee_current_bbw2_format = {"name": "Coffee BBW 2", "service_name": "Coffee BBW 2", "characteristic": 'CurrentTemperature'}
homebridge_coffee_target_bbw2_format = {"name": "Coffee BBW 2", "service_name": "Coffee BBW 2", "characteristic": 'TargetTemperature'}
homebridge_coffee_current_bbw2_state_format = {"name": "Coffee BBW 2", "service_name": "Coffee BBW 2", "characteristic": 'CurrentHeatingCoolingState'}
homebridge_coffee_target_bbw2_state_format = {"name": "Coffee BBW 2", "service_name": "Coffee BBW 2", "characteristic": 'TargetHeatingCoolingState'}
homebridge_coffee_boiler_ready_format = {"name": "Coffee Boiler Ready", "service_name": "Coffee Boiler Ready", "characteristic": 'MotionDetected'}
homebridge_coffee_steam_ready_format = {"name": "Coffee Steam Ready", "service_name": "Coffee Steam Ready", "characteristic": 'MotionDetected'}

# Map API readable topics to Homebridge mqtt field formats
MQTT_MAP = {"Coffee Power": [{"mqtt_map": homebridge_coffee_power_format, "value_map": {"PoweredOn": True, "Brewing": True, "StandBy": False, "Off": False}}],
            "Coffee Temp": [{"mqtt_map": homebridge_coffee_target_temp_format}, {"mqtt_map": homebridge_coffee_target_temp_state_format, "value": 1}],
            "Coffee Boiler State": [{"mqtt_map": homebridge_coffee_boiler_ready_format, "value_map": {"Ready": True, "HeatingUp": False, "StandBy": False, "NoWater": False}},
            {"mqtt_map": homebridge_coffee_current_temp_state_format, "value_map": {"Ready": 1, "HeatingUp": 1, "StandBy": 0, "NoWater": 0}}],
            "Coffee Steam State": [{"mqtt_map": homebridge_coffee_steam_format, "value_map": {"Ready": True, "Off": False, "StandBy": True, "HeatingUp": True, "NoWater": False}},
                                  {"mqtt_map": homebridge_coffee_steam_ready_format, "value_map": {"Ready": True, "Off": False, "StandBy": False, "HeatingUp": False, "NoWater": False}}],
            "Current Coffee Temp": [{"mqtt_map": homebridge_coffee_current_temp_format}],
            "Coffee BBW 1": [{"mqtt_map": homebridge_coffee_target_bbw1_format}, {"mqtt_map": homebridge_coffee_target_bbw1_state_format, "value": 1}],
            "Coffee BBW 2": [{"mqtt_map": homebridge_coffee_target_bbw2_format}, {"mqtt_map": homebridge_coffee_target_bbw1_state_format, "value": 1}],
            "Coffee Current BBW 1": [{"mqtt_map": homebridge_coffee_current_bbw1_format}],
            "Coffee Current BBW 2": [{"mqtt_map": homebridge_coffee_current_bbw2_format}],
            "Coffee Dose":[{"mqtt_map": homebridge_coffee_dose1_format, "value_map": {"Dose1": True, "Dose2": False, "Continuous": False}},
                           {"mqtt_map": homebridge_coffee_dose2_format, "value_map": {"Dose1": False, "Dose2": True, "Continuous": False}},
                           {"mqtt_map": homebridge_coffee_continuous_format, "value_map": {"Dose1": False, "Dose2": False, "Continuous": True}}],
            "Coffee Backflush":[{"mqtt_map": homebridge_coffee_backflush_format, "value_map": {"Off": False, "Requested": True, "Cleaning": True}},
                                {"mqtt_map": homebridge_coffee_action_backflush_format, "value_map": {"Off": False, "Requested": True, "Cleaning": False}}],
            "Coffee Steam Level":[{"mqtt_map": homebridge_coffee_steam1_format, "value_map": {"Level1": True, "Level2": False, "Level3": False}},
                           {"mqtt_map": homebridge_coffee_steam2_format, "value_map": {"Level1": False, "Level2": True, "Level3": False}},
                           {"mqtt_map": homebridge_coffee_steam3_format, "value_map": {"Level1": False, "Level2": False, "Level3": True}}]}

# Homebridge mqtt topics
hb_incoming_mqtt_topic = "homebridge/from/set" #Topic for messages from the Homebridge mqtt plugin
hb_outgoing_mqtt_topic = "homebridge/to/set" #Topic for messages to the Homebridge mqtt plugin

mqtt_publish_queue: asyncio.Queue = asyncio.Queue() # Creat a global publish queue

def print_update(print_message): # Prints with a date and time stamp
        today = datetime.now()
        print('')
        print(print_message + " on " + today.strftime('%A %d %B %Y @ %H:%M:%S'))

def flatten(obj, parent_key="", sep="."): # Flattens API messages
    items = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            items.update(flatten(v, new_key, sep))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            new_key = f"{parent_key}{sep}{i}"
            items.update(flatten(v, new_key, sep))
    else:
        items[parent_key] = obj
    return items

async def mqtt_publisher(): # MQTT publisher task
    async with aiomqtt.Client(MQTT_BROKER_IP_ADDRESS) as client:
        while True:
            topic, payload = await mqtt_publish_queue.get()
            try:
                await client.publish(topic, json.dumps(payload))
            except Exception as e:
                LOG.exception("MQTT publish failed")
            finally:
                mqtt_publish_queue.task_done()

def publish_homebridge(payload: dict): # Publish Homebridge mqtt message
    mqtt_publish_queue.put_nowait(
        (hb_outgoing_mqtt_topic, payload)
    )
        
def filter_topics(flat): # Filter out unwanted API messages
    return {
        topic: value
        for topic, value in flat.items()
        if topic in ALLOWED_KEYS
    }

def map_topics(flat): # Map filtered API messages to readable messages
    mapped = {}
    for topic, value in flat.items():
        mapped_topic = TOPIC_MAP.get(topic)
        if mapped_topic:
            mapped[mapped_topic] = value
    return mapped

def publish_mqtt_map(key, value): # Publish mapped Homebridge mqtt messages
    for message in MQTT_MAP[key]:
        parsed_json = {}
        parsed_json["name"] = message["mqtt_map"]["name"]
        parsed_json["service_name"] = message["mqtt_map"]["service_name"]
        parsed_json["characteristic"] = message["mqtt_map"]["characteristic"]
        if "value_map" in message:
            parsed_json["value"] = message["value_map"][value] # Use mapped values when available
        elif "value" in message:
            parsed_json["value"] = message["value"] # For constant single values
        else:
            parsed_json["value"] = value # For variable single values
        LOG.debug("Published mqtt Message to Homebridge " + str(parsed_json))
        publish_homebridge(parsed_json)

def update_homebridge(machine_dict: dict, tracker: StateTracker, phase): # Update Homebridge with any changed API states
    print_update(phase)
    flat = flatten(machine_dict)
    #print(json.dumps(flat, indent =2))
    mapped = map_topics(flat)
    target_temp = mapped["Coffee Temp"] # To match current temp to target temp when the boiler is ready
    bbw_1 = mapped["Coffee BBW 1"]
    bbw_2 = mapped["Coffee BBW 2"]
    #print(json.dumps(mapped, indent =2))
    #print(" ")
    changed = tracker.update(mapped)
    if not changed:
        print("No Changed States")
    else:
        print("Changed States:")
    for key in changed:
        value = changed[key]
        if key == "Coffee Power":
            if value == "StandBy":
                print("Coffee Power Off")
            elif value == "PoweredOn":
                print("Coffee Power On")
            publish_mqtt_map(key, value)
        elif key == "Coffee Brewing Mode": # No Homebridge update, just monitor
            if value == "StandBy":
                print("Coffee Brewing Standby")
            elif value == "BrewingMode":
                print("Coffee Brewing Ready")
        elif key == "Coffee Temp": # Set Target Temp control to same as machine brew temp and set to heat mode
            print("Coffee Temp: ", value)
            publish_mqtt_map(key, value)  
        elif key == "Coffee Steam State":
            if value == "Off":
                print("Coffee Steam Off")
            elif value == "Standby":
                print("Coffee Steam Standby")
            elif value == "HeatingUp":
                print("Coffee Steam Heating Up")
            elif value == "Ready":
                print("Coffee Steam Ready")
            elif value == "NoWater":
                print("Coffee Steam No Water")
            publish_mqtt_map(key, value)    
        elif key == "Coffee Steam Level":
            print("Coffee Steam Level: ", value)
            publish_mqtt_map(key, value)
        elif key == "Coffee Puck Prep Time": # No Homebridge update, just monitor
            print("Coffee Puck Prep Time: ", value)
        elif key == "Coffee Boiler State":
            if value == "StandBy":
                temp_value = 80
                print("Coffee Boiler Standby")
            elif value == "HeatingUp":
                temp_value = 80
                print("Coffee Boiler Heating Up")
            elif value == "NoWater":
                temp_value = 80
                print("Coffee Boiler No Water")
            elif value == "Ready":
                temp_value = target_temp
                print("Coffee Boiler On")
            publish_mqtt_map(key, value)
            publish_mqtt_map("Current Coffee Temp", temp_value) # Set current brew temp to target brew temp when the boiler is ready and 80 when it's not ready
        elif key == "Coffee BBW Connected":
            print("Coffee BBW Connected:", value)
            if value:
                bbw_1_value = bbw_1
                bbw_2_value = bbw_2
            else:
                bbw_1_value = 14
                bbw_2_value = 14
            publish_mqtt_map("Coffee Current BBW 1", bbw_1_value) # Set current BBW 1 to target weight when scale is connected and 14g when it's not connected
            publish_mqtt_map("Coffee Current BBW 2", bbw_2_value) # Set current BBW 2 to target weight when scale is connected and 14g when it's not connected
        elif key == "Coffee Dose":
            print("Coffee Dose:", value)
            publish_mqtt_map(key, value)
        elif key == "Coffee BBW 1":
            print("Coffee BBW 1 Weight:", value)
            publish_mqtt_map(key, value)
        elif key == "Coffee BBW 2":
            print("Coffee BBW 2 Weight:", value)
            publish_mqtt_map(key, value)
        elif key == "Coffee Backflush":
            print("Coffee Backflush", value)
            publish_mqtt_map(key, value)
            
async def main():
    state_tracker = StateTracker() # Initialise tracking of changed API states

    """Async main."""
    asyncio.create_task(mqtt_publisher()) # Initialise mqtt publisher
    
    # Generate or load key API material
    registration_required = False
    key_file = Path("installation_key.json")
    if not key_file.exists():
        print("Generating new key material...")
        installation_key = generate_installation_key(str(uuid.uuid4()).lower())
        print("Generated key material:")
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(installation_key.to_json())
        registration_required = True
    else:
        print("Loading existing key material...")
        with open(key_file, "r", encoding="utf-8") as f:
            installation_key = InstallationKey.from_json(f.read())
                        
    async def mqtt_listener(machine: LaMarzoccoMachine): # Homebridge mqtt listener
        async with aiomqtt.Client(MQTT_BROKER_IP_ADDRESS) as client:
            await client.subscribe(hb_incoming_mqtt_topic)
            async for message in client.messages:
                parsed_json = json.loads(message.payload.decode())
                await handle_homebridge_command(machine, parsed_json)
                    
    async def handle_homebridge_command(machine, parsed_json): # Process incoming Homebridge mqtt messages
        if parsed_json["name"] == "Coffee Power":
            if parsed_json["value"]:
                await machine.set_power(True)
            else:
                await machine.set_power(False)
        elif parsed_json["name"] == "Coffee Steam":
                if parsed_json["value"]:
                    await machine.set_steam(True)
                else:
                    await machine.set_steam(False)
        elif parsed_json["name"] == "Coffee Backflush":
            if parsed_json["value"]:      
                await machine.start_backflush()
        elif parsed_json["name"] == "Coffee Dose 1":
            if parsed_json["value"]:
                await machine.set_brew_by_weight_dose_mode("Dose1")
        elif parsed_json["name"] == "Coffee Dose 2":
            if parsed_json["value"]:
                await machine.set_brew_by_weight_dose_mode("Dose2")
        elif parsed_json["name"] == "Coffee Continuous":
            if parsed_json["value"]:
                await machine.set_brew_by_weight_dose_mode("Continuous")
        elif parsed_json["name"] == "Coffee BBW 1":
            if parsed_json["characteristic"] == "TargetTemperature" and parsed_json["value"] != 0:
                await machine.set_brew_by_weight_dose("Dose1", parsed_json["value"])
        elif parsed_json["name"] == "Coffee BBW 2":
            if parsed_json["characteristic"] == "TargetTemperature" and parsed_json["value"] != 0:
                await machine.set_brew_by_weight_dose("Dose2", parsed_json["value"])
        elif parsed_json["name"] == "Coffee Temp":
            if parsed_json["characteristic"] == "TargetTemperature" and parsed_json["value"] != 0:
                await machine.set_coffee_target_temperature(parsed_json["value"])
        elif parsed_json["name"] == "Coffee Steam 1" :
            if parsed_json["value"]:
                await(machine.set_steam_level("Level1"))
        elif parsed_json["name"] == "Coffee Steam 2" :
            if parsed_json["value"]:
                await(machine.set_steam_level("Level2"))
        elif parsed_json["name"] == "Coffee Steam 3" :
            if parsed_json["value"]:
                await(machine.set_steam_level("Level3"))

    async with ClientSession() as session: # Set up API cloud client session
        client = LaMarzoccoCloudClient(
            username=USERNAME,
            password=PASSWORD,
            installation_key=installation_key,
            client=session,
        )
        if registration_required:
            print("Registering device...")
            await client.async_register_client()
        machine = LaMarzoccoMachine(SERIAL, client)
        asyncio.create_task(mqtt_listener(machine))
        await machine.get_dashboard()
        phase = "Startup Phase"
        update_homebridge(machine.to_dict(), state_tracker, phase)
        
        def my_callback(config: ThingDashboardWebsocketConfig):
            phase = "Machine Update"
            update_homebridge(machine.to_dict(), state_tracker, phase)

        asyncio.create_task(machine.connect_dashboard_websocket(my_callback)) # Connect to dashboard websocket with optional callback
        await machine.connect_dashboard_websocket(my_callback)

asyncio.run(main())
