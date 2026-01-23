#!/usr/bin/env python3
#Northcliff La Marzocco mqtt Homebridge Manager - 1.0 pub
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
                "dashboard.widgets.3.output.mode", "dashboard.widgets.3.output.times.pre_brewing.0.seconds.In",
                "dashboard.widgets.3.output.times.pre_brewing.0.seconds.Out", "dashboard.widgets.4.output.scale_connected",
                "dashboard.widgets.4.output.mode", "dashboard.widgets.4.output.doses.dose_1.dose",
                "dashboard.widgets.4.output.doses.dose_2.dose", "dashboard.widgets.5.output.enabled",
                "dashboard.widgets.5.output.time_seconds", "dashboard.widgets.6.output.status"}

# Map API fields to readable topics
TOPIC_MAP = {"dashboard.widgets.0.output.mode": "Coffee Brewing Mode", "dashboard.widgets.0.output.status": "Coffee Power",
             "dashboard.widgets.1.output.status": "Coffee Boiler State", "dashboard.widgets.1.output.target_temperature": "Coffee Temp",
             "dashboard.widgets.2.output.status": "Coffee Steam State", "dashboard.widgets.2.output.target_level": "Coffee Steam Level",
             "dashboard.widgets.3.output.mode": "Coffee Pre-Brewing Mode", "dashboard.widgets.3.output.times.pre_brewing.0.seconds.In": "Coffee Pre-Brewing On Time",
             "dashboard.widgets.3.output.times.pre_brewing.0.seconds.Out": "Coffee Pre-Brewing Off Time",
             "dashboard.widgets.4.output.scale_connected": "Coffee Scale Connected", "dashboard.widgets.4.output.mode": "Coffee Dose",
             "dashboard.widgets.4.output.doses.dose_1.dose": "Coffee BBW 1 Weight", "dashboard.widgets.4.output.doses.dose_2.dose": "Coffee BBW 2 Weight",
             "dashboard.widgets.5.output.enabled": "Coffee Rinse Enabled", "dashboard.widgets.5.output.time_seconds": "Coffee Rinse Time",
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
            "Coffee BBW 1 Weight": [{"mqtt_map": homebridge_coffee_target_bbw1_format}, {"mqtt_map": homebridge_coffee_target_bbw1_state_format, "value": 1}],
            "Coffee BBW 2 Weight": [{"mqtt_map": homebridge_coffee_target_bbw2_format}, {"mqtt_map": homebridge_coffee_target_bbw2_state_format, "value": 1}],
            "Coffee Current BBW 1 Weight": [{"mqtt_map": homebridge_coffee_current_bbw1_format}],
            "Coffee Current BBW 2 Weight": [{"mqtt_map": homebridge_coffee_current_bbw2_format}],
            "Coffee Dose":[{"mqtt_map": homebridge_coffee_dose1_format, "value_map": {"Dose1": True, "Dose2": False, "Continuous": False}},
                           {"mqtt_map": homebridge_coffee_dose2_format, "value_map": {"Dose1": False, "Dose2": True, "Continuous": False}},
                           {"mqtt_map": homebridge_coffee_continuous_format, "value_map": {"Dose1": False, "Dose2": False, "Continuous": True}}],
            "Coffee Backflush":[{"mqtt_map": homebridge_coffee_backflush_format, "value_map": {"Off": False, "Requested": True, "Cleaning": True}},
                                {"mqtt_map": homebridge_coffee_action_backflush_format, "value_map": {"Off": False, "Requested": True, "Cleaning": False}}],
            "Coffee Steam Level":[{"mqtt_map": homebridge_coffee_steam1_format, "value_map": {"Level1": True, "Level2": False, "Level3": False}},
                           {"mqtt_map": homebridge_coffee_steam2_format, "value_map": {"Level1": False, "Level2": True, "Level3": False}},
                           {"mqtt_map": homebridge_coffee_steam3_format, "value_map": {"Level1": False, "Level2": False, "Level3": True}}]}

# Handlers for machine state update MQTT message logging and publishing
KEY_HANDLERS = {
    "Coffee Power": lambda k, v: log_and_publish(k, v, ""),
    
    "Coffee Brewing Mode": lambda k, v: handle_simple_print(k, v, ""),

    "Coffee Temp": lambda k, v: log_and_publish(k, v, "degrees C"),

    "Coffee Steam State": lambda k, v: log_and_publish(k, v, ""),

    "Coffee Steam Level": lambda k, v: log_and_publish(k, v, ""),
    
    "Coffee Pre-Brewing Mode": lambda k, v: handle_simple_print(k, v, ""),
    
    "Coffee Pre-Brewing On Time": lambda k, v: handle_simple_print(k, v, "seconds"),
    
    "Coffee Pre-Brewing Off Time": lambda k, v: handle_simple_print(k, v, "seconds"),

    "Coffee Dose": lambda k, v: log_and_publish(k, v, ""),

    "Coffee BBW 1 Weight": lambda k, v: log_and_publish(k, v, "grams"),

    "Coffee BBW 2 Weight": lambda k, v: log_and_publish(k, v, "grams"),
    
    "Coffee Rinse Enabled": lambda k, v: handle_simple_print(k, v, ""),
    
    "Coffee Rinse Time": lambda k, v: handle_simple_print(k, v, "seconds"),

    "Coffee Backflush": lambda k, v: log_and_publish(k, v, "")
}


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

async def mqtt_publisher():
    while True:
        try:
            async with aiomqtt.Client(MQTT_BROKER_IP_ADDRESS) as client:
                while True:
                    topic, payload = await mqtt_publish_queue.get()
                    await client.publish(topic, json.dumps(payload))
                    mqtt_publish_queue.task_done()
        except Exception:
            LOG.exception("MQTT connection lost, retrying in 5s")
            await asyncio.sleep(5)

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

def log_and_publish(key, value, units):  # Use dispatch table for simple prints and publishes
    print(f"	{key}: {value} {units}")
    publish_mqtt_map(key, value)
    
def handle_simple_print(key, value, units): # Use dispatch table for simple prints
    print(f"	{key}: {value} {units}")
    
def update_homebridge(machine_dict: dict, tracker: StateTracker, phase): # Update Homebridge with any changed API states
    print_update(phase)
    flat = flatten(machine_dict)
    #print(json.dumps(flat, indent =2))
    mapped = map_topics(flat)
    target_temp = mapped.get("Coffee Temp", 93)
    bbw_1 = mapped.get("Coffee BBW 1 Weight", 14)
    bbw_2 = mapped.get("Coffee BBW 2 Weight", 14)
    #print(json.dumps(mapped, indent =2))
    #print(" ")
    changed = tracker.update(mapped)
    if not changed:
        print("No Changed States")
    else:
        print("Changed States:")
    for key, value in changed.items():
        if key == "Coffee Boiler State":
            if value == "StandBy":
                temp_value = 80
            elif value == "HeatingUp":
                temp_value = 80
            elif value == "NoWater":
                temp_value = 80
            elif value == "Ready":
                temp_value = target_temp
            handle_simple_print(key, value, "")
            publish_mqtt_map("Coffee Boiler State", value)
            publish_mqtt_map("Current Coffee Temp", temp_value)
            continue
        if key == "Coffee Scale Connected":
            handle_simple_print(key, value, "")
            bbw_1_value = bbw_1 if value else 14
            bbw_2_value = bbw_2 if value else 14
            publish_mqtt_map("Coffee Current BBW 1 Weight", bbw_1_value)
            publish_mqtt_map("Coffee Current BBW 2 Weight", bbw_2_value)
            continue      
        handler = KEY_HANDLERS.get(key) # Use dispatch table for simple prints and publishes
        if handler:
            handler(key, value)
        else:
            LOG.debug("Unhandled changed state update key: %s = %s", key, value)
 
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
        update_homebridge(machine.to_dict(), state_tracker, "Startup Phase")
        
        def my_callback(config: ThingDashboardWebsocketConfig):
            update_homebridge(machine.to_dict(), state_tracker, "Machine Update")

        await machine.connect_dashboard_websocket(my_callback)
        
asyncio.run(main())
